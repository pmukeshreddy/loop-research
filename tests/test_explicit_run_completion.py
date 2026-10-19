"""Explicit-run bookkeeping must reject completed archives with research errors."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


@pytest.fixture
def runner(monkeypatch, tmp_path):
    directory = Path(__file__).resolve().parents[1] / "runs/round2"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("explicit_completion_test", directory / "run_explicit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    here, root = tmp_path / "artifacts", tmp_path / "workspace"
    here.mkdir()
    root.mkdir()
    monkeypatch.setattr(module, "HERE", here)
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda seconds: time.sleep(0.001)))
    monkeypatch.setattr(module, "unchanged_source", lambda *args: True)
    isolated = tmp_path / "isolated"
    (isolated / "runs").mkdir(parents=True)
    monkeypatch.setattr(module, "clone_workspace", lambda *args: (isolated, {"workspace": str(isolated)}))
    write(here / "manifest.json", {"replay_plan": str(here / "plan.json"), "replay_coordinator": str(here / "coordinator.json")})
    write(here / "coordinator.json", {"status": "complete", "arms": {"arm": {"status": "complete"}},
                                      "preflight": {"source": {"commit": "fixture"}}})
    write(here / "explicit_request.json", {"label": "explicit", "base": "a" * 40,
                                          "question": "Fixture question", "columns": ["entity"],
                                          "keys": ["entity"], "language": "en", "classification": "fixture"})
    script = tmp_path / "fake_cli"
    script.write_text(f"#!{sys.executable}\n" + r'''
import json, pathlib, sys
root = pathlib.Path(sys.argv[sys.argv.index("--root") + 1])
spec = json.loads(pathlib.Path(sys.argv[sys.argv.index("--config") + 1]).read_text())
run = root / "runs" / spec["record"]["run_id"]
run.mkdir()
(run / "research.json").write_text(json.dumps(spec["record"]))
(run / "trace.log").write_text("original trace\n")
print("fake research completed", flush=True)
raise SystemExit(spec["exit_code"])
''')
    script.chmod(0o700)
    write(here / "plan.json", {"public_cli": str(script), "config_file": str(here / "fake_spec.json")})
    return module


def configure(runner, *, error=None, status="complete", exit_code=0):
    record = {"run_id": "research-" + "1" * 32, "task_id": "fixture", "status": status,
              "error": error, "harness_head": "b" * 40}
    write(runner.HERE / "fake_spec.json", {"record": record, "exit_code": exit_code})
    return record


@pytest.mark.parametrize("error", ["RuntimeError: fixture worker failed", {"type": "RuntimeError", "message": "fixture worker failed"}])
def test_exit_zero_complete_archive_with_worker_error_is_failed_and_preserved(runner, error):
    original = configure(runner, error=error)
    request = (runner.HERE / "explicit_request.json").read_bytes()
    with pytest.raises(ValueError, match="did not complete unchanged"):
        runner.main()
    execution = json.loads((runner.HERE / "explicit_execution.json").read_text())
    assert execution["status"] == "failed"
    assert execution["exit_code"] == 0
    assert execution["record"] == original
    assert execution["source_unchanged"] is True
    archive = Path(execution["run_path"]) / "research.json"
    assert json.loads(archive.read_text()) == original
    hashes = json.loads((runner.HERE / "explicit.archive_hashes.json").read_text())
    saved = next(item for item in hashes if item["relative_path"] == "research.json")
    assert saved["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (runner.HERE / "explicit_request.json").read_bytes() == request


def test_exit_zero_complete_archive_without_error_remains_complete(runner):
    original = configure(runner)
    runner.main()
    execution = json.loads((runner.HERE / "explicit_execution.json").read_text())
    assert execution["status"] == "complete"
    assert execution["record"] == original
    assert execution["exit_code"] == 0


@pytest.mark.parametrize("status,exit_code", [("interrupted", 0), ("complete", 1)])
def test_noncomplete_archive_or_nonzero_exit_remains_failed(runner, status, exit_code):
    original = configure(runner, status=status, exit_code=exit_code)
    with pytest.raises(ValueError, match="did not complete unchanged"):
        runner.main()
    execution = json.loads((runner.HERE / "explicit_execution.json").read_text())
    assert execution["status"] == "failed"
    assert execution["record"] == original
    assert execution["exit_code"] == exit_code


def test_changed_source_is_still_rejected_after_cli_exits(runner, monkeypatch):
    configure(runner)
    checks = iter([True, False])
    monkeypatch.setattr(runner, "unchanged_source", lambda *args: next(checks))
    with pytest.raises(ValueError, match="did not complete unchanged"):
        runner.main()
    execution = json.loads((runner.HERE / "explicit_execution.json").read_text())
    assert execution["source_unchanged"] is False
