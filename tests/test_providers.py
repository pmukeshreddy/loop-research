
import io
import json
from pathlib import Path

import pytest


def test_codex_command_forces_subscription_auth_and_disables_local_tools(tmp_path):
    from webshaper.providers import CodexProvider
    from webshaper.models import ModelConfig
    p = CodexProvider(ModelConfig())
    command = p.command(tmp_path, tmp_path / "schema.json", tmp_path / "out.json", False)
    assert 'forced_login_method="chatgpt"' in command
    assert 'web_search="disabled"' in command
    assert "--ignore-user-config" in command and "--ephemeral" in command
    for feature in ("shell_tool", "unified_exec", "plugins", "apps", "multi_agent", "browser_use"):
        assert feature in command and command[command.index(feature)-1] == "--disable"
    env = p.environment({"PATH": "/bin", "OPENAI_API_KEY": "secret", "CODEX_API_KEY": "secret2", "HOME": "/home/test"})
    assert "OPENAI_API_KEY" not in env and "CODEX_API_KEY" not in env
    assert env["HOME"] == "/home/test"
    # Codex's built-in search needs its execution host; tool access is restricted separately.
    assert "code_mode_host" not in command


def test_output_schema_is_strict_without_optional_required_ambiguity():
    from webshaper.providers import strict_schema
    from webshaper.models import SolverAnswer
    schema = strict_schema(SolverAnswer.model_json_schema())
    assert set(schema["required"]) == {"answer", "citations", "uncertainty"}
    assert schema["additionalProperties"] is False


def test_limit_error_is_a_clean_pause_not_api_fallback(tmp_path):
    from webshaper.providers import ModelGateway
    from webshaper.models import Budget, SolverAnswer
    from webshaper.storage import Journal, SubscriptionLimit

    class Limited:
        config = {"backend": "test"}
        def invoke(self, *args, **kwargs):
            raise SubscriptionLimit("usage limit reached")

    with Journal(tmp_path / "run.sqlite", {}, Budget()) as j:
        gateway = ModelGateway(j, {"solver": Limited()}, token_reservation=100)
        with pytest.raises(SubscriptionLimit):
            gateway.call("solver", "solver", {}, SolverAnswer, "attempt-1")
        assert j.calls()[0]["status"] == "limited"
        assert j.usage()["completed_calls"] == 0


def test_completed_model_call_is_reused_and_attempts_have_distinct_cache_keys(tmp_path):
    from webshaper.providers import ModelGateway, ProviderResult
    from webshaper.models import Budget, SolverAnswer
    from webshaper.storage import Journal

    class Counting:
        config = {"backend": "test"}
        count = 0
        def invoke(self, *args, **kwargs):
            self.count += 1
            return ProviderResult({"answer": ["a"], "citations": [], "uncertainty": ""}, 20, 0, {})

    provider = Counting()
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as j:
        g = ModelGateway(j, {"solver": provider}, token_reservation=100)
        g.call("solver", "solver", {}, SolverAnswer, "attempt-1")
        g.call("solver", "solver", {}, SolverAnswer, "attempt-1")
        g.call("solver", "solver", {}, SolverAnswer, "attempt-2")
        assert provider.count == 2
        assert j.usage()["tokens"] == 40


def fake_cli(monkeypatch, events, *, response=None, returncode=0, stderr=""):
    """Scripted CLI transport fixture; never invokes a model or claims live browsing."""
    from webshaper import providers

    class Process:
        def __init__(self, command, **kwargs):
            self.stdin = io.StringIO()
            self.stdout = io.StringIO("".join(json.dumps(event) + "\n" for event in events))
            self.returncode = None
            if response is not None:
                Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps(response))
            kwargs["stderr"].write(stderr)

        def wait(self, timeout=None):
            self.returncode = returncode
            return returncode

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(providers.subprocess, "Popen", Process)


def web_event(item_id, action, *, status="completed", event_type="item.completed"):
    return {"type": event_type, "item": {
        "id": item_id, "type": "web_search", "status": status, "action": action,
    }}


def test_role_permissions_restrict_reads_without_legacy_sandbox_override(tmp_path):
    import tomllib
    from webshaper.models import ModelConfig
    from webshaper.providers import CodexProvider

    command = CodexProvider(ModelConfig()).command(tmp_path, tmp_path / "s", tmp_path / "o", True)
    # CLI -c splits keys on dots; only its VALUES are parsed as TOML. Quoted path
    # keys must be inside a table value, not inside the CLI's dotted key string.
    for i, arg in enumerate(command):
        if arg == "-c":
            assert '"' not in command[i + 1].split("=", 1)[0]
    settings = tomllib.loads("\n".join(command[i + 1] for i, arg in enumerate(command) if arg == "-c"))
    assert "--sandbox" not in command
    profile = settings["permissions"][settings["default_permissions"]]
    assert profile["filesystem"] == {":root": "deny", ":minimal": "read", str(tmp_path.resolve()): "read"}
    assert profile["network"]["enabled"] is False
    assert settings["web_search"] == "live"
    assert settings["mcp_servers"] == {}
    for flag in ("shell_snapshot", "multi_agent_v2", "request_permissions_tool", "workspace_dependencies"):
        assert command[command.index(flag) - 1] == "--disable"


def test_observed_cli_counts_unique_actions_and_preserves_refs(monkeypatch):
    from webshaper.models import ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider

    events = [
        web_event("s", {"type": "search", "query": "example question"},
                  status="in_progress", event_type="item.started"),
        web_event("s", {"type": "search", "query": "example question"}),
        web_event("o", {"type": "open_page", "url": "https://example.org/page"}),
        web_event("f", {"type": "find_in_page", "url": "turn0search0", "pattern": "needle"}),
        {"type": "turn.completed", "usage": {"input_tokens": 42, "output_tokens": 8}},
    ]
    fake_cli(monkeypatch, events, response={"answer": ["invented https://fake.test"], "citations": [], "uncertainty": ""})
    result = CodexProvider(ModelConfig(max_searches_per_call=4)).invoke("test", {}, SolverAnswer.model_json_schema(), web=True)
    obs = result.observation
    assert result.searches == obs["searches"] == 3
    assert result.tokens == obs["tokens"] == 50
    assert obs["visited_urls"] == ["https://example.org/page"]
    assert len(obs["web_events"]) == 4
    assert obs["web_events"][0]["status"] == "in_progress"
    assert obs["web_events"][0]["timestamp"]
    assert obs["web_events"][-1]["action"]["url"] == "turn0search0"
    assert obs["web_events"][-1]["raw_event"] == events[3]
    assert obs["web_enabled"] is True
    assert obs["latency_seconds"] >= 0
    assert obs["cli_command"][0:2] == ["codex", "exec"]
    assert 'default_permissions="webshaper-role"' in obs["cli_command"]
    assert "--sandbox" not in obs["cli_command"]


def test_internal_open_ref_is_never_invented_as_visited_url(monkeypatch):
    from webshaper.models import ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider

    events = [web_event("o", {"type": "open_page", "url": "turn0search0"}),
              {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
    fake_cli(monkeypatch, events, response={"answer": [], "citations": [], "uncertainty": ""})
    obs = CodexProvider(ModelConfig()).invoke("test", {}, SolverAnswer.model_json_schema(), web=True).observation
    assert obs["visited_urls"] == []
    assert obs["web_events"][0]["action"] == {"type": "open_page", "url": "turn0search0"}


def test_started_or_failed_open_is_not_a_visited_page(monkeypatch):
    from webshaper.models import ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider

    events = [web_event("o", {"type": "open_page", "url": "https://example.org"},
                        status="in_progress", event_type="item.started"),
              web_event("o", {"type": "open_page", "url": "https://example.org"}, status="failed"),
              {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
    fake_cli(monkeypatch, events, response={"answer": [], "citations": [], "uncertainty": "access denied"})
    obs = CodexProvider(ModelConfig()).invoke("test", {}, SolverAnswer.model_json_schema(), web=True).observation
    assert obs["searches"] == 1
    assert obs["visited_urls"] == []


def test_live_cli_event_shape_has_normalized_status_and_raw_query(monkeypatch):
    """Shape captured in open-web-capability-v1; no live model runs in this test."""
    from webshaper.models import ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider

    events = [
        {"type": "item.started", "item": {"id": "native", "type": "web_search", "query": "",
                                           "action": {"type": "other"}}},
        {"type": "item.updated", "item": {"id": "native", "type": "web_search", "action": None}},
        {"type": "item.completed", "item": {"id": "native", "type": "web_search", "query": "https://example.org",
            "action": {"type": "open_page", "url": "https://example.org"}, "results": [
                {"type": "text_result", "ref_id": "turn1view0", "url": "https://example.org", "snippet": "Total lines: 10"}
            ]}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}},
    ]
    fake_cli(monkeypatch, events, response={"answer": [], "citations": [], "uncertainty": ""})
    obs = CodexProvider(ModelConfig()).invoke("test", {}, SolverAnswer.model_json_schema(), web=True).observation
    assert [e["status"] for e in obs["web_events"]] == ["started", "updated", "completed"]
    assert obs["web_events"][1]["action"] is None
    assert obs["web_events"][-1]["raw_event"] == events[2]
    assert obs["visited_urls"] == ["https://example.org"]
    assert obs["searches"] == 1


def test_observed_call_caches_trace_and_usage_without_redispatch(tmp_path, monkeypatch):
    from webshaper.models import Budget, ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider, ModelGateway
    from webshaper.storage import Journal

    events = [web_event("s", {"type": "search", "query": "example"}),
              {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
    fake_cli(monkeypatch, events, response={"answer": ["a"], "citations": [], "uncertainty": ""})
    provider = CodexProvider(ModelConfig())
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        gateway = ModelGateway(journal, {"solver": provider}, token_reservation=100)
        answer, obs = gateway.call_observed("solver", "solver", {}, SolverAnswer, "one", web=True)
        monkeypatch.setattr(provider, "invoke", lambda *a, **k: pytest.fail("cached call redispatched"))
        cached_answer, cached_obs = gateway.call_observed("solver", "solver", {}, SolverAnswer, "one", web=True)
        assert cached_answer == answer
        assert cached_obs == obs
        assert journal.usage()["tokens"] == 12
        assert journal.usage()["calls"] == 1
        assert journal.records("web_traces") == [obs]
        assert obs["cache_key"] == journal.calls()[0]["key"]
        assert obs["call_id"] == "one" and obs["role"] == "solver" and obs["operation"] == "solver"


def test_budget_interruption_keeps_partial_trace_and_full_reservation(tmp_path, monkeypatch):
    from webshaper.models import Budget, ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider, ModelGateway
    from webshaper.storage import BudgetExceeded, Journal

    events = [web_event("s", {"type": "search", "query": "example"}),
              web_event("o", {"type": "open_page", "url": "https://example.org"})]
    fake_cli(monkeypatch, events)
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        gateway = ModelGateway(journal, {"solver": CodexProvider(ModelConfig(max_searches_per_call=1))},
                               token_reservation=100)
        with pytest.raises(BudgetExceeded) as caught:
            gateway.call_observed("solver", "solver", {}, SolverAnswer, "one", web=True)
        obs = caught.value.observation
        assert obs["failure_code"] == "web_action_budget"
        # The second event was already queued by the fake remote process. Keep
        # it even after stopping at the first; never hide in-flight activity.
        assert obs["searches"] == 2
        assert len(obs["web_events"]) == 2
        assert journal.records("web_traces") == [obs]
        assert journal.usage()["token_upper_bound"] == 100
        assert journal.usage()["searches"] == 2
        assert gateway.halted.is_set()


def test_failed_cli_preserves_web_trace_and_capability_message(tmp_path, monkeypatch):
    from webshaper.models import Budget, ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider, ModelGateway
    from webshaper.storage import Journal, UncertainCall

    events = [web_event("s", {"type": "search", "query": "example"}),
              {"type": "item.completed", "item": {"id": "m", "type": "agent_message",
               "text": "The web tool is unavailable in this session."}},
              {"type": "turn.failed", "error": {"message": "Web tool unavailable"}}]
    fake_cli(monkeypatch, events, returncode=1)
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        gateway = ModelGateway(journal, {"solver": CodexProvider(ModelConfig())}, token_reservation=100)
        with pytest.raises(UncertainCall) as caught:
            gateway.call_observed("solver", "solver", {}, SolverAnswer, "one", web=True)
        obs = caught.value.observation
        assert obs["failure_code"] == "capability_unavailable"
        assert obs["agent_messages"] == [events[1]["item"]["text"]]
        assert obs["failures"][0]["raw_event"] == events[2]
        assert journal.records("web_traces") == [obs]
        assert journal.usage()["token_upper_bound"] == 100
        assert journal.usage()["searches"] == 3


def test_completed_no_tool_output_cannot_claim_observed_browsing(tmp_path, monkeypatch):
    from webshaper.models import Budget, ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider, ModelGateway
    from webshaper.storage import Journal

    events = [{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}]
    fake_cli(monkeypatch, events, response={"answer": ["a"], "citations": [],
                                         "uncertainty": "I searched https://fake.test"})
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        gateway = ModelGateway(journal, {"solver": CodexProvider(ModelConfig())}, token_reservation=100)
        _, obs = gateway.call_observed("solver", "solver", {}, SolverAnswer, "one", web=True)
        assert obs["searches"] == 0
        assert obs["web_events"] == obs["visited_urls"] == []
        assert "https://fake.test" in obs["output_text"]


def test_schema_failure_still_caches_completed_trace(tmp_path, monkeypatch):
    from pydantic import ValidationError
    from webshaper.models import Budget, ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider, ModelGateway
    from webshaper.storage import Journal

    fake_cli(monkeypatch, [{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 2}}],
             response={"wrong": True})
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        gateway = ModelGateway(journal, {"solver": CodexProvider(ModelConfig())}, token_reservation=100)
        with pytest.raises(ValidationError) as caught:
            gateway.call_observed("solver", "solver", {}, SolverAnswer, "one", web=True)
        assert journal.usage()["completed_calls"] == 1
        assert journal.usage()["tokens"] == 12
        assert journal.records("web_traces") == [caught.value.observation]
        assert caught.value.observation["failure_code"] == "invalid_response"


def test_explicit_limited_retry_archives_trace_with_attempt(tmp_path):
    from webshaper.models import Budget, SolverAnswer
    from webshaper.providers import ModelGateway, ProviderResult
    from webshaper.storage import Journal, SubscriptionLimit

    class OnceLimited:
        config = {"backend": "scripted"}
        limited = False

        def invoke(self, *args, **kwargs):
            if not self.limited:
                self.limited = True
                raise SubscriptionLimit("quota exceeded")
            return ProviderResult({"answer": ["a"], "citations": [], "uncertainty": ""}, 20, 0, {})

    provider = OnceLimited()
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        with pytest.raises(SubscriptionLimit):
            ModelGateway(journal, {"solver": provider}, 100).call_observed(
                "solver", "solver", {}, SolverAnswer, "one", web=True)
        original_key = journal.calls()[0]["key"]
        journal.retry_limited()
        _, obs = ModelGateway(journal, {"solver": provider}, 100).call_observed(
            "solver", "solver", {}, SolverAnswer, "one", web=True)
        traces = journal.records("web_traces")
        assert len(traces) == 2
        assert {t["cache_key"] for t in traces} == {c["key"] for c in journal.calls()}
        assert obs["cache_key"] == original_key
        assert journal.usage()["token_upper_bound"] == 120


def test_predispatch_budget_exhaustion_has_trace_without_usage(tmp_path):
    from webshaper.models import Budget, SolverAnswer
    from webshaper.providers import ModelGateway
    from webshaper.storage import BudgetExceeded, Journal

    class NeverCalled:
        config = {"backend": "scripted"}

        def invoke(self, *args, **kwargs):
            pytest.fail("over-budget call was dispatched")

    with Journal(tmp_path / "run.sqlite", {}, Budget(max_tokens=99)) as journal:
        with pytest.raises(BudgetExceeded) as caught:
            ModelGateway(journal, {"solver": NeverCalled()}, 100).call_observed(
                "solver", "solver", {}, SolverAnswer, "one", web=True)
        assert caught.value.observation["dispatched"] is False
        assert journal.usage()["calls"] == 0
        assert journal.records("web_traces") == [caught.value.observation]


def test_unexpected_tool_failure_preserves_event_and_halts(tmp_path, monkeypatch):
    from webshaper.models import Budget, ModelConfig, SolverAnswer
    from webshaper.providers import CodexProvider, ModelGateway
    from webshaper.storage import Journal, UncertainCall

    event = {"type": "item.started", "item": {"id": "bad", "type": "command_execution", "command": "pwd"}}
    fake_cli(monkeypatch, [event])
    with Journal(tmp_path / "run.sqlite", {}, Budget()) as journal:
        gateway = ModelGateway(journal, {"solver": CodexProvider(ModelConfig())}, 100)
        with pytest.raises(UncertainCall) as caught:
            gateway.call_observed("solver", "solver", {}, SolverAnswer, "one", web=True)
        assert caught.value.observation["failure_code"] == "unexpected_tool"
        assert caught.value.observation["failures"][0]["raw_event"] == event
        assert gateway.halted.is_set()
