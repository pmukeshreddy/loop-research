"""Subscription-only Codex adapter and cached, budgeted model-call boundary.

No API clients, tokens, or authentication-file reads. Codex owns OAuth.
"""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .prompts import PROMPTS, PROMPT_VERSION
from .storage import BudgetExceeded, SubscriptionLimit, UncertainCall, digest, dump


@dataclass
class ProviderResult:
    data: dict
    tokens: int
    searches: int
    metadata: dict


def strict_schema(schema):
    schema = json.loads(json.dumps(schema))
    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)
    visit(schema)
    return schema


class CodexProvider:
    DISABLED = ("shell_tool", "unified_exec", "apps", "plugins", "multi_agent", "browser_use",
                "browser_use_external", "computer_use", "image_generation", "view_image", "hooks",
                "memories", "skill_search", "code_mode", "in_app_browser",
                "in_app_chat", "in_app_local_automation", "unbounded_connection_retries")

    def __init__(self, config):
        self.settings = config
        self.config = config.model_dump(mode="json")

    @staticmethod
    def environment(environ=None):
        source = os.environ if environ is None else environ
        # Keep OS/keychain discovery. Do not mutate HOME/CODEX_HOME or inspect credentials.
        return {k: v for k, v in source.items() if k not in
                ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID")}

    def command(self, cwd, schema, output, web):
        cmd = [self.settings.executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
               "--skip-git-repo-check", "--sandbox", "read-only", "-C", str(cwd),
               "--enable", "skip_host_skill_discovery"]
        for feature in self.DISABLED:
            cmd += ["--disable", feature]
        for setting in ('forced_login_method="chatgpt"', 'model_provider="openai"', 'approval_policy="never"',
                        f'web_search="{"live" if web else "disabled"}"', 'project_doc_max_bytes=0',
                        'hide_agent_reasoning=true', f'model_reasoning_effort="{self.settings.reasoning_effort}"'):
            cmd += ["-c", setting]
        if self.settings.model:
            cmd += ["--model", self.settings.model]
        return cmd + ["--output-schema", str(schema), "--output-last-message", str(output), "--json", "-"]

    def preflight(self):
        version = subprocess.run([self.settings.executable, "--version"], capture_output=True, text=True, timeout=10,
                                 env=self.environment(), check=True).stdout.strip()
        login = subprocess.run([self.settings.executable, "login", "status"], capture_output=True, text=True,
                               timeout=10, env=self.environment())
        if login.returncode or "ChatGPT" not in login.stdout + login.stderr:
            raise ValueError("Codex ChatGPT sign-in required: run `codex login`; API-key auth is not accepted")
        help_text = subprocess.run([self.settings.executable, "exec", "--help"], capture_output=True, text=True,
                                   timeout=10, env=self.environment(), check=True).stdout
        if any(flag not in help_text for flag in ("--ignore-user-config", "--ephemeral", "--output-schema")):
            raise ValueError("Codex CLI lacks required isolation/structured-output flags; update official CLI")
        return {"version": version, "authentication": "ChatGPT", "additional_paid_budget_usd": 0}

    def invoke(self, prompt, payload, schema, web=False):
        with tempfile.TemporaryDirectory(prefix="webshaper-role-") as tmp:
            root = Path(tmp)
            schema_path, output = root / "schema.json", root / "response.json"
            schema_path.write_text(dump(strict_schema(schema)))
            text = prompt + f"\nMaximum web-search actions: {self.settings.max_searches_per_call if web else 0}.\nINPUT JSON:\n" + dump(payload)
            events = []
            search_ids = set()
            usage = {}
            event_queue = queue.Queue()
            start = time.monotonic()
            with tempfile.TemporaryFile(mode="w+") as errors:
                process = subprocess.Popen(self.command(root, schema_path, output, web), stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=errors, text=True, env=self.environment())
                def reader():
                    for line in process.stdout:
                        event_queue.put(line)
                    event_queue.put(None)
                thread = threading.Thread(target=reader, daemon=True)
                thread.start()
                try:
                    process.stdin.write(text)
                    process.stdin.close()
                    while True:
                        remaining = self.settings.timeout_seconds - (time.monotonic() - start)
                        if remaining <= 0:
                            raise UncertainCall("Codex session timed out; outcome and usage may be incomplete")
                        try:
                            line = event_queue.get(timeout=min(1, remaining))
                        except queue.Empty:
                            continue
                        if line is None:
                            break
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        item = event.get("item", {})
                        kind = item.get("type")
                        if kind == "web_search":
                            search_ids.add(item["id"])
                            if not web or len(search_ids) > self.settings.max_searches_per_call:
                                raise BudgetExceeded("Codex exceeded the allowed search actions; session stopped")
                        elif kind in ("command_execution", "mcp_tool_call", "file_change", "collab_tool_call"):
                            raise UncertainCall("unexpected tool invocation in isolated Codex role")
                        if event.get("type") == "turn.completed":
                            usage = event.get("usage", {})
                        if event.get("type") in ("error", "turn.failed"):
                            events.append(event)
                        if kind == "error":
                            events.append(item)
                    process.wait(timeout=5)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                    thread.join(timeout=2)
                    process.stdout.close()
                errors.seek(0)
                failure = errors.read() + dump(events)
                if process.returncode or not output.exists():
                    if any(s in failure.lower() for s in ("usage limit", "rate limit", "limit reached", "quota exceeded", "insufficient_quota")):
                        raise SubscriptionLimit("Codex subscription limit reached; checkpoint saved")
                    # Never put raw stderr (which can contain environment details) in the journal.
                    raise UncertainCall(f"Codex failed with exit {process.returncode}; no automatic retry")
            if not usage:
                raise UncertainCall("Codex returned no token-usage record")
            return ProviderResult(json.loads(output.read_text()), usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                                  len(search_ids), {"usage": usage, "web_search_actions": len(search_ids),
                                                    "session": "fresh_ephemeral", "authentication": "ChatGPT"})


class ModelGateway:
    def __init__(self, journal, providers, token_reservation=None):
        self.journal, self.providers = journal, providers
        self.token_reservation = token_reservation
        self.halted = threading.Event()

    def call(self, role, operation, payload, output_type, call_id, *, web=False):
        if self.halted.is_set():
            raise SubscriptionLimit("run requested a pause; no further model calls were dispatched")
        provider = self.providers[role]
        prompt = PROMPTS[operation]
        schema = output_type.model_json_schema()
        key = digest([role, operation, call_id, payload, provider.config, prompt, schema, PROMPT_VERSION, web])
        reserve_tokens = self.token_reservation or provider.config.get("token_reservation", 100_000)
        search_cap = provider.config.get("max_searches_per_call", 3) if web else 0
        cached = self.journal.reserve(key, role + ":" + operation, 0, reserve_tokens, search_cap)
        if cached is not None:
            return output_type.model_validate(cached["data"])
        started = time.monotonic()
        completed = False
        try:
            result = provider.invoke(prompt, payload, schema, web=web)
            # Record completed calls even when schema validation fails: they consumed usage.
            metadata = {**result.metadata, "call_id": call_id, "role": role, "operation": operation}
            self.journal.complete(key, {"data": result.data, "metadata": metadata}, 0,
                                  result.tokens, result.searches, time.monotonic() - started)
            completed = True
            return output_type.model_validate(result.data)
        except SubscriptionLimit:
            self.halted.set()
            self.journal.fail(key, "limited", "subscription_limit", time.monotonic() - started)
            raise
        except (UncertainCall, BudgetExceeded, KeyboardInterrupt):
            self.halted.set()
            self.journal.fail(key, "uncertain", "interrupted_or_unknown", time.monotonic() - started)
            raise
        except Exception as error:
            # Completed malformed replies remain cached; transport failures stay uncertain.
            if not completed:
                self.halted.set()
                self.journal.fail(key, "uncertain", "provider_failure", time.monotonic() - started)
                raise UncertainCall("provider outcome unknown: " + type(error).__name__) from error
            raise
