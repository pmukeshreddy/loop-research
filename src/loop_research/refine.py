"""Background planning, precise host-side edits at model-turn boundaries."""
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
import copy
import json
import threading
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from .archive import append_json, stamp


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


class Proposal(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    summary: str
    edits: list[Edit]


INSTRUCTIONS = '''Refine supplemental harness state from this run's trajectory and deterministic self-check.
The base system prompt, tool code, grader code and self-check code are immutable.
Use the smallest evidence-backed edit. Update, merge (update then delete), or delete existing entries
before creating anything new. Never rewrite the whole harness. An empty edits list is valid when
there is no reusable lesson. Failures become memories; successful repeatable tactics become skills.
Review usage and self-check outcomes: revise or delete entries whose outcomes are consistently bad.
No answer keys or grades are available. Preserve procedures and failure modes, not benchmark answers.
Skills may include a standalone Python module as source text; it will execute only in the isolated REPL.
Use create/update/delete, the existing bare ids, and full title/content for create/update.
For delete use null title/content/module. For create use null id. Return the requested JSON schema.
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

    def resume(self):
        with self.lock:
            job = self.ctx.load('refine_state.json')
            if self.pending is not None or not job or job['status'] in {'applied', 'discarded'}:
                return False
            if not self.enabled:
                raise ValueError('Cannot resume refinement with learning disabled')
            self.focus = job['focus']
            if job.get('proposal') is not None:
                self.pending = Future()
                self.pending.set_result(job)
            else:
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
                return {'scheduled': False, 'reason': 'already_applied'}
            if self.pending is not None:
                self.audit('skipped_request', reason='planning_in_progress', requested_focus=focus)
                return {'scheduled': False, 'reason': 'planning already in progress'}
            if self.resume():
                return {'scheduled': True, 'resumed': True}
            snapshot = self.harness.snapshot()
            observed = self.observation()
            if set(observed) != {'trajectory', 'self_check'}:
                raise ValueError('Refinement receives only trajectory and self-check')
            self.focus = focus
            job = {'status': 'planning', 'focus': focus, 'snapshot': snapshot, 'observed': observed,
                   'branch': self.harness.branch, 'proposal': None, 'request_id': request_id or uuid4().hex}
            self.ctx.save('refine_state.json', job)
            self.ctx.trace.emit('Refine', 'scheduled', focus=focus, request_id=job['request_id'])
            self.pending = self.pool.submit(copy_context().run, self._plan, job)
            return {'scheduled': True}

    def _plan(self, job):
        with self.ctx.trace.span('Refine', 'planning', focus=job['focus'], request_id=job['request_id']):
            return self._plan_job(job)

    def _plan_job(self, job):
        prompt = INSTRUCTIONS + json.dumps({'focus': job['focus'], 'entries': list(job['snapshot']['entries'].values()),
                                            **job['observed']}, ensure_ascii=False)
        schema = Proposal.model_json_schema()
        schema['properties']['edits']['maxItems'] = self.ctx.config.refine.max_edits
        text = None
        try:
            text = self.backend.complete(prompt, purpose='refine', model=self.ctx.config.models.refine, schema=schema)
            proposal = Proposal.model_validate_json(text)
            if len(proposal.edits) > self.ctx.config.refine.max_edits:
                raise ValueError('Proposal exceeds refine.max_edits')
            for edit in proposal.edits:
                if edit.id is not None:
                    self.harness._key(edit.kind, edit.id)
            self.ctx.trace.emit('Refine', 'proposal', summary=proposal.summary, edits=[edit.model_dump() for edit in proposal.edits])
            job.update(status='planned', proposal=proposal.model_dump(),
                       operations=['refine_' + uuid4().hex for _ in proposal.edits])
            self.ctx.save('refine_state.json', job)
            return job
        except Exception as exc:
            job.update(status='failed', error=str(exc))
            self.ctx.save('refine_state.json', job)
            self.audit('discarded', reason='planning_failed', error=str(exc), proposal=text)
            raise

    def boundary(self, wait=False):
        with self.lock:
            if self.pending is None or (not wait and not self.pending.done()):
                return []
            future, self.pending = self.pending, None
            job = future.result()
            with self.harness.transaction():
                try:
                    with self.ctx.trace.span('Refine', 'apply', focus=job['focus']) as details:
                        result = self._apply(job)
                        details['commits'] = result
                        return result
                except Exception as exc:
                    self.audit('failed', reason='apply_failed', error=str(exc), proposal=job['proposal'])
                    raise

    def _discard(self, job, reason):
        self.audit('discarded', reason=reason, proposal=job['proposal'])
        job['status'] = 'discarded'
        self.ctx.save('refine_state.json', job)

    def _apply(self, job):
        if job['branch'] != self.harness.branch:
            self._discard(job, 'lineage_changed')
            return []
        proposal = Proposal.model_validate(job['proposal'])
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
                        self.audit('skipped_delete', reason='entry_missing', kind=edit.kind, id=edit.id)
                        continue
            commits.append(self.harness.head)
            self.ctx.trace.emit('Refine', 'edit_applied', commit=self.harness.head,
                                edit=edit.model_dump(), operation_id=operation)
        self.audit('applied', summary=proposal.summary, commits=commits)
        job['status'] = 'applied'
        self.ctx.save('refine_state.json', job)
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
