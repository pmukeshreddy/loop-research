"""Codex clients and project-owned RLM/LocalREPL subclasses; upstream is unchanged."""
import ast
import asyncio
from contextlib import contextmanager
import importlib
import json
import threading
import time
from types import ModuleType
from rlm import RLM
from rlm.clients.base_lm import BaseLM
from rlm.core.lm_handler import LMHandler
from rlm.core.types import ModelUsageSummary, UsageSummary, RLMChatCompletion, REPLResult
from rlm.environments.local_repl import LocalREPL


def transcript(prompt):
    if isinstance(prompt, str):
        return prompt
    messages = prompt if isinstance(prompt, list) else [prompt]
    return "\n\n".join(f"<{m.get('role', 'user')}>\n" +
        (m.get("content", "") if isinstance(m.get("content", ""), str) else json.dumps(m["content"], ensure_ascii=False)) +
        f"\n</{m.get('role', 'user')}>" for m in messages)


class CodexLM(BaseLM):
    def __init__(self, backend, model=None, purpose="root"):
        super().__init__(model_name=model or f"codex-default-{purpose}")
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


_ALLOWED_MODULES = {"json", "re", "math", "statistics", "collections", "itertools", "datetime", "decimal"}
_BLOCKED = {"open", "eval", "exec", "compile", "getattr", "setattr", "delattr", "hasattr", "vars", "dir",
            "globals", "locals", "input", "help", "breakpoint", "type", "object", "super", "memoryview"}


def validate_code(code):
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.Global, ast.Nonlocal)):
            raise ValueError("Classes/global namespace mutation are unavailable")
        if isinstance(node, ast.Name) and (node.id.startswith('_') or node.id in _BLOCKED):
            raise ValueError(f"Name unavailable: {node.id}")
        if isinstance(node, ast.Attribute) and (node.attr.startswith('_') or node.attr in {"format", "format_map"}):
            raise ValueError("Private/introspection attributes and format traversal are unavailable; use f-strings")
        if isinstance(node, ast.Import) and any(x.name not in _ALLOWED_MODULES for x in node.names):
            raise ValueError("Only documented computation modules may be imported")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in _ALLOWED_MODULES or any(x.name.startswith('_') or x.name == '*' for x in node.names):
                raise ValueError("Import unavailable")


def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in _ALLOWED_MODULES or any(x.startswith('_') for x in (fromlist or ())):
        raise ImportError("Only documented computation modules are available")
    module = importlib.import_module(name)
    # Standard modules expose implementation dependencies (json.codecs.open,
    # re.enum.sys) that bypass a name-only import allowlist.
    exports = getattr(module, "__all__", [key for key in vars(module) if not key.startswith('_')])
    public = ModuleType(name)
    for key in exports:
        value = getattr(module, key)
        if not key.startswith('_') and not isinstance(value, ModuleType):
            setattr(public, key, value)
    return public


class ResearchREPL(LocalREPL):
    """A restricted computation interface; not a general-purpose OS sandbox."""
    def setup(self):
        super().setup()
        builtins = self.globals["__builtins__"]
        for name in _BLOCKED:
            builtins.pop(name, None)
        builtins["__import__"] = safe_import

    def execute_code(self, code):
        try:
            validate_code(code)
        except (ValueError, SyntaxError) as exc:
            return REPLResult(stdout="", stderr=str(exc), locals={}, execution_time=0, rlm_calls=[])
        return super().execute_code(code)


class CodexRLM(RLM):
    def __init__(self, transport, *, root_model=None, sub_model=None, **kwargs):
        self.transport, self.root_model, self.sub_model = transport, root_model, sub_model
        super().__init__(backend="codex", backend_kwargs={"model_name": root_model or "codex-default-root"},
                         environment="local", **kwargs)

    @contextmanager
    def _spawn_completion_context(self, prompt):
        root = CodexLM(self.transport, self.root_model, "root" if self.depth == 0 else "sub")
        sub = CodexLM(self.transport, self.sub_model, "sub")
        handler = CodexHandler(root, other_backend_client=sub)
        handler.register_client(sub.model_name, sub)
        handler.start()
        env = None
        try:
            env = ResearchREPL(lm_handler_address=(handler.host, handler.port), context_payload=prompt,
                depth=self.depth + 1, subcall_fn=self._subcall if self.max_depth > 1 else None,
                custom_tools=self.custom_tools, custom_sub_tools=self.custom_sub_tools,
                max_concurrent_subcalls=self.max_concurrent_subcalls)
            yield handler, env
        finally:
            handler.stop()
            if env is not None:
                env.cleanup()

    def _fallback_answer(self, message):
        return CodexLM(self.transport, self.sub_model if self.depth else self.root_model,
                       "sub" if self.depth else "root").completion(message)

    def _subcall(self, prompt, model=None):
        next_depth = self.depth + 1
        chosen = model or self.sub_model
        if next_depth >= self.max_depth:
            client = CodexLM(self.transport, chosen, "sub")
            start = time.monotonic()
            text = client.completion(prompt)
            return RLMChatCompletion(client.model_name, prompt, text, client.get_usage_summary(), time.monotonic() - start)
        child = CodexRLM(self.transport, root_model=chosen, sub_model=self.sub_model,
            depth=next_depth, max_depth=self.max_depth, max_iterations=self.max_iterations,
            max_timeout=self.max_timeout, custom_system_prompt=self.system_prompt,
            custom_tools=self.custom_sub_tools, custom_sub_tools=self.custom_sub_tools,
            logger=self.logger, max_concurrent_subcalls=self.max_concurrent_subcalls)
        return child.completion(prompt)
