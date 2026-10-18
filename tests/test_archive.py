import subprocess
import sys
import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor

import pytest
from loop_research.archive import append_json, read_jsonl

def test_archive_resume_preserves_config_and_harness(ctx):
    root = ctx.task("other")
    root.initialize("fixture-sha", benchmark="widesearch")
    root.initialize("fixture-sha", benchmark="widesearch")
    assert root.load("config.json") == ctx.config.model_dump()
    with pytest.raises(ValueError, match="harness"):
        root.initialize("changed-sha")
    root.config.codex.timeout_s = 100
    with pytest.raises(ValueError, match="configuration"):
        root.initialize("fixture-sha")


def test_run_process_preserves_input_output_and_exit_status(ctx):
    result = ctx.run_process([sys.executable, "-c",
        "import sys; print(sys.stdin.read()); print('fixture error', file=sys.stderr); sys.exit(7)"],
        input="fixture input", capture_output=True, text=True, timeout=5)
    assert result.returncode == 7
    assert result.stdout == "fixture input\n" and result.stderr == "fixture error\n"


@pytest.mark.parametrize("capture_output", [False, True])
def test_run_cancellation_kills_active_child_and_prevents_new_calls(ctx, monkeypatch, capture_output):
    ctx.cancellation = Future()
    started, children = threading.Event(), []
    popen = subprocess.Popen

    def track(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        started.set()
        return child

    monkeypatch.setattr(subprocess, "Popen", track)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(ctx.run_process, [sys.executable, "-c", "import time; time.sleep(30)"],
                             capture_output=capture_output, text=True, timeout=5)
        try:
            assert started.wait(5)
            ctx.cancellation.cancel()
            with pytest.raises(CancelledError):
                future.result(timeout=5)
            assert children[0].poll() is not None
            with pytest.raises(CancelledError):
                ctx.run_process([sys.executable, "-c", "raise AssertionError('must not start')"])
            assert len(children) == 1
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait()


def test_jsonl_and_real_trajectory_fields(ctx):
    path = ctx.path / "trajectory.jsonl"
    iteration = {"type": "iteration", "iteration": 1, "code_blocks": [{"code": "print('fixture')",
                 "result": {"stdout": "fixture", "stderr": "", "rlm_calls": [{"response": "subcall"}]}}]}
    append_json(path, {"type": "metadata"})
    append_json(path, iteration)
    assert read_jsonl(path)[1] == iteration


def test_codex_call_count_includes_pending_attempts_without_double_counting(ctx):
    from loop_research.archive import count_codex_calls, write_json
    log = ctx.path / "codex_calls.jsonl"
    write_json(ctx.path / "codex_attempts/completed.json", {"call_id": "completed", "purpose": "root"})
    write_json(ctx.path / "codex_attempts/pending.json", {"call_id": "pending", "purpose": "sub"})
    write_json(ctx.path / "codex_attempts/judge.json", {"call_id": "judge", "purpose": "grade"})
    append_json(log, {"call_id": "completed", "purpose": "root", "duration_s": .1})
    append_json(log, {"call_id": "completed", "purpose": "root", "duration_s": .1})
    append_json(log, {"purpose": "search", "duration_s": .1})  # Legacy completed call.
    assert count_codex_calls(ctx.path) == 4
    assert count_codex_calls(ctx.path, exclude_purposes=("grade",)) == 3
    assert count_codex_calls(ctx.path / "empty") == 0
