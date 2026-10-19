"""Real coordinator subprocess tests; fake research never calls a model or web tool."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest


OWN_ID = "research-" + "1" * 32
OTHER_ID = "research-" + "2" * 32
BASE = "a" * 40
HEAD = "b" * 40


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def wait_for(predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.01)
    raise AssertionError("Fake CLI/coordinator did not reach the expected state")


def read_if_ready(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@pytest.fixture
def coordinator(monkeypatch):
    directory = Path(__file__).resolve().parents[1] / "runs/round2"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location("replay_coordinator_ownership_test", directory / "launch_replay.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def plan_for(root, *, modes=("main",)):
    root.mkdir(parents=True, exist_ok=True)
    (root / "runs").mkdir(exist_ok=True)
    task = root / "task.json"
    write(task, {"task_id": "fixture", "benchmark": "research", "question": "Fixture question",
                 "as_of_date": None, "language": "en", "spec": {"columns": ["entity"], "keys": ["entity"]}})
    plan = {"main_root": str(root), "manifest_file": str(root / "manifest.json"),
            "log_directory": str(root / "logs"), "workspace_parent": str(root / "clones"),
            "input_files": [], "arms": [
                {"label": f"arm{i}", "workspace_mode": mode, "task_file": str(task),
                 "learning": True, "base": {"commit": BASE}, "publish_head": "PUBLISHED"}
                for i, mode in enumerate(modes)]}
    write(root / "plan.json", plan)
    return plan


FAKE_CLI = r'''
import json, pathlib, shlex, sys, time
spec = json.loads(pathlib.Path(sys.argv[1]).read_text())
root = pathlib.Path(spec["root"])
run = root / "runs" / spec["run_id"]
run.mkdir()
(run / "trace.log").write_text("original trace\n")
record = {"run_id": spec.get("archived_run_id", run.name),
          "task_id": spec.get("archived_task_id", "fixture"),
          "status": "running", "harness_head": spec["head"], "error": None}
(run / "research.json").write_text(json.dumps(record))
trace = run / "trace.log"
mode = spec["mode"]
if mode == "outside":
    trace = root.parent / "outside" / run.name / "trace.log"
elif mode == "filename":
    trace = run / "other.log"
elif mode == "run_name":
    trace = root / "runs" / "research-not-a-uuid" / "trace.log"
elif mode == "relative":
    trace = pathlib.Path("runs") / run.name / "trace.log"
elif mode == "symlink":
    (run / "trace.log").unlink()
    outside = root / "outside.log"
    outside.write_text("outside\n")
    (run / "trace.log").symlink_to(outside)
line = "Watch live: tail -f " + shlex.quote(str(trace))
if mode == "malformed_quote":
    line = "Watch live: tail -f 'unterminated"
elif mode == "extra_token":
    line += " extra"
elif mode == "wrong_command":
    line = line.replace("tail -f", "tail -F")
if mode in ("partial", "unterminated"):
    sys.stdout.write(line)
    sys.stdout.flush()
elif mode != "missing":
    print(line, flush=True)
    if mode == "duplicate":
        print(line, flush=True)
(root / "cli_ready").write_text("ready")
deadline = time.monotonic() + 12
while not (root / "release_cli").exists():
    if time.monotonic() > deadline:
        raise RuntimeError("Test did not release fake CLI")
    time.sleep(0.01)
if mode == "partial":
    print(flush=True)
record["status"] = "complete"
(run / "research.json").write_text(json.dumps(record))
'''


@contextmanager
def running(coordinator, monkeypatch, root, mode="normal", **extra):
    plan = plan_for(root)
    manifest = {"runs": {}}
    write(root / "manifest.json", manifest)
    script = root / "fake_cli.py"
    script.write_text(FAKE_CLI)
    spec = root / "fake_spec.json"
    write(spec, {"root": str(root), "run_id": OWN_ID, "head": HEAD, "mode": mode, **extra})
    monkeypatch.setattr(coordinator, "preflight", lambda *args: (manifest, {"source": {"commit": "fixture"}}))
    monkeypatch.setattr(coordinator, "unchanged_source", lambda *args: True)
    monkeypatch.setattr(coordinator, "command_for", lambda *args: [sys.executable, str(script), str(spec)])
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(coordinator.launch, root / "plan.json", plan, "fixture", root / "audit.json", 0.005)
        try:
            wait_for(lambda: (root / "cli_ready").exists())
            yield future
        finally:
            (root / "release_cli").touch()
            future.result(timeout=15)


def test_unrelated_archive_copy_during_owned_run_does_not_change_ownership(coordinator, monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    with running(coordinator, monkeypatch, root) as future:
        state = root / "logs/coordinator.json"
        wait_for(lambda: read_if_ready(state).get("arms", {}).get("arm0", {}).get("run_id") == OWN_ID)
        unrelated = tmp_path / OTHER_ID
        unrelated.mkdir()
        write(unrelated / "research.json", {"run_id": OTHER_ID, "status": "complete", "harness_head": "unrelated"})
        shutil.copytree(unrelated, root / "runs" / OTHER_ID)
        (root / "release_cli").touch()
        assert future.result(timeout=15) == 0
    result = coordinator.load(root / "logs/coordinator.json")
    assert result["status"] == "complete"
    assert result["arms"]["arm0"]["run_id"] == OWN_ID
    assert result["arms"]["arm0"]["run_path"] == str(root / "runs" / OWN_ID)
    assert coordinator.load(root / "manifest.json")["runs"] == {"arm0": OWN_ID}
    assert coordinator.load(root / "manifest.json")["PUBLISHED"] == HEAD
    assert coordinator.load(root / "runs" / OTHER_ID / "research.json")["harness_head"] == "unrelated"


def test_quoted_workspace_path_is_taken_from_cli_announcement(coordinator, monkeypatch, tmp_path):
    root = tmp_path / "workspace with 'quotes' and 雪"
    with running(coordinator, monkeypatch, root) as future:
        (root / "release_cli").touch()
        assert future.result(timeout=15) == 0
    record = coordinator.load(root / "logs/coordinator.json")["arms"]["arm0"]
    assert record["run_path"] == str(root / "runs" / OWN_ID)
    assert record["archive_announcement"] in (root / "logs/arm0.console.log").read_text().splitlines()


def test_partial_announcement_waits_for_newline_before_assigning_ownership(coordinator, monkeypatch, tmp_path):
    root = tmp_path / "workspace"
    with running(coordinator, monkeypatch, root, "partial") as future:
        # The CLI has created its directory and flushed an unterminated line.
        time.sleep(0.1)
        record = coordinator.load(root / "logs/coordinator.json")["arms"]["arm0"]
        assert "run_id" not in record
        (root / "release_cli").touch()
        assert future.result(timeout=15) == 0
    assert coordinator.load(root / "manifest.json")["runs"] == {"arm0": OWN_ID}


@pytest.mark.parametrize("mode", ["missing", "unterminated", "outside", "filename", "run_name", "relative",
                                 "symlink", "malformed_quote", "extra_token", "wrong_command", "duplicate"])
def test_invalid_or_missing_announcement_never_falls_back_to_directory_scan(coordinator, monkeypatch, tmp_path, mode):
    root = tmp_path / "workspace"
    with running(coordinator, monkeypatch, root, mode) as future:
        (root / "release_cli").touch()
        assert future.result(timeout=15) == 1
    record = coordinator.load(root / "logs/coordinator.json")["arms"]["arm0"]
    assert record["status"] == "failed"
    assert "announcement" in record["error"].lower()
    assert record["exit_code"] == 0
    assert coordinator.load(root / "manifest.json")["runs"] == {}
    assert "PUBLISHED" not in coordinator.load(root / "manifest.json")


@pytest.mark.parametrize("metadata", [{"archived_run_id": OTHER_ID}, {"archived_task_id": "other-task"}])
def test_durable_archive_identity_must_match_announcement_and_planned_task(coordinator, monkeypatch, tmp_path, metadata):
    root = tmp_path / "workspace"
    with running(coordinator, monkeypatch, root, **metadata) as future:
        (root / "release_cli").touch()
        assert future.result(timeout=15) == 1
    record = coordinator.load(root / "logs/coordinator.json")["arms"]["arm0"]
    assert record["status"] == "failed"
    assert "identity" in record["error"].lower()
    assert coordinator.load(root / "manifest.json")["runs"] == {}


def test_all_isolated_plan_is_valid(coordinator, tmp_path):
    plan = plan_for(tmp_path, modes=("clone", "clone"))
    assert coordinator.read_plan(tmp_path / "plan.json") == plan


def test_two_main_arms_are_rejected(coordinator, tmp_path):
    plan_for(tmp_path, modes=("main", "main"))
    with pytest.raises(ValueError, match="main workspace"):
        coordinator.read_plan(tmp_path / "plan.json")


def prepare_preflight(coordinator, monkeypatch, root, modes):
    from loop_research.config import Config
    plan = plan_for(root, modes=modes)
    config = Config.load(Path(__file__).resolve().parents[1] / "config.yaml")
    write(root / "config.json", config.model_dump(mode="json"))
    plan.update(config_file=str(root / "config.json"), original_config_file=str(root / "config.json"),
                shared_codex_max_concurrent=config.codex.max_concurrent, required_refine_cases=["saved"],
                saved_refine_execution=str(root / "saved.json"))
    write(root / "manifest.json", {"source_commit": "fixture", "runs": {},
                                   "unit_suite": {"source_commit": "fixture", "exit_code": 0, "passed": 1}})
    write(root / "saved.json", {"status": "complete", "source_verification": {"commit": "fixture"},
                               "results": [{"label": "saved", "status": "complete", "strict_proposal_valid": True,
                                            "accounting_valid": True, "original_inputs_unchanged": True,
                                            "original_harness_unchanged": True}]})
    write(root / "audit.json", {"search_root": str(root / "runs"), "runs": []})
    monkeypatch.setattr(coordinator, "verify_installed_source", lambda *args: {"commit": "fixture"})
    return plan


def test_all_isolated_preflight_does_not_require_main_head_to_equal_clone_base(coordinator, monkeypatch, tmp_path):
    plan = prepare_preflight(coordinator, monkeypatch, tmp_path, ("clone", "clone"))
    git_calls = []
    def git(path, *args):
        git_calls.append(args)
        return HEAD if args == ("rev-parse", "HEAD") else ""
    monkeypatch.setattr(coordinator, "git", git)
    _, gates = coordinator.preflight(plan, "fixture", tmp_path / "audit.json")
    assert ("rev-parse", "HEAD") not in git_calls
    assert ("status", "--porcelain") in git_calls
    assert gates["source"]["commit"] == "fixture"


@pytest.mark.parametrize("modes,dirty", [(("main",), False), (("clone",), True)])
def test_main_base_and_all_isolated_cleanliness_gates_remain_strict(coordinator, monkeypatch, tmp_path, modes, dirty):
    plan = prepare_preflight(coordinator, monkeypatch, tmp_path, modes)
    monkeypatch.setattr(coordinator, "git", lambda path, *args: HEAD if args == ("rev-parse", "HEAD") else "dirty" if dirty else "")
    with pytest.raises(ValueError, match="uncommitted changes" if dirty else "planned base"):
        coordinator.preflight(plan, "fixture", tmp_path / "audit.json")


def test_isolated_clone_checks_out_explicit_base_instead_of_current_main_head(coordinator, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    def git(*args):
        return subprocess.run(["git", "-C", str(source), *args], check=True, text=True, capture_output=True).stdout.strip()
    git("init")
    git("config", "user.name", "Offline fixture")
    git("config", "user.email", "fixture@localhost")
    write(source / "harness_state.json", {"revision": 1})
    git("add", "harness_state.json")
    git("commit", "-m", "Initial fixture")
    base = git("rev-parse", "HEAD")
    write(source / "harness_state.json", {"revision": 2})
    git("commit", "-am", "Later fixture")
    current = git("rev-parse", "HEAD")
    workspace, proof = coordinator.clone_workspace({"workspace_parent": str(tmp_path / "clones")}, {"label": "isolated"}, base, source)
    assert base != current
    assert proof["base"] == base
    assert coordinator.git(workspace / "harness", "rev-parse", "HEAD").strip() == base
    assert coordinator.load(workspace / "harness/harness_state.json") == {"revision": 1}
    assert git("rev-parse", "HEAD") == current
    assert not (workspace / "harness/.git/objects/info/alternates").exists()
    with pytest.raises(subprocess.CalledProcessError):
        coordinator.clone_workspace({"workspace_parent": str(tmp_path / "invalid")}, {"label": "isolated"}, "f" * 40, source)
