
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
