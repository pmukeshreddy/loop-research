"""Codex clients and project-owned RLM/LocalREPL subclasses; upstream is unchanged."""
import builtins
import asyncio
from contextlib import contextmanager
import sys
import json
import threading
import time
from types import ModuleType
from uuid import uuid4
from rlm import RLM
from rlm.clients.base_lm import BaseLM
from rlm.core.lm_handler import LMHandler
from rlm.core.types import ModelUsageSummary, UsageSummary, RLMChatCompletion
from rlm.environments.local_repl import LocalREPL


def transcript(prompt):
    if isinstance(prompt, str):
        return prompt
    messages = prompt if isinstance(prompt, list) else [prompt]
    return "\n\n".join(f"<{m.get('role', 'user')}>\n" +
        (m.get("content", "") if isinstance(m.get("content", ""), str) else json.dumps(m["content"], ensure_ascii=False)) +
        f"\n</{m.get('role', 'user')}>" for m in messages)


class CodexLM(BaseLM):
    def __init__(self, backend, model, purpose="root"):
        if not isinstance(model, str) or not model.strip():
            raise ValueError("An explicit model name is required")
        super().__init__(model_name=model)
        self.transport, self.model, self.purpose = backend, model, purpose
        self.lock = threading.Lock()
        self.total = ModelUsageSummary(0, 0, 0)
        self.last = ModelUsageSummary(0, 0, 0)

    def completion(self, prompt):
        result = self.transport.complete(transcript(prompt), purpose=self.purpose, model=self.model)
        usage = self.transport.last_usage
        # RLM requires integers. Unavailable usage is flagged in the authoritative call log.
        last = ModelUsageSummary(1, (usage or {}).get("input_tokens", 0), (usage or {}).get("output_tokens", 0))
        with self.lock:
            self.last = last
            self.total = ModelUsageSummary(self.total.total_calls + 1,
                self.total.total_input_tokens + last.total_input_tokens,
                self.total.total_output_tokens + last.total_output_tokens)
        return result

    async def acompletion(self, prompt):
        return await asyncio.to_thread(self.completion, prompt)

    def get_last_usage(self):
        with self.lock:
            return self.last

    def get_usage_summary(self):
        with self.lock:
            return UsageSummary({self.model_name: self.total})


class CodexHandler(LMHandler):
    def get_client(self, model=None, depth=0):
        client = self.other_backend_client if depth > 0 else self.default_client
        if client is None:
            raise ValueError("A configured sub model is required for nested calls")
        if model is not None and model != client.model_name:
            raise ValueError(f"This call requires configured model {client.model_name!r}")
        return client

    def get_usage_summary(self):
        # Upstream overwrites usage when root and sub clients name the same model.
        merged = {}
        clients = {id(client): client for client in
                   [self.default_client, self.other_backend_client, *self.clients.values()] if client is not None}
        for client in clients.values():
            for model, usage in client.get_usage_summary().model_usage_summaries.items():
                previous = merged.get(model, ModelUsageSummary(0, 0, 0))
                merged[model] = ModelUsageSummary(previous.total_calls + usage.total_calls,
                    previous.total_input_tokens + usage.total_input_tokens,
                    previous.total_output_tokens + usage.total_output_tokens)
        return UsageSummary(merged)


class CodexRLM(RLM):
    def __init__(self, transport, *, root_model, sub_model, skill_modules=(), trace_enabled=False, parent_rlm_id=None, **kwargs):
        if any(not isinstance(model, str) or not model.strip() for model in (root_model, sub_model)):
            raise ValueError("Explicit root and sub model names are required")
        self.transport, self.root_model, self.sub_model = transport, root_model, sub_model
        self.skill_modules = skill_modules
        self.trace_enabled = trace_enabled
        self.trace_iteration = 0
        self.rlm_id = uuid4().hex if trace_enabled else None
        self.parent_rlm_id = parent_rlm_id
        self.trace_answer_ready = False
        super().__init__(backend="codex", backend_kwargs={"model_name": root_model},
                         environment="local", **kwargs)

    @contextmanager
    def _observe(self, component, event, **details):
        if not self.trace_enabled:
            yield details
            return
        details.update(rlm_id=self.rlm_id, parent_rlm_id=self.parent_rlm_id)
        parent = ('RLM sub' if self.depth else 'RLM root') if component == 'REPL' else ('REPL' if self.depth else 'Worker')
        self.transport.call('trace', component, event + '.start', parent=parent, depth=self.depth, **details)
        start = time.monotonic()
        try:
            yield details
        except BaseException as exc:
            details['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            self.transport.call('trace', component, event + '.end', duration_s=time.monotonic() - start,
                                depth=self.depth, **details)

    def completion(self, prompt, root_prompt=None):
        self.trace_iteration = 0
        self.trace_answer_ready = False
        with self._observe('RLM', 'completion') as details:
            try:
                result = super().completion(prompt, root_prompt=root_prompt)
                details['termination'] = ('answer_ready' if self.trace_answer_ready else
                    'direct_lm' if self.depth >= self.max_depth else 'iteration_limit')
                return result
            except BaseException:
                details['termination'] = 'error'
                raise
            finally:
                details['iterations'] = self.trace_iteration

    def _completion_turn(self, prompt, lm_handler, environment):
        self.trace_iteration += 1
        with self._observe('RLM iteration', 'iteration', iteration=self.trace_iteration):
            result = super()._completion_turn(prompt, lm_handler, environment)
            self.trace_answer_ready = any(block.result.final_answer is not None for block in result.code_blocks)
            return result

    @contextmanager
    def _spawn_completion_context(self, prompt):
        root = CodexLM(self.transport, self.root_model, "root" if self.depth == 0 else "sub")
        sub = CodexLM(self.transport, self.sub_model, "sub")
        handler = CodexHandler(root, other_backend_client=sub)
        handler.register_client(sub.model_name, sub)
        handler.start()
        env = None
        try:
            env = LocalREPL(lm_handler_address=(handler.host, handler.port), context_payload=prompt,
                depth=self.depth + 1, subcall_fn=self._subcall if self.max_depth > 1 else None,
                custom_tools=self.custom_tools, custom_sub_tools=self.custom_sub_tools,
                max_concurrent_subcalls=self.max_concurrent_subcalls)
            if self.trace_enabled:
                execute = env.execute_code
                def observed_code(code):
                    with self._observe('REPL', 'code', first_lines='\n'.join(code.splitlines()[:8])) as details:
                        result = execute(code)
                        details.update(stdout=result.stdout[:1000], error=result.stderr or None,
                                       answer_ready=result.final_answer is not None)
                        return result
                env.execute_code = observed_code
            env.globals['__builtins__'] = vars(builtins).copy()
            loaded = {}
            for entry in self.skill_modules:
                if entry.get('module'):
                    name = 'skill_' + entry['id']
                    module = ModuleType(name)
                    module.__dict__.update({k: v for k, v in env.globals.items() if k != '__name__'})
                    sys.modules[name] = module
                    exec(compile(entry['module'], name + '.py', 'exec'), module.__dict__)
                    loaded[entry['id']] = module
                    env.globals[name] = module
            env.globals['loaded_skills'] = loaded
            yield handler, env
        finally:
            handler.stop()
            if env is not None:
                env.cleanup()

    def _fallback_answer(self, message):
        return CodexLM(self.transport, self.sub_model if self.depth else self.root_model,
                       "sub" if self.depth else "root").completion(message)

    def _subcall(self, prompt, model=None):
        if model is not None and model != self.sub_model:
            raise ValueError(f"Recursive calls require configured sub model {self.sub_model!r}")
        next_depth = self.depth + 1
        chosen = self.sub_model
        if next_depth >= self.max_depth:
            client = CodexLM(self.transport, chosen, "sub")
            start = time.monotonic()
            text = client.completion(prompt)
            return RLMChatCompletion(client.model_name, prompt, text, client.get_usage_summary(), time.monotonic() - start)
        child = CodexRLM(self.transport, root_model=chosen, sub_model=self.sub_model,
            depth=next_depth, max_depth=self.max_depth, max_iterations=self.max_iterations,
            max_timeout=self.max_timeout, custom_system_prompt=self.system_prompt,
            custom_tools=self.custom_sub_tools, custom_sub_tools=self.custom_sub_tools,
            logger=self.logger, max_concurrent_subcalls=self.max_concurrent_subcalls, trace_enabled=self.trace_enabled,
            parent_rlm_id=self.rlm_id)
        return child.completion(prompt)
