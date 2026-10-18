"""Background planning, precise host-side edits at model-turn boundaries."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    edits: list[Edit] = Field(max_length=2)


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

    def run(self, focus=None):
        if focus is not None and not isinstance(focus, str):
            raise TypeError('focus must be text or None')
        with self.lock:
            if not self.enabled:
                return {'scheduled': False, 'reason': 'no-learning comparison'}
            if self.pending is not None:
                return {'scheduled': False, 'reason': 'planning already in progress'}
            snapshot = self.harness.snapshot()
            observed = self.observation()
            if set(observed) != {'trajectory', 'self_check'}:
                raise ValueError('Refinement receives only trajectory and self-check')
            self.focus = focus
            self.pending = self.pool.submit(self._plan, snapshot, observed, focus, self.harness.branch)
            return {'scheduled': True}

    def _plan(self, snapshot, observed, focus, branch):
        prompt = INSTRUCTIONS + json.dumps({'focus': focus, 'entries': list(snapshot['entries'].values()),
                                            **observed}, ensure_ascii=False)
        text = self.backend.complete(prompt, purpose='refine', model=self.ctx.config.models.refine,
                                     schema=Proposal.model_json_schema())
        return branch, snapshot, Proposal.model_validate_json(text)

    def boundary(self, wait=False):
        with self.lock:
            if self.pending is None or (not wait and not self.pending.done()):
                return []
            future, self.pending = self.pending, None
            branch, snapshot, proposal = future.result()
            with self.harness.transaction():
                return self._apply(branch, snapshot, proposal)

    def _apply(self, branch, snapshot, proposal):
        if branch != self.harness.branch:
            return []
        current = self.harness.snapshot()
        for edit in proposal.edits:
            key = edit.kind + ':' + str(edit.id)
            if edit.action != 'create' and current['entries'].get(key) != snapshot['entries'].get(key):
                self.run(self.focus)
                return []
        commits = []
        for edit in proposal.edits:
            kwargs = {'trigger': self.focus or 'after task', 'evidence': [self.ctx.run_id + '/' + self.ctx.task_id]}
            if edit.action == 'create':
                self.harness.create(edit.kind, edit.title, edit.content, module=edit.module, **kwargs)
            elif edit.action == 'update':
                previous = snapshot['entries'].get(edit.kind + ':' + str(edit.id))
                self.harness.update(edit.kind, edit.id, edit.title, edit.content, module=edit.module,
                                    expected_version=previous['version'] if previous else None, **kwargs)
            else:
                previous = snapshot['entries'].get(edit.kind + ':' + str(edit.id))
                if not self.harness.delete(edit.kind, edit.id,
                        expected_version=previous['version'] if previous else None, **kwargs):
                    continue
            commits.append(self.harness.head)
        append_json(self.ctx.path / 'refinements.jsonl', {'created_at': stamp(), 'focus': self.focus,
                    'summary': proposal.summary, 'commits': commits})
        return commits


    def rollback(self, id):
        if not self.enabled:
            raise ValueError('Harness writes disabled for no-learning comparison')
        return self.harness.rollback(id)

    def close(self):
        self.pool.shutdown(wait=True)
