import base64
import hashlib
import importlib
import importlib.util
import json
import subprocess
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner


def cli_module():
    assert importlib.util.find_spec("loop_research.cli") is not None, "The CLI is not implemented"
    return importlib.import_module("loop_research.cli")


def test_init_is_idempotent_and_preserves_verification(tmp_path):
    cli = cli_module()
    runner = CliRunner()
    result = runner.invoke(cli.app, ["--root", str(tmp_path), "init"])
    assert result.exit_code == 0, result.output
    for name in ("skills", "runs", "reports", "data", "docs"):
        assert (tmp_path / name).is_dir()
    assert (tmp_path / "skills/.git").is_dir()
    assert (tmp_path / "config.yaml").is_file()
    verification = tmp_path / "docs/VERIFIED.md"
    assert "unverified" in verification.read_text().lower()
    verification.write_text("Existing verified evidence\n")
    again = runner.invoke(cli.app, ["--root", str(tmp_path), "init"])
    assert again.exit_code == 0, again.output
    assert verification.read_text() == "Existing verified evidence\n"


@pytest.mark.parametrize("arguments", [
    ["run", "--split", "test", "--n", "1"],
    ["run", "--split", "val", "--n", "1"],
    ["run", "--n", "0"],
    ["evaluate", "--benchmark", "widesearch", "--split", "test"],
    ["evaluate", "--benchmark", "wandr"],
])
def test_cli_rejects_forbidden_scope_before_research(tmp_path, arguments):
    cli = cli_module()
    (tmp_path / "config.yaml").write_text("{}\n")
    result = CliRunner().invoke(cli.app, ["--root", str(tmp_path), *arguments])
    assert result.exit_code != 0
    assert not (tmp_path / "runs").exists()


def test_cli_uses_explicit_config_and_returns_archive_id(tmp_path, monkeypatch):
    cli = cli_module()
    from loop_research import loop
    (tmp_path / "custom.yaml").write_text("data:\n  seed: 73\n")
    def run(root, config, n):
        assert root == tmp_path and config.data.seed == 73 and n == 2
        return "train-fixture"
    monkeypatch.setattr(loop, "run_train", run)
    result = CliRunner().invoke(cli.app, ["--root", str(tmp_path), "--config", "custom.yaml", "run", "--n", "2"])
    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "train-fixture"


def test_verify_reports_failed_checks_without_live_calls(tmp_path, monkeypatch):
    cli = cli_module()
    from loop_research import evaluate
    (tmp_path / "config.yaml").write_text("{}\n")
    def command(args, **kwargs):
        assert args[1:] in (["--version"], ["exec", "--help"], ["login", "status"])
        text = "codex fixture" if args[1:] == ["--version"] else "Logged in using an API key"
        return subprocess.CompletedProcess(args, 0, text, "")
    monkeypatch.setattr(cli.subprocess, "run", command)
    monkeypatch.setattr(cli, "verify_rlm", lambda: "pinned fixture")
    monkeypatch.setattr(cli.WideSearchData, "verify_code", lambda self: None)
    monkeypatch.setattr(cli.WideSearchData, "verify_data", lambda self: None)
    monkeypatch.setattr(evaluate, "verify_wandr", lambda *args: [("WANDR browser", True, "ready")])
    result = CliRunner().invoke(cli.app, ["--root", str(tmp_path), "verify"])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output and "ChatGPT" in result.output and "WANDR browser" in result.output


def test_rlm_verification_checks_import_location_and_installed_hash(tmp_path, monkeypatch):
    cli = cli_module()
    source = tmp_path / "rlm/__init__.py"
    source.parent.mkdir()
    source.write_text("# fixture package\n")
    digest = base64.urlsafe_b64encode(hashlib.sha256(source.read_bytes()).digest()).decode().rstrip("=")
    class Entry:
        hash = SimpleNamespace(mode="sha256", value=digest)
        def __str__(self):
            return "rlm/__init__.py"
    distribution = SimpleNamespace(
        files=[Entry()],
        read_text=lambda name: json.dumps({"url": "https://github.com/alexzhang13/rlm.git", "vcs_info": {
            "vcs": "git", "commit_id": "d04208afbad29ca675ab13478c40ee8bebc84bfe"}}),
        locate_file=lambda path: tmp_path / str(path),
    )
    monkeypatch.setattr(cli.metadata, "distribution", lambda name: distribution)
    monkeypatch.setattr(cli.importlib, "import_module", lambda name: SimpleNamespace(__file__=str(source)))
    assert "d04208a" in cli.verify_rlm()
    source.write_text("# altered package\n")
    with pytest.raises(ValueError, match="integrity"):
        cli.verify_rlm()


def test_smoke_archives_each_real_component_boundary(tmp_path, monkeypatch):
    cli = cli_module()
    from loop_research import rlm_codex_client
    from loop_research.config import Config
    from loop_research.archive import read_json
    calls = []
    class Backend:
        def __init__(self, ctx, **kwargs):
            self.ctx = ctx
        def complete(self, prompt, **kwargs):
            calls.append(kwargs["purpose"])
            return {"root": "READY", "search": json.dumps({"results": [{"title": "Python", "url": "https://www.python.org/", "snippet": "Python"}]}),
                    "fetch": "Python programming language"}[kwargs["purpose"]]
    class RLM:
        def __init__(self, backend, **kwargs):
            assert set(kwargs["custom_tools"]) >= {"search", "fetch"}
            assert 0 < kwargs["max_timeout"] < 3600
            self.logger = kwargs["logger"]
        def completion(self, prompt, **kwargs):
            assert "REPL" in prompt
            self.logger.log_metadata(SimpleNamespace(to_dict=lambda: {"fixture": "smoke"}))
            return SimpleNamespace(response="5")
    monkeypatch.setattr(cli, "CodexBackend", Backend)
    monkeypatch.setattr(rlm_codex_client, "CodexRLM", RLM)
    run_id = cli.smoke_run(tmp_path, Config())
    saved = read_json(tmp_path / "runs" / run_id / "smoke/smoke.json")
    assert saved["plain"] == "READY" and saved["rlm"] == "5"
    assert calls == ["root", "search", "fetch"]
    assert (tmp_path / "runs" / run_id / "smoke/tool_cache.json").exists()
    assert (tmp_path / "runs" / run_id / "smoke/trajectory.jsonl").stat().st_size > 0


def test_report_works_without_model_or_dataset(tmp_path):
    cli = cli_module()
    (tmp_path / "config.yaml").write_text("{}\n")
    result = CliRunner().invoke(cli.app, ["--root", str(tmp_path), "report"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "reports/summary.md").is_file()
