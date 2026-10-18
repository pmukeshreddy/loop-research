"""Trusted research services; no graders or answer stores are imported here."""
import json
import threading
from concurrent.futures import Future
from dataclasses import replace

from .archive import append_json, read_jsonl, count_codex_calls
from .codex_backend import CodexBackend, CallBudget, CodexError
from .refine import Refiner
from .repl_tools import ResearchTools
from .selfcheck import check


class Session:
    def __init__(self, task, ctx, harness, *, learning=True, backend=None):
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
        self.rollbacks = []
        self.refiner = Refiner(harness, ctx, CodexBackend(ctx), self.observation, enabled=learning)
        if ctx.cancellation is not None:
            ctx.cancellation.add_done_callback(lambda _: self.close_worker())

    def close_worker(self):
        with self.lifecycle, self.tools.lock:
            self.research_ctx.cancellation.cancel()

    def apply_refinement(self, wait=False):
        try:
            commits = self.refiner.boundary(wait=wait)
        except (ValueError, CodexError) as exc:
            append_json(self.ctx.path / 'refinements.jsonl', {'error': str(exc), 'status': 'failed'})
            commits = []
        while self.rollbacks:
            id = self.rollbacks.pop(0)
            try:
                self.refiner.rollback(id)
            except ValueError as exc:
                append_json(self.ctx.path / 'refinements.jsonl', {'error': str(exc), 'rollback': id, 'status': 'failed'})
        return commits

    def retrieve(self):
        entries = self.harness.search(self.task.question + ' ' + json.dumps(self.task.spec, ensure_ascii=False),
                                      limit=self.ctx.config.harness.retrieval_limit)
        self.harness.record_usage(entries, self.run_id)
        return entries

    def self_check(self):
        report = check(self.task, self.output, self.tools.snapshot(), self.status)
        self.ctx.save('self_check.json', report)
        return report

    def observation(self):
        return {'trajectory': read_jsonl(self.ctx.path / 'trajectory.jsonl'), 'self_check': self.self_check()}

    def dispatch(self, method, args, kwargs):
        self.research_ctx.check_cancelled()
        if method == 'complete':
            purpose = kwargs.get('purpose')
            if purpose not in {'root', 'sub'} or len(args) != 1 or not isinstance(args[0], str):
                raise ValueError('Worker may request only root/sub completions')
            prompt = args[0]
            if purpose == 'root':
                with self.lifecycle, self.turn_lock:
                    self.research_ctx.check_cancelled()
                    self.apply_refinement()
                    self.turns += 1
                    if self.turns > self.ctx.config.rlm.max_iterations:
                        self.status['iteration_limit'] = True
                    prompt += '\nCURRENT RELEVANT HARNESS ENTRIES\n' + json.dumps(self.retrieve(), ensure_ascii=False)
            model = self.ctx.config.models.root if purpose == 'root' else self.ctx.config.models.sub
            text = self.backend.complete(prompt, purpose=purpose, model=model)
            with self.lifecycle:
                self.research_ctx.check_cancelled()
                append_json(self.ctx.path / 'trajectory.jsonl', {'type': 'model', 'purpose': purpose,
                            'prompt': prompt, 'response': text})
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
            result = getattr(self.harness, name)(*args, **kwargs)
            if name in {'read', 'get', 'list', 'search'} and result:
                self.harness.record_usage(result if isinstance(result, list) else [result], self.run_id)
            return result
        if method == 'refine.run':
            return self.refiner.run(*args, **kwargs)
        if method == 'refine.rollback':
            if not self.learning or len(args) != 1 or kwargs or not isinstance(args[0], str) or not args[0]:
                raise ValueError('Rollback requires an id and enabled learning')
            with self.turn_lock:
                self.rollbacks.append(args[0])
            return {'scheduled': True}
        if method == 'iteration':
            if len(args) != 1 or kwargs:
                raise ValueError('Expected one trajectory event')
            append_json(self.ctx.path / 'trajectory.jsonl', {'type': 'worker_iteration', 'event': args[0]})
            return True
        raise ValueError('Unknown host operation')

    def finish(self):
        self.close_worker()
        report = self.self_check()
        self.harness.record_outcome(self.run_id, {k: report[k] for k in ('ok', 'issues')})
        self.apply_refinement(wait=True)
        self.refiner.run()
        while self.refiner.pending is not None:
            self.apply_refinement(wait=True)
        self.refiner.close()
        return report
