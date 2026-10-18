import json
import subprocess
import sys


def test_reexport_after_code_upgrade_preserves_generation_rules(tmp_path, monkeypatch):
    from webshaper.pipeline import run
    from webshaper.fixtures import fixture_config
    from webshaper import cli
    from webshaper.storage import dump
    root = tmp_path / "run"
    run(fixture_config(), root)
    before = json.loads((root / "export/manifest.json").read_text())
    def changed(*args):
        return {"implementation_hash": "new-generation-code"}
    monkeypatch.setattr(cli, "frozen_config", changed)
    assert cli.main(["export", "--run-dir", str(root)]) == 0
    after = json.loads((root / "export/manifest.json").read_text())
    assert dump(before["frozen"]) == dump(after["frozen"])
    assert before["stats"]["usage"] == after["stats"]["usage"]


def test_cli_fixture_run_and_status(tmp_path):
    config = tmp_path / "fixture.json"
    commands = [["init", "--mode", "fixture", "--output", str(config)],
                ["run", "--config", str(config), "--run-dir", str(tmp_path / "run")],
                ["status", "--run-dir", str(tmp_path / "run")]]
    for arguments in commands:
        result = subprocess.run([sys.executable, "-m", "webshaper", *arguments], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
    stats = json.loads(result.stdout)
    assert stats["accepted_tasks"] == 1
    assert stats["data_mode"] == "fixture"


def test_live_init_defaults_to_codex_and_zero_paid_budget(tmp_path):
    config = tmp_path / "live.json"
    result = subprocess.run([sys.executable, "-m", "webshaper", "init", "--mode", "live", "--output", str(config)],
                             capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    data = json.loads(config.read_text())
    assert data["generator"]["backend"] == "codex"
    assert data["research_mode"] == "open_web"
    assert data["budget"]["max_usd"] == 0
    assert data["concurrency"] == 1
    assert data["target_tasks"] == 250
    assert data["campaign"]["target_companies"] == 50
    assert data["sources"] == []
