"""Codex clients and project-owned RLM/LocalREPL subclasses; upstream is unchanged."""
import builtins
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import sys
import json
import threading
import time
from types import ModuleType
from uuid import uuid4
from rlm import RLM
from rlm.clients.base_lm import BaseLM
from rlm.core.comms_utils import LMRequest, LMResponse, send_lm_request, send_lm_request_batched
from rlm.core.lm_handler import LMHandler
from rlm.core.types import ModelUsageSummary, UsageSummary, RLMChatCompletion, REPLResult
from rlm.environments.local_repl import LocalREPL


RESEARCH_SYSTEM_PROMPT = '''You coordinate research through a persistent Python REPL.
The full task instructions and output contract are in `context`. Inspect those instructions
before acting. Write Python in ```repl``` blocks; variables persist between turns.
Keep fetched text and intermediate tables in REPL variables. For records consumed by Python,
use llm_query_json(prompt, schema) or llm_query_json_batched(prompts, schema), with an explicit
JSON Schema for nested field types. They return validated Python values; JSON parsing alone
does not validate types. Use llm_query(prompt) or llm_query_batched(prompts) for prose review.
For model-query APIs, prompt must be a string and batched prompts must be a list of strings.
Build that text from the relevant variables: serialize dictionaries or lists with
json.dumps(evidence, ensure_ascii=False), then combine it with the task instruction.
The schema is a separate dictionary argument, not a prompt. These sub-models only see the text you supply and have
no independent tools. Group related evidence and rows into coherent extraction calls. Select
simple URL fields directly from structured search results when no semantic judgment is needed.
Inspect budget() before costly batches and plan capacity for the remaining research and checks.
Validate results before mutating accumulated records. If a block fails, inspect and reuse its
already completed tool results instead of repeating successful searches or fetches.
Use rlm_query(prompt) or rlm_query_batched(prompts) for a subtask needing its own iterative
REPL; give the child the evidence and a precise task, then use its result in Python.
Use programmatic checks for structure, keys, missing fields, quote membership and coverage.
Print counts, variable shapes, unresolved questions, check failures, or a focused diagnostic
needed to decide the next action. Avoid printing whole pages, search-result collections,
extraction payloads or candidate tables merely to inspect them: stdout accumulates in your
own conversation. Ask a sub-model to review those variables and print its concise findings.
This does not replace evidence checks: inspect and resolve reported gaps before submitting.
Use full Python and the supplied research tools; never invent sources or quotations.
The REPL exposes SHOW_VARS() and an `answer` dictionary. Assemble and validate the final
output in Python, set answer["content"] to its serialized content, then set answer["ready"]
to True. Submission returns that content directly; a full-table print is unnecessary.
{custom_tools_section}
'''


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


class CodexREPL(LocalREPL):
    """Preserve completed Python work and surface transport failures as errors."""
    def __init__(self, *args, lm_timeout, **kwargs):
        self.lm_timeout = lm_timeout
        super().__init__(*args, **kwargs)

    def execute_code(self, code):
        # The pinned implementation commits bindings only after a successful
        # block. Keep its capture/scaffold/result contract, including errors,
        # but retain completed assignments when a later statement fails.
        start = time.perf_counter()
        self._pending_llm_calls = []
        with self._capture_output() as (stdout_buf, stderr_buf), self._temp_cwd():
            combined = {**self.globals, **self.locals}
            completed = False
            try:
                try:
                    exec(code, combined, combined)
                    completed = True
                finally:
                    captured_answer = self._last_final_answer
                    for key, value in combined.items():
                        if key not in self.globals and not key.startswith('_'):
                            self.locals[key] = value
                    self._restore_scaffold()
                    if not completed:
                        # Restoration must not submit a plain answer dict from
                        # a failed block; retain only an existing callback capture.
                        self._last_final_answer = captured_answer
                stderr = stderr_buf.getvalue()
            except Exception as exc:
                stderr = stderr_buf.getvalue() + f'\n{type(exc).__name__}: {exc}'
            stdout = stdout_buf.getvalue()
        final_answer = self._last_final_answer
        self._last_final_answer = None
        return REPLResult(stdout=stdout, stderr=stderr, locals=self.locals.copy(),
            execution_time=time.perf_counter() - start,
            rlm_calls=self._pending_llm_calls.copy(), final_answer=final_answer)

    def _responses(self, responses):
        errors = []
        for index, response in enumerate(responses):
            if response.success:
                self._pending_llm_calls.append(response.chat_completion)
            else:
                errors.append(f'sub-call {index}: {response.error}')
        if errors:
            raise RuntimeError('; '.join(errors))
        return [response.chat_completion.response for response in responses]

    def _llm_query(self, prompt, model=None):
        response = send_lm_request(self.lm_handler_address,
                                   LMRequest(prompt=prompt, model=model, depth=self.depth),
                                   timeout=self.lm_timeout)
        return self._responses([response])[0]

    def _llm_query_batched(self, prompts, model=None):
        responses = send_lm_request_batched(self.lm_handler_address, prompts, model=model,
                                           depth=self.depth, timeout=self.lm_timeout)
        return self._responses(responses)

    def _rlm_query(self, prompt, model=None):
        if self.subcall_fn is None:  # The configured depth limit is a plain LM base case.
            return self._llm_query(prompt, model)
        completion = self.subcall_fn(prompt, model)
        self._pending_llm_calls.append(completion)
        return completion.response

    def _rlm_query_batched(self, prompts, model=None):
        if self.subcall_fn is None:
            return self._llm_query_batched(prompts, model)
        def call(prompt):
            try:
                return LMResponse.success_response(self.subcall_fn(prompt, model))
            except Exception as exc:
                return LMResponse.error_response(f'{type(exc).__name__}: {exc}')
        with ThreadPoolExecutor(max_workers=self.max_concurrent_subcalls) as pool:
            return self._responses(list(pool.map(call, prompts)))


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
        # The stock orchestrator addendum requires printing the candidate answer.
        # Research validates/submits its Python value without copying it to stdout.
        kwargs.setdefault('custom_system_prompt', RESEARCH_SYSTEM_PROMPT)
        kwargs.setdefault('orchestrator', False)
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
        handler = CodexHandler(root, other_backend_client=sub,
                               batch_max_concurrent=self.max_concurrent_subcalls)
        handler.register_client(sub.model_name, sub)
        handler.start()
        env = None
        try:
            env = CodexREPL(lm_handler_address=(handler.host, handler.port), context_payload=prompt,
                lm_timeout=self.max_timeout,
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
