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
from urllib.parse import urlsplit

from .prompts import PROMPTS, PROMPT_VERSION
from .storage import BudgetExceeded, SubscriptionLimit, UncertainCall, digest, dump, now


@dataclass
class ProviderResult:
    data: dict
    tokens: int
    searches: int
    metadata: dict
    observation: dict | None = None


def empty_observation(web):
    return {"web_events": [], "visited_urls": [], "tokens": 0, "searches": 0,
            "latency_seconds": 0, "web_enabled": web, "usage": {}, "usage_known": False,
            "failures": [], "failure_code": None, "agent_messages": [], "output_text": ""}


def usable_web_actions(reserved_cap):
    """Leave one action as a stop margin; CLI events arrive after dispatch."""
    return max(1, reserved_cap - 1)


class _Trace:
    """Only CLI events establish tool activity; final model text is never evidence of it."""

    def __init__(self, web):
        self.observation = empty_observation(web)
        self.action_ids = set()
        self.started = time.monotonic()

    def consume(self, event):
        obs = self.observation
        item = event.get("item") or {}
        kind, event_type = item.get("type"), event.get("type")
        stamp = now()
        if kind == "web_search":
            action = item.get("action")
            obs["web_events"].append({"event_type": event_type, "id": item.get("id"),
                "status": item.get("status") or str(event_type).removeprefix("item."), "action": action,
                "timestamp": stamp, "raw_event": event})
            # Count once across started/updated/completed. Unknown actions consume budget too.
            if item.get("id") is None:
                raise UncertainCall("web event has no action id; action usage cannot be established")
            self.action_ids.add(item["id"])
            obs["searches"] = len(self.action_ids)
            if (event_type == "item.completed" and item.get("status", "completed") == "completed"
                    and isinstance(action, dict) and action.get("type") == "open_page"):
                url = action.get("url")
                if isinstance(url, str) and urlsplit(url).scheme in ("http", "https") and urlsplit(url).netloc:
                    if url not in obs["visited_urls"]:
                        obs["visited_urls"].append(url)
        if kind == "agent_message" and event_type == "item.completed":
            obs["agent_messages"].append(item.get("text", ""))
        if event_type == "turn.completed":
            usage = event.get("usage") or {}
            obs["usage"] = usage
            obs["usage_known"] = all(isinstance(usage.get(k), int) for k in ("input_tokens", "output_tokens"))
            if obs["usage_known"]:
                obs["tokens"] = usage["input_tokens"] + usage["output_tokens"]
        if event_type in ("error", "turn.failed") or kind == "error":
            obs["failures"].append({"timestamp": stamp, "raw_event": event})

    def finish(self):
        self.observation["latency_seconds"] = time.monotonic() - self.started
        return self.observation


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
                "in_app_chat", "in_app_local_automation", "unbounded_connection_retries",
                "shell_snapshot", "multi_agent_v2", "request_permissions_tool", "workspace_dependencies",
                "remote_plugin", "stable_environment_tools", "tool_suggest", "goals")

    def __init__(self, config):
        self.settings = config
        self.config = {**config.model_dump(mode="json"), "provider_policy_version": 2}

    @staticmethod
    def environment(environ=None):
        source = os.environ if environ is None else environ
        # Keep OS/keychain discovery. Do not mutate HOME/CODEX_HOME or inspect credentials.
        return {k: v for k, v in source.items() if k not in
                ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID")}

    def command(self, cwd, schema, output, web):
        cmd = [self.settings.executable, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
               "--skip-git-repo-check", "--strict-config", "-C", str(cwd),
               "--enable", "skip_host_skill_discovery"]
        for feature in self.DISABLED:
            cmd += ["--disable", feature]
        for setting in ('forced_login_method="chatgpt"', 'model_provider="openai"', 'approval_policy="never"',
                        f'web_search="{"live" if web else "disabled"}"', 'project_doc_max_bytes=0',
                        'hide_agent_reasoning=true', f'model_reasoning_effort="{self.settings.reasoning_effort}"',
                        'mcp_servers={}', 'default_permissions="webshaper-role"',
                        'permissions.webshaper-role={filesystem={":root"="deny",":minimal"="read",'
                        + json.dumps(str(Path(cwd).resolve())) + '="read"},network={enabled=false}}'):
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
        if any(flag not in help_text for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral",
                                                  "--output-schema", "--strict-config")):
            raise ValueError("Codex CLI lacks required isolation/structured-output flags; update official CLI")
        return {"version": version, "authentication": "ChatGPT", "additional_paid_budget_usd": 0}

    def invoke(self, prompt, payload, schema, web=False):
        trace = _Trace(web)
        try:
            return self._invoke(prompt, payload, schema, web, trace)
        except BaseException as error:
            observation = trace.finish()
            if not observation["failure_code"]:
                observation["failure_code"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "provider_failure"
            error.observation = observation
            raise

    def _invoke(self, prompt, payload, schema, web, trace):
        obs = trace.observation
        with tempfile.TemporaryDirectory(prefix="webshaper-role-") as tmp:
            root = Path(tmp)
            schema_path, output = root / "schema.json", root / "response.json"
            schema_path.write_text(dump(strict_schema(schema)))
            text = (prompt + "\nUse only the hosted web tool when enabled. No shell, filesystem, apps, MCP, "
                    "or delegation tools. Search, open-page and find-in-page each consume one web action."
                    f"\nMaximum web actions: {usable_web_actions(self.settings.max_searches_per_call) if web else 0}."
                    " Run web actions sequentially; do not batch parallel tool invocations.\nINPUT JSON:\n"
                    + dump(payload))
            event_queue = queue.Queue()
            with tempfile.TemporaryFile(mode="w+") as errors:
                obs["cli_command"] = self.command(root, schema_path, output, web)
                process = subprocess.Popen(obs["cli_command"], stdin=subprocess.PIPE,
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
                        remaining = self.settings.timeout_seconds - (time.monotonic() - trace.started)
                        if remaining <= 0:
                            obs["failure_code"] = "timeout"
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
                        if not isinstance(event, dict):
                            continue
                        trace.consume(event)
                        item = event.get("item") or {}
                        kind = item.get("type")
                        if kind == "web_search":
                            if not web or obs["searches"] >= self.settings.max_searches_per_call:
                                obs["failure_code"] = "web_action_budget"
                                raise BudgetExceeded("Codex reached the reserved web-action stop margin; session stopped")
                        elif kind in ("command_execution", "mcp_tool_call", "file_change", "collab_tool_call"):
                            obs["failure_code"] = "unexpected_tool"
                            obs["failures"].append({"timestamp": now(), "raw_event": event})
                            raise UncertainCall("unexpected tool invocation in isolated Codex role")
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
                    # Preserve events already emitted before cancellation, including
                    # final usage. The hosted service may have work in flight.
                    while not event_queue.empty():
                        queued = event_queue.get_nowait()
                        if queued is None:
                            continue
                        try:
                            event = json.loads(queued)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(event, dict):
                            trace.consume(event)
                    if output.exists():
                        obs["output_text"] = output.read_text()
                errors.seek(0)
                failure = (errors.read() + dump(obs["failures"])).lower()
                if output.exists():
                    obs["output_text"] = output.read_text()
                if process.returncode or not output.exists() or any(
                        e["raw_event"].get("type") == "turn.failed" for e in obs["failures"]):
                    if any(s in failure.lower() for s in ("usage limit", "rate limit", "limit reached", "quota exceeded", "insufficient_quota")):
                        obs["failure_code"] = "subscription_limit"
                        raise SubscriptionLimit("Codex subscription limit reached; checkpoint saved")
                    unavailable = ("unavailable", "not available", "not supported", "unsupported", "unknown")
                    obs["failure_code"] = ("capability_unavailable" if any(s in failure for s in unavailable)
                                           and any(s in failure for s in ("web", "tool", "feature", "permission"))
                                           else "provider_failure")
                    # Never put raw stderr (which can contain environment details) in the journal.
                    raise UncertainCall(f"Codex failed with exit {process.returncode}; no automatic retry")
            if not obs["usage_known"]:
                obs["failure_code"] = "missing_usage"
                raise UncertainCall("Codex returned no token-usage record")
            try:
                data = json.loads(obs["output_text"])
            except json.JSONDecodeError as error:
                obs["failure_code"] = "invalid_response"
                raise UncertainCall("Codex returned invalid JSON") from error
            return ProviderResult(data, obs["tokens"], obs["searches"],
                                  {"usage": obs["usage"], "web_search_actions": obs["searches"],
                                   "session": "fresh_ephemeral", "authentication": "ChatGPT"}, trace.finish())


class ModelGateway:
    def __init__(self, journal, providers, token_reservation=None):
        self.journal, self.providers = journal, providers
        self.token_reservation = token_reservation
        self.halted = threading.Event()

    def call(self, role, operation, payload, output_type, call_id, *, web=False):
        return self.call_observed(role, operation, payload, output_type, call_id, web=web)[0]

    def call_observed(self, role, operation, payload, output_type, call_id, *, web=False):
        if self.halted.is_set():
            error = SubscriptionLimit("run requested a pause; no further model calls were dispatched")
            error.observation = {**empty_observation(web), "call_id": call_id, "role": role,
                                 "operation": operation, "failure_code": "run_paused", "dispatched": False}
            raise error
        provider = self.providers[role]
        prompt = PROMPTS[operation]
        schema = output_type.model_json_schema()
        key = digest([role, operation, call_id, payload, provider.config, prompt, schema, PROMPT_VERSION, web])
        reserve_tokens = self.token_reservation or provider.config.get("token_reservation", 100_000)
        search_cap = provider.config.get("max_searches_per_call", 3) if web else 0
        context = {"cache_key": key, "call_id": call_id, "role": role, "operation": operation}
        try:
            cached = self.journal.reserve(key, role + ":" + operation, 0, reserve_tokens, search_cap)
        except (BudgetExceeded, SubscriptionLimit, UncertainCall) as error:
            observation = self.journal.record_value("web_traces", key)
            if observation is None:
                observation = {**empty_observation(web), **context, "dispatched": False,
                               "failure_code": "budget_exhausted" if isinstance(error, BudgetExceeded)
                               else "prior_call_unresolved"}
                self.journal.record("web_traces", key, observation)
            error.observation = observation
            raise
        if cached is not None:
            observation = cached.get("observation") or self.journal.record_value("web_traces", key)
            if observation is None:
                # Historical cache entries have no observed web evidence.
                observation = {**empty_observation(web), **context, "legacy_unobserved_cache": True}
            try:
                return output_type.model_validate(cached["data"]), observation
            except Exception as error:
                error.observation = observation
                raise
        started = time.monotonic()
        completed = False
        observation = {**empty_observation(web), **context, "dispatched": True}
        try:
            result = provider.invoke(prompt, payload, schema, web=web)
            # Record completed calls even when schema validation fails: they consumed usage.
            metadata = {**result.metadata, "call_id": call_id, "role": role, "operation": operation}
            observation.update(result.observation or result.metadata.get("observation") or {})
            observation.update(context)
            observation.update(tokens=result.tokens, searches=result.searches, web_enabled=web,
                               latency_seconds=time.monotonic() - started, usage_known=True)
            validation_error = None
            try:
                response = output_type.model_validate(result.data)
            except Exception as error:
                observation["failure_code"] = "invalid_response"
                validation_error = error
            self.journal.complete(key, {"data": result.data, "metadata": metadata, "observation": observation}, 0,
                                  result.tokens, result.searches, observation["latency_seconds"], observation=observation)
            completed = True
            if validation_error is not None:
                validation_error.observation = observation
                raise validation_error
            return response, observation
        except BaseException as error:
            if completed:
                raise
            observation.update(getattr(error, "observation", {}))
            observation.update(context)
            observation["latency_seconds"] = time.monotonic() - started
            limited = isinstance(error, SubscriptionLimit)
            if not observation["failure_code"]:
                observation["failure_code"] = "subscription_limit" if limited else "interrupted_or_unknown"
            # Persist trace and conservative usage before exposing the halt to other roles.
            self.journal.fail(key, "limited" if limited else "uncertain", observation["failure_code"],
                              observation["latency_seconds"], observation=observation)
            self.halted.set()
            error.observation = observation
            if not isinstance(error, (SubscriptionLimit, UncertainCall, BudgetExceeded, KeyboardInterrupt, SystemExit)):
                wrapped = UncertainCall("provider outcome unknown: " + type(error).__name__)
                wrapped.observation = observation
                raise wrapped from error
            raise
