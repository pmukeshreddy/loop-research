"""Background planning, precise host-side edits at model-turn boundaries."""
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
import copy
import hashlib
import json
import re
import threading
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .archive import append_json, digest, stamp
from .shared_text import encode_shared_text


class Edit(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    action: Literal['create', 'update', 'delete']
    kind: Literal['prompt', 'memory', 'skill', 'subagent']
    id: str | None
    title: str | None
    content: str | None
    module: str | None

    @model_validator(mode='after')
    def valid_operation(self):
        if self.action != 'create' and not self.id:
            raise ValueError('Update/delete require an existing entry id')
        if self.action != 'delete' and (not self.title or not self.title.strip() or not self.content or not self.content.strip()):
            raise ValueError('Create/update require nonempty title and content')
        if self.module is not None and self.kind != 'skill':
            raise ValueError('Only skills may have Python modules')
        return self


class HistoricalProposal(BaseModel):
    """Only for resuming proposals persisted before candidate accounting existed."""
    model_config = ConfigDict(extra='forbid', strict=True)
    summary: str
    edits: list[Edit]


Nonblank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Candidate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: Nonblank
    description: Nonblank
    evidence_refs: list[Nonblank] = Field(min_length=1)


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    candidate_id: Nonblank
    decision: Literal['accepted', 'declined']
    reason: Nonblank
    evidence_refs: list[Nonblank] = Field(min_length=1)
    edit_indexes: list[int]


class Proposal(HistoricalProposal):
    additional_candidates: list[Candidate]
    decisions: list[Decision]


def candidate_inventory(observed):
    """Group current-run evidence without inventing lessons or dropping occurrences."""
    candidates = []
    for collection in ('issues', 'signals'):
        groups = {}
        for index, item in enumerate(observed['self_check'].get(collection, [])):
            kind = item.get('type') if isinstance(item, dict) else None
            kind = kind if isinstance(kind, str) and kind else 'untyped'
            if kind not in groups:
                groups[kind] = {'id': f'self_check:{collection}:{kind}', 'source': f'self_check.{collection}',
                                'type': kind, 'count': 0, 'evidence_refs': []}
                candidates.append(groups[kind])
            groups[kind]['count'] += 1
            groups[kind]['evidence_refs'].append(f'/self_check/{collection}/{index}')
    errors = {}
    for index, event in enumerate(observed['trajectory']):
        if not isinstance(event, dict) or event.get('type') != 'worker_iteration':
            continue
        for block_index, block in enumerate(event['event'].get('code_blocks', [])):
            stderr = block.get('result', {}).get('stderr')
            if not isinstance(stderr, str) or not stderr.strip():
                continue
            if stderr not in errors:
                errors[stderr] = {'id': f'trajectory:stderr:{index}:{block_index}', 'source': 'trajectory',
                                  'type': 'execution_stderr', 'error': stderr, 'count': 0, 'evidence_refs': []}
                candidates.append(errors[stderr])
            errors[stderr]['count'] += 1
            errors[stderr]['evidence_refs'].append(f'/trajectory/{index}/event/code_blocks/{block_index}/result/stderr')
    return candidates


def planning_input(job):
    return {'focus': job['focus'], 'candidate_inventory': job['candidate_inventory'],
            'entries': list(job['snapshot']['entries'].values()), **job['observed']}


def evidence_anchors(payload):
    """Finite source paths for generation, without removing evidence or candidates."""
    refs = ['/trajectory', '/self_check', '/entries']
    for collection in ('trajectory', 'entries'):
        refs.extend(f'/{collection}/{index}' for index in range(len(payload[collection])))
    refs.extend('/self_check/' + key.replace('~', '~0').replace('/', '~1')
                for key in payload['self_check'])
    for candidate in payload['candidate_inventory']:
        refs.extend(candidate['evidence_refs'])
    return list(dict.fromkeys(refs))


def validate_accounting(proposal, payload):
    """Check coverage and evidence identity; semantic soundness remains a model judgment."""
    candidates = {item['id']: item['evidence_refs'] for item in payload['candidate_inventory']}

    def check_refs(refs):
        for ref in refs:
            parts = ref.split('/')
            if len(parts) < 2 or parts[0] != '' or parts[1] not in {'trajectory', 'self_check', 'entries'}:
                raise ValueError(f'Invalid evidence reference: {ref}')
            value = payload
            try:
                for part in parts[1:]:
                    key = part.replace('~1', '/').replace('~0', '~')
                    if isinstance(value, list):
                        if not key.isdecimal() or str(int(key)) != key:
                            raise KeyError(key)
                        value = value[int(key)]
                    elif isinstance(value, dict):
                        value = value[key]
                    else:
                        raise KeyError(key)
            except (KeyError, IndexError):
                raise ValueError(f'Invalid evidence reference: {ref}') from None

    for candidate in proposal.additional_candidates:
        if candidate.id in candidates:
            raise ValueError('Candidate ids must be unique')
        check_refs(candidate.evidence_refs)
        candidates[candidate.id] = candidate.evidence_refs
    ids = [decision.candidate_id for decision in proposal.decisions]
    if len(ids) != len(set(ids)) or set(ids) != set(candidates):
        raise ValueError('Every presented and additional candidate requires a decision exactly once')
    linked_edits = set()
    for decision in proposal.decisions:
        check_refs(decision.evidence_refs)
        if not any(ref == source or ref.startswith(source + '/')
                   for ref in decision.evidence_refs for source in candidates[decision.candidate_id]):
            raise ValueError('Decision must cite its candidate evidence')
        if decision.decision == 'declined' and decision.edit_indexes:
            raise ValueError('Declined candidates cannot link edits')
        if decision.decision == 'accepted' and not decision.edit_indexes:
            raise ValueError('Accepted candidates must link edits')
        if any(index < 0 or index >= len(proposal.edits) for index in decision.edit_indexes):
            raise ValueError('Decision references an invalid edit index')
        linked_edits.update(decision.edit_indexes)
    if linked_edits != set(range(len(proposal.edits))):
        raise ValueError('Every edit must be linked to an accepted candidate')


PLANNING_INSTRUCTIONS = '''Refine supplemental harness state from this run's trajectory and deterministic self-check.
The base system prompt, tool code, grader code and self-check code are immutable.
Evaluate every candidate in candidate_inventory, including every occurrence in its evidence_refs.
These are evidence groups to consider, not predetermined lessons. A passing self-check does not
dismiss process signals; recovered failures can still support a reusable lesson, or justify no edit.
Add any further candidates you identify in the trajectory or harness outcomes to additional_candidates.
Give every presented and additional candidate exactly one accepted/declined decision, a nonempty
evidence-based reason, and evidence_refs as JSON pointers into /trajectory, /self_check or /entries.
Choose references from evidence_index, the visible list of existing source anchors in this snapshot.
Array indexes are zero-based. A record anchor cites its complete contents; explain the relevant
field in your reason. The output schema permits only these anchors. Additional candidates may
cite any listed anchor, including successful observations and existing harness entries.
Each decision must cite at least one of its candidate's evidence_refs (or a child of that reference).
Explain the evidence for accepting or declining the whole group, including recovery, existing coverage,
insufficient support, or edit-budget prioritization when relevant. Do not silently skip a candidate.
Accepted decisions list their zero-based edit_indexes; declined decisions list no edit indexes.
Every edit must be linked to an accepted candidate. Multiple candidates may share an edit.
Use minimal evidence-backed edits. The configured max_edits is a ceiling, never a target or minimum.
Update, merge (update then delete), or delete existing entries
before creating anything new. Never rewrite the whole harness. An empty edits list is valid when
there is no reusable lesson. Failures become memories; successful repeatable tactics become skills.
Review usage and self-check outcomes: revise or delete entries whose outcomes are consistently bad.
No answer keys or grades are available. Preserve procedures and failure modes, not benchmark answers.
Skills may include a standalone Python module as source text; it will execute only in the isolated REPL.
Use create/update/delete, the existing bare ids, and full title/content for create/update.
For delete use null title/content/module. For create use null id. Return the requested JSON schema.
'''

INSTRUCTIONS = PLANNING_INSTRUCTIONS + '''\
The input uses a lossless shared-text-v2 or shared-text-v3 representation, not a summary.
The format field identifies the selected version. Its shared_texts array
contains exact literal strings. In payload, {"$shared_text": N} means that complete string
at zero-based index N. {"$shared_text_parts": PARTS} means concatenate the listed literal
strings and shared-text references in order, with no added separators or normalization.
This preserves repeated text embedded inside otherwise different prompts and code blocks.
In v3 only, {"$json_quote": N} means apply json.dumps(shared_texts[N], ensure_ascii=False)
exactly once, including the surrounding double quotes and JSON escapes. This reference can
also be a part in $shared_text_parts. It preserves a JSON-quoted occurrence of the same
raw text; it does not change the original string's spelling. All table entries remain
literal strings. V1/v2 have no $json_quote marker; that key is an ordinary literal key there.
{"$literal_object": OBJECT} escapes an original object with a reserved
marker shape: keep that object's keys and recursively decode its values. Decode references
recursively; every original field and string occurrence is retained. Evidence pointers address
the decoded logical payload, not this representation's wrapper or shared_texts table.
Return ordinary strings in the proposal, never shared-text markers.
'''


class Refiner:
    def __init__(self, harness, ctx, backend, observation, *, enabled=True):
        self.harness, self.ctx, self.backend, self.observation = harness, ctx, backend, observation
        self.enabled = enabled
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='refine')
        self.pending = None
        self.lock = threading.RLock()
        self.focus = None

    def audit(self, status, **details):
        self.ctx.trace.emit('Refine', status, focus=self.focus, **details)
        append_json(self.ctx.path / 'refinements.jsonl', {'created_at': stamp(), 'status': status,
                                                       'focus': self.focus, **details})

    def _save_job(self, job):
        job.setdefault('job_id', uuid4().hex)
        # Archive first: advancing the resumable latest pointer must never erase an earlier input.
        self.ctx.save(f"refine_requests/{digest(job['request_id'])}/{job['job_id']}.json", job)
        self.ctx.save('refine_state.json', job)

    def status(self):
        """Read one durable job and prove its operations against one immutable Git HEAD.

        This never waits for planning, resumes a job, or applies a proposal. In
        particular, a planned job may already have receipts after an interrupted
        apply; receipts and durable lifecycle state remain separate facts.
        """
        with self.lock, self.harness.lock:
            job = self.ctx.load('refine_state.json')
            result = {'enabled': self.enabled, 'state': 'idle', 'request_id': None, 'job_id': None,
                      'focus': None, 'proposal': None, 'error': None, 'commits': []}
            if job is None:
                return result
            result.update(state=job['status'], request_id=job['request_id'], job_id=job.get('job_id'),
                          focus=job['focus'], proposal=job['proposal'], error=job.get('error'))
            head = self.harness.head
            for operation in job.get('operations', []):
                if not isinstance(operation, str) or not re.fullmatch(r'refine_[a-f0-9]+', operation):
                    raise ValueError('Invalid refinement identity')
                path = 'edits/' + operation + '.json'
                if not self.harness.git('ls-tree', '--name-only', head, '--', path):
                    continue
                record = json.loads(self.harness.git('show', head + ':' + path))
                if record['id'] != operation:
                    raise ValueError('Committed refinement identity mismatch')
                result['commits'].append({'operation_id': operation,
                    'commit': self.harness.git('log', '-1', '--format=%H', head, '--', path),
                    'key': record['key'], 'action': record['action']})
            return result

    def resume(self):
        with self.lock:
            job = self.ctx.load('refine_state.json')
            if self.pending is not None or not job or job['status'] in {'applied', 'discarded'}:
                return False
            if not self.enabled:
                raise ValueError('Cannot resume refinement with learning disabled')
            self.focus = job['focus']
            if 'job_id' not in job:
                self._save_job(job)
            if job.get('proposal') is not None:
                self.pending = Future()
                self.pending.set_result(job)
            else:
                if 'planner_prompt' in job:
                    # A new model attempt must not overwrite the prior input or rejected response.
                    job = {key: value for key, value in job.items()
                           if key not in {'planner_prompt', 'planner_schema', 'planner_representation', 'planner_transport', 'evidence_index',
                                          'response_text', 'error', 'operations'}}
                    job.update(job_id=uuid4().hex, status='planning')
                    self._save_job(job)
                self.pending = self.pool.submit(copy_context().run, self._plan, job)
            return True

    def run(self, focus=None, *, request_id=None):
        if focus is not None and not isinstance(focus, str):
            raise TypeError('focus must be text or None')
        with self.lock:
            if not self.enabled:
                return {'scheduled': False, 'reason': 'no-learning comparison'}
            previous = self.ctx.load('refine_state.json')
            if request_id and previous and previous.get('request_id') == request_id and previous['status'] == 'applied':
                return {'scheduled': False, 'reason': 'already_applied',
                        'request_id': previous['request_id'], 'job_id': previous.get('job_id')}
            if self.pending is not None:
                self.audit('skipped_request', reason='planning_in_progress', requested_focus=focus)
                return {'scheduled': False, 'reason': 'planning already in progress',
                        'request_id': previous['request_id'], 'job_id': previous.get('job_id')}
            if self.resume():
                resumed = self.ctx.load('refine_state.json')
                return {'scheduled': True, 'resumed': True,
                        'request_id': resumed['request_id'], 'job_id': resumed['job_id']}
            if previous:
                self._save_job(previous)
            snapshot = self.harness.snapshot()
            observed = self.observation()
            if set(observed) != {'trajectory', 'self_check'}:
                raise ValueError('Refinement receives only trajectory and self-check')
            self.focus = focus
            job = {'status': 'planning', 'focus': focus, 'snapshot': snapshot, 'observed': observed,
                   'branch': self.harness.branch, 'proposal': None, 'request_id': request_id or uuid4().hex}
            job.update(accounting_version=1, candidate_inventory=candidate_inventory(observed))
            self._save_job(job)
            self.ctx.trace.emit('Refine', 'scheduled', focus=focus, request_id=job['request_id'], job_id=job['job_id'])
            self.pending = self.pool.submit(copy_context().run, self._plan, job)
            return {'scheduled': True, 'request_id': job['request_id'], 'job_id': job['job_id']}

    def _plan(self, job):
        with self.ctx.trace.span('Refine', 'planning', focus=job['focus'], request_id=job['request_id'], job_id=job['job_id']):
            return self._plan_job(job)

    def _plan_job(self, job):
        # Unplanned historical jobs upgrade here; already-planned jobs keep their recorded schema.
        job.update(accounting_version=1, candidate_inventory=candidate_inventory(job['observed']))
        payload = planning_input(job)
        payload['max_edits'] = self.ctx.config.refine.max_edits
        payload['evidence_index'] = evidence_anchors(payload)
        logical_text = json.dumps(payload, ensure_ascii=False)
        wire = encode_shared_text(payload)
        wire_text = json.dumps(wire, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        prompt = INSTRUCTIONS + wire_text
        schema = Proposal.model_json_schema()
        schema['properties']['edits']['maxItems'] = self.ctx.config.refine.max_edits
        schema['$defs']['EvidenceRef'] = {'type': 'string', 'enum': payload['evidence_index']}
        for definition in ('Candidate', 'Decision'):
            schema['$defs'][definition]['properties']['evidence_refs']['items'] = {'$ref': '#/$defs/EvidenceRef'}
        job.update(planner_prompt=prompt, planner_schema=schema, evidence_index=payload['evidence_index'], planner_representation={
            'format': wire['format'],
            'logical_payload_chars': len(logical_text),
            'logical_payload_sha256': hashlib.sha256(logical_text.encode()).hexdigest(),
            'wire_payload_chars': len(wire_text),
            'wire_payload_sha256': hashlib.sha256(wire_text.encode()).hexdigest(),
        })
        self._save_job(job)
        text = None
        try:
            from .codex_backend import INSTRUCTION
            from .refine_context import MAX_PROMPT_CHARS, plan_context
            if len(INSTRUCTION + prompt) > MAX_PROMPT_CHARS:
                job['planner_transport'] = {'kind': 'repl-context-v1', 'input_limit_chars': MAX_PROMPT_CHARS,
                                            'complete_prompt_chars': len(INSTRUCTION + prompt)}
                self._save_job(job)
                text = plan_context(self.ctx, self.backend, job['job_id'], logical_text, schema,
                                    PLANNING_INSTRUCTIONS)
            else:
                text = self.backend.complete(prompt, purpose='refine', model=self.ctx.config.models.refine, schema=schema)
            job['response_text'] = text
            self._save_job(job)
            proposal = Proposal.model_validate_json(text)
            if len(proposal.edits) > self.ctx.config.refine.max_edits:
                raise ValueError('Proposal exceeds refine.max_edits')
            validate_accounting(proposal, payload)
            if job.get('planner_transport', {}).get('kind') == 'repl-context-v1':
                from jsonschema import Draft202012Validator, ValidationError
                try:
                    Draft202012Validator(schema).validate(json.loads(text))
                except ValidationError as error:
                    raise ValueError('Proposal does not satisfy planner schema: ' + str(error)) from error
            for edit in proposal.edits:
                if edit.id is not None:
                    self.harness._key(edit.kind, edit.id)
            self.ctx.trace.emit('Refine', 'proposal', request_id=job['request_id'], job_id=job['job_id'], **proposal.model_dump())
            job.update(status='planned', proposal=proposal.model_dump(),
                       operations=['refine_' + uuid4().hex for _ in proposal.edits])
            self._save_job(job)
            return job
        except Exception as exc:
            job.update(status='failed', error=str(exc))
            self._save_job(job)
            self.audit('discarded', request_id=job['request_id'], job_id=job['job_id'],
                       reason='planning_failed', error=str(exc), proposal=text)
            raise

    def boundary(self, wait=False):
        with self.lock:
            if self.pending is None or (not wait and not self.pending.done()):
                return []
            future, self.pending = self.pending, None
            job = future.result()
            with self.harness.transaction():
                try:
                    with self.ctx.trace.span('Refine', 'apply', focus=job['focus'],
                                             request_id=job['request_id'], job_id=job['job_id']) as details:
                        result = self._apply(job)
                        details['commits'] = result
                        return result
                except Exception as exc:
                    self.audit('failed', request_id=job['request_id'], job_id=job['job_id'],
                               reason='apply_failed', error=str(exc), proposal=job['proposal'])
                    raise

    def _discard(self, job, reason):
        self.audit('discarded', request_id=job['request_id'], job_id=job['job_id'], reason=reason, proposal=job['proposal'])
        job['status'] = 'discarded'
        self._save_job(job)

    def _apply(self, job):
        if job['branch'] != self.harness.branch:
            self._discard(job, 'lineage_changed')
            return []
        if 'accounting_version' not in job:
            proposal = HistoricalProposal.model_validate(job['proposal'])
        elif job['accounting_version'] == 1:
            proposal = Proposal.model_validate(job['proposal'])
            validate_accounting(proposal, planning_input(job))
        else:
            raise ValueError('Unknown refinement accounting version')
        expected = copy.deepcopy(job['snapshot']['entries'])
        records = [self.harness.edit_record(op) for op in job['operations']]
        for record in records:
            if record:
                if record['after'] is None:
                    expected.pop(record['key'], None)
                else:
                    expected[record['key']] = record['after']
        current = self.harness.snapshot()
        for edit, record in zip(proposal.edits, records):
            key = edit.kind + ':' + str(edit.id)
            if record is None and edit.action != 'create' and current['entries'].get(key) != expected.get(key):
                self._discard(job, 'target_changed')
                self.run(self.focus, request_id=job['request_id'])
                return []
        commits = []
        for edit, operation, record in zip(proposal.edits, job['operations'], records):
            if record:
                commits.append(self.harness.git('log', '-1', '--format=%H', '--', 'edits/' + operation + '.json'))
                continue
            kwargs = {'trigger': self.focus or 'after task', 'evidence': [self.ctx.run_id + '/' + self.ctx.task_id],
                      'operation_id': operation}
            with self.ctx.trace.span('Harness', 'refine_edit', action=edit.action, kind=edit.kind, id=edit.id):
                if edit.action == 'create':
                    self.harness.create(edit.kind, edit.title, edit.content, id=operation.removeprefix('refine_'),
                                        module=edit.module, **kwargs)
                elif edit.action == 'update':
                    previous = self.harness.get(edit.kind, edit.id)
                    self.harness.update(edit.kind, edit.id, edit.title, edit.content, module=edit.module,
                                        expected_version=previous['version'] if previous else None, **kwargs)
                else:
                    previous = self.harness.get(edit.kind, edit.id)
                    if not self.harness.delete(edit.kind, edit.id,
                            expected_version=previous['version'] if previous else None, **kwargs):
                        self.audit('skipped_delete', request_id=job['request_id'], job_id=job['job_id'],
                                   reason='entry_missing', kind=edit.kind, id=edit.id)
                        continue
            commits.append(self.harness.head)
            self.ctx.trace.emit('Refine', 'edit_applied', commit=self.harness.head,
                                request_id=job['request_id'], job_id=job['job_id'],
                                edit=edit.model_dump(), operation_id=operation)
        self.audit('applied', request_id=job['request_id'], job_id=job['job_id'], **proposal.model_dump(), commits=commits)
        job['status'] = 'applied'
        self._save_job(job)
        return commits

    def rollback(self, id, *, operation_id=None):
        if not self.enabled:
            raise ValueError('Harness writes disabled for no-learning comparison')
        with self.ctx.trace.span('Refine', 'rollback', id=id, operation_id=operation_id) as details:
            result = self.harness.rollback(id, operation_id=operation_id)
            if self.ctx.trace.enabled:
                details.update(commit=self.harness.head, result=result)
        if result is False:
            self.audit('skipped_delete', reason='entry_missing', rollback=id)
        return result

    def close(self):
        self.pool.shutdown(wait=True)
