"""Trusted research services; no graders or answer stores are imported here."""
from collections import Counter
import json
import threading
from concurrent.futures import Future
from dataclasses import replace
from uuid import uuid4

from .archive import append_json, read_jsonl, count_codex_calls
from .codex_backend import CodexBackend, CallBudget, BudgetExceeded
from .refine import Refiner
from .repl_tools import ResearchTools
from .selfcheck import check


class Session:
    def __init__(self, task, ctx, harness, *, learning=True, backend=None, resume=False):
        self.task, self.ctx, self.harness, self.learning = task, ctx, harness, learning
        self.run_id = ctx.run_id + '/' + ctx.task_id
        self.budget = CallBudget(ctx.config.agent.max_codex_calls, ctx.config.agent.task_timeout_s)
        self.budget.count = count_codex_calls(ctx.path, exclude_purposes=('grade', 'refine'))
        self.research_ctx = replace(ctx, cancellation=Future())
        self.backend = backend or CodexBackend(self.research_ctx, budget=self.budget)
        self.repair_backend = backend or CodexBackend(ctx, budget=self.budget)
        self.tools = ResearchTools(self.backend, self.research_ctx)
        self.lifecycle = threading.RLock()
        self.status = {}
        self.output = {'rows': []}
        self.turns = 0
        self.turn_lock = threading.Lock()
        state = ctx.load('session_state.json', {})
        self.rollbacks = state.get('rollbacks', [])
        self.finish_phase = state.get('finish_phase', 'pending')
        self.automatic_id = state.get('automatic_id', uuid4().hex)
        self.fatal = None if resume else state.get('fatal')
        self.refiner = Refiner(harness, ctx, CodexBackend(ctx), self.observation, enabled=learning)
        if ctx.cancellation is not None:
            ctx.cancellation.add_done_callback(lambda _: self.close_worker())

    def close_worker(self):
        with self.lifecycle, self.tools.lock:
            self.research_ctx.cancellation.cancel()

    def checkpoint(self):
        self.ctx.save('session_state.json', {'rollbacks': self.rollbacks, 'finish_phase': self.finish_phase,
                      'automatic_id': self.automatic_id, 'fatal': self.fatal})

    def apply_refinement(self, wait=False):
        if self.fatal:
            raise RuntimeError(self.fatal)
        operation = 'Refinement'
        try:
            commits = self.refiner.boundary(wait=wait)
            while self.rollbacks:
                operation = 'Rollback'
                self.refiner.rollback(**self.rollbacks[0])
                self.rollbacks.pop(0)
                self.checkpoint()
            return commits
        except Exception as exc:
            self.fatal = f'{operation} failed: {type(exc).__name__}: {exc}'
            self.refiner.audit('failed', reason=operation.lower(), error=self.fatal)
            self.checkpoint()
            raise RuntimeError(self.fatal) from exc

    def retrieve(self):
        query = self.task.question + ' ' + json.dumps(self.task.spec, ensure_ascii=False)
        trace = self.ctx.trace
        with trace.span('Harness', 'retrieve', query=query) as details:
            if trace.enabled:
                details['head_before'] = self.harness.head
            options = {'on_retrieved': lambda entries: details.update(entries=entries)} if trace.enabled else {}
            entries = self.harness.search(query, limit=self.ctx.config.harness.retrieval_limit, **options)
            self.harness.record_usage(entries, self.run_id)
            if trace.enabled:
                details['head_after'] = self.harness.head
            # Outcomes remain in the store/refiner, not in every research turn.
            # Preserve all procedural content and provenance without recursively
            # importing previous tasks' self-check records into the root context.
            return [{key: value for key, value in entry.items() if key not in {'usage', 'outcomes'}}
                    for entry in entries]

    def self_check(self):
        with self.ctx.trace.span('Output', 'self_check') as details:
            report = check(self.task, self.output, self.tools.snapshot(), self.status)
            details.update(ok=report['ok'], issues_by_type=dict(Counter(i['type'] for i in report['issues'])),
                           issues=report['issues'], signals=report['signals'],
                           signals_by_type=dict(Counter(s['type'] for s in report['signals'])))
        self.ctx.save('self_check.json', report)
        return report

    def observation(self):
        trajectory = read_jsonl(self.ctx.path / 'trajectory.jsonl')
        root_seen = False
        for record in trajectory:
            if record['type'] == 'model' and record['purpose'] == 'root':
                # Keep the initial task/instructions, then each new response.
                # Later root prompts repeat the accumulated conversation.
                if root_seen:
                    record.pop('prompt')
                root_seen = True
            elif record['type'] == 'worker_iteration':
                event = record['event']
                event.pop('prompt', None)
                event.pop('response', None)  # Already in the model record.
                for block in event.get('code_blocks', []):
                    block['result'].pop('locals', None)  # Full persistent heap, repeated each turn.
                    block['result'].pop('rlm_calls', None)  # Already in model records.
        return {'trajectory': trajectory, 'self_check': self.self_check()}

    def dispatch(self, method, args, kwargs):
        try:
            return self._dispatch(method, args, kwargs)
        except BudgetExceeded:
            self.status['call_limit' if self.budget.count >= self.budget.limit else 'timeout'] = True
            raise

    def _dispatch(self, method, args, kwargs):
        self.research_ctx.check_cancelled()
        if method == 'complete':
            purpose = kwargs.get('purpose')
            if purpose not in {'root', 'sub'} or len(args) != 1 or not isinstance(args[0], str):
                raise ValueError('Worker may request only root/sub completions')
            model = self.ctx.config.models.root if purpose == 'root' else self.ctx.config.models.sub
            if 'model' in kwargs and kwargs['model'] != model:
                raise ValueError('Worker must use the configured model for its role')
            with self.ctx.trace.span('RLM ' + purpose, 'model', model=model) as details:
                prompt = args[0]
                if purpose == 'root':
                    with self.lifecycle, self.turn_lock:
                        self.research_ctx.check_cancelled()
                        self.apply_refinement()
                        self.turns += 1
                        if self.turns > self.ctx.config.rlm.max_iterations:
                            self.status['iteration_limit'] = True
                        prompt += '\nCURRENT RELEVANT HARNESS ENTRIES\n' + json.dumps(self.retrieve(), ensure_ascii=False)
                text = self.backend.complete(prompt, purpose=purpose, model=model)
                details.update(response_chars=len(text), usage=self.backend.last_usage)
            with self.lifecycle:
                self.research_ctx.check_cancelled()
                append_json(self.ctx.path / 'trajectory.jsonl', {'type': 'model', 'purpose': purpose,
                            'model': model, 'prompt': prompt, 'response': text})
            return {'text': text, 'usage': self.backend.last_usage}
        if method.startswith('tools.'):
            name = method.removeprefix('tools.')
            functions = {name: value['tool'] for name, value in self.tools.injected().items()}
            if name not in functions:
                raise ValueError('Unknown research tool')
            result = functions[name](*args, **kwargs)
            with self.lifecycle:
                self.research_ctx.check_cancelled()
                append_json(self.ctx.path / 'trajectory.jsonl', {'type': 'tool', 'tool': name,
                            'args': args, 'kwargs': kwargs, 'result': result})
            return result
        with self.lifecycle:
            self.research_ctx.check_cancelled()
            return self._state_dispatch(method, args, kwargs)

    def _state_dispatch(self, method, args, kwargs):
        if method.startswith('harness.'):
            name = method.removeprefix('harness.')
            if name not in {'create', 'read', 'get', 'update', 'delete', 'list', 'search'}:
                raise ValueError('Unknown harness operation')
            if name in {'create', 'update', 'delete'}:
                if not self.learning:
                    raise ValueError('Harness writes disabled for no-learning comparison')
                if set(kwargs) - {'id', 'module', 'trigger', 'evidence'}:
                    raise ValueError('Unsupported harness edit fields')
                kwargs['evidence'] = [self.run_id]
                kwargs.setdefault('trigger', 'agent mid-task edit')
            with self.ctx.trace.span('Harness', name, args=args, kwargs=kwargs) as details:
                if self.ctx.trace.enabled:
                    details['head_before'] = self.harness.head
                result = getattr(self.harness, name)(*args, **kwargs)
                if self.ctx.trace.enabled:
                    details.update(head_after=self.harness.head, result=result)
            if name == 'delete' and result is False:
                self.refiner.audit('skipped_delete', reason='entry_missing', args=args, kwargs=kwargs)
            if name in {'read', 'get', 'list', 'search'} and result:
                self.harness.record_usage(result if isinstance(result, list) else [result], self.run_id)
            return result
        if method == 'refine.run':
            if len(args) > 1 or set(kwargs) - {'focus'}:
                raise ValueError('Refinement accepts only focus')
            return self.refiner.run(*args, **kwargs)
        if method == 'refine.rollback':
            if not self.learning or len(args) != 1 or kwargs or not isinstance(args[0], str) or not args[0]:
                raise ValueError('Rollback requires an id and enabled learning')
            with self.turn_lock:
                self.rollbacks.append({'id': args[0], 'operation_id': 'refine_' + uuid4().hex})
                self.checkpoint()
            return {'scheduled': True}
        if method == 'trace':
            if len(args) != 2 or args[0] not in {'RLM', 'RLM iteration', 'REPL'}:
                raise ValueError('Invalid worker trace event')
            self.ctx.trace.emit(*args, **kwargs)
            return True
        if method == 'iteration':
            if len(args) != 1 or kwargs:
                raise ValueError('Expected one trajectory event')
            append_json(self.ctx.path / 'trajectory.jsonl', {'type': 'worker_iteration', 'event': args[0]})
            return True
        raise ValueError('Unknown host operation')

    def finish(self):
        self.close_worker()
        if self.fatal:
            raise RuntimeError(self.fatal)
        if self.finish_phase == 'complete':
            return self.ctx.load('self_check.json')
        report = self.self_check()
        self.refiner.resume()
        if self.finish_phase == 'pending':
            self.harness.record_outcome(self.run_id, {k: report[k] for k in ('ok', 'issues', 'signals')})
            self.apply_refinement(wait=True)
            while self.refiner.pending is not None:
                self.apply_refinement(wait=True)
            self.finish_phase = 'automatic'
            self.checkpoint()
        self.refiner.run(request_id=self.automatic_id)
        while self.refiner.pending is not None:
            self.apply_refinement(wait=True)
        self.finish_phase = 'complete'
        self.checkpoint()
        self.refiner.close()
        return report
