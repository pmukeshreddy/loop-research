"""Scoped cancellation exercises real transport, archives, locks and budgets."""
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from loop_research.archive import count_codex_calls, read_jsonl
from loop_research.codex_backend import CallBudget, CodexBackend, INSTRUCTION


def completed(command, text="done"):
    Path(command[command.index("--output-last-message") + 1]).write_text(text)
    return SimpleNamespace(returncode=0, stdout=json.dumps({
        "type": "turn.completed", "usage": {"input_tokens": 8, "output_tokens": 2},
    }), stderr="")


@pytest.fixture
def local_provider(ctx, tmp_path):
    # A local Python subprocess accepts the CLI transport flags but never calls
    # a provider. Marker files synchronize actual process start and release.
    executable = tmp_path / "offline-provider"
    executable.write_text(f"#!{sys.executable}\n" + """
import json, os, sys, time
from pathlib import Path
request = json.loads(sys.stdin.read().splitlines()[-1])
if request.get("started"):
    Path(request["started"]).write_text(str(os.getpid()))
if request.get("release"):
    while not Path(request["release"]).exists():
        time.sleep(.01)
output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
output.write_text(request.get("reply", "done"))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 8, "output_tokens": 2}}))
""")
    executable.chmod(0o755)
    ctx.config.codex.bin = str(executable)
    ctx.config.codex.timeout_s = 5
    ctx.config.codex.max_retries = 0
    ctx.cancellation = Future()
    return CodexBackend(ctx)


def wait_for_file(path):
    deadline = time.monotonic() + 3
    while not path.exists():
        assert time.monotonic() < deadline, f"Offline process did not start: {path}"
        threading.Event().wait(.01)


def test_scope_rebinds_default_transport_and_cancels_only_child_processes(ctx, tmp_path, local_provider):
    parent = local_provider
    parent_started, parent_release = tmp_path / "parent-started", tmp_path / "parent-release"
    child_started, child_release = tmp_path / "child-started", tmp_path / "child-release"
    manager = parent.scope(budget=CallBudget(10, 10))
    child = manager.__enter__()
    with ThreadPoolExecutor(max_workers=3) as pool:
        try:
            parent_call = pool.submit(parent.complete, json.dumps({
                "started": str(parent_started), "release": str(parent_release), "reply": "parent",
            }), purpose="root")
            child_call = pool.submit(child.complete, json.dumps({
                "started": str(child_started), "release": str(child_release),
            }), purpose="refine")
            wait_for_file(parent_started)
            wait_for_file(child_started)
            pool.submit(manager.__exit__, None, None, None).result(timeout=3)
            with pytest.raises(CancelledError):
                child_call.result(timeout=1)
            assert child.ctx.cancellation.cancelled()
            assert not ctx.cancellation.cancelled()
            assert not parent_call.done(), "Closing the child scope interrupted its parent"
            parent_release.touch()
            assert parent_call.result(timeout=3) == "parent"
            assert parent.complete(json.dumps({"reply": "still usable"}), purpose="root") == "still usable"
            with pytest.raises(CancelledError):
                child.complete("after exit", purpose="refine")
        finally:
            # Also unblocks the deliberately broken parent-bound runner case.
            child_release.touch()
            parent_release.touch()
            ctx.cancellation.cancel()
            child.ctx.cancellation.cancel()


@pytest.mark.parametrize("cancel_before_scope", [False, True])
def test_parent_cancellation_propagates_to_scoped_process(ctx, tmp_path, local_provider,
                                                       cancel_before_scope):
    parent = local_provider
    if cancel_before_scope:
        ctx.cancellation.cancel()
    with parent.scope(budget=CallBudget(10, 10)) as child:
        with ThreadPoolExecutor(max_workers=1) as pool:
            started, release = tmp_path / "started", tmp_path / "release"
            call = pool.submit(child.complete, json.dumps({
                "started": str(started), "release": str(release),
            }), purpose="refine")
            try:
                if not cancel_before_scope:
                    wait_for_file(started)
                    ctx.cancellation.cancel()
                with pytest.raises(CancelledError):
                    call.result(timeout=3)
                assert child.ctx.cancellation.cancelled()
                if cancel_before_scope:
                    assert not started.exists()
            finally:
                release.touch()
                ctx.cancellation.cancel()
                child.ctx.cancellation.cancel()


def test_scope_preserves_injected_transport_retry_hooks_model_validation_and_usage(ctx):
    ctx.cancellation = Future()
    ctx.config.codex.max_retries = 1
    parent_budget, child_budget = CallBudget(10, 30), CallBudget(10, 30)
    waits, jitters, attempts = [], [], []

    def runner(command, **kwargs):
        attempts.append((command, kwargs))
        assert command[command.index("--model") + 1] == ctx.config.models.refine
        if len(attempts) == 1:
            return SimpleNamespace(returncode=1, stdout="", stderr="temporary failure")
        return completed(command)

    def jitter():
        jitters.append(True)
        return .25

    parent = CodexBackend(ctx, runner=runner, sleep=waits.append, jitter=jitter, budget=parent_budget)
    with parent.scope(budget=child_budget) as child:
        assert child.ctx is not ctx and child.ctx.config is ctx.config and child.ctx.trace is ctx.trace
        assert child.ctx.path == ctx.path
        assert child.ctx.cancellation is not ctx.cancellation
        with pytest.raises(ValueError, match="configured"):
            child.complete("invalid override", purpose="refine", model="wrong")
        assert child.complete("fixture", purpose="refine", model=ctx.config.models.refine) == "done"
        assert child.last_usage == {"input_tokens": 8, "output_tokens": 2}
        assert parent.last_usage is None
    assert child_budget.count == 2 and parent_budget.count == 0
    assert waits == [1.25] and jitters == [True]
    assert [x["attempt"] for x in read_jsonl(ctx.path / "codex_calls.jsonl")] == [0, 1]
    assert not ctx.cancellation.done()
    assert parent.complete("parent", purpose="refine") == "done"
    assert parent_budget.count == 1


def test_scope_exit_closes_admission_and_drains_all_concurrent_calls(ctx):
    ctx.cancellation = Future()
    entered = threading.Barrier(3)
    releases = [threading.Event(), threading.Event()]
    child_budget = CallBudget(10, 30)

    def runner(command, **kwargs):
        index = int(kwargs["input"].splitlines()[-1])
        entered.wait(timeout=3)
        assert releases[index].wait(3), "Test release did not arrive"
        return completed(command)

    parent = CodexBackend(ctx, runner=runner)
    manager = parent.scope(budget=child_budget)
    child = manager.__enter__()
    cancelled = threading.Event()
    child.ctx.cancellation.add_done_callback(lambda _: cancelled.set())
    with ThreadPoolExecutor(max_workers=3) as pool:
        calls = [pool.submit(child.complete, str(i), purpose="refine") for i in range(2)]
        try:
            entered.wait(timeout=3)
            closing = pool.submit(manager.__exit__, None, None, None)
            assert cancelled.wait(3)
            assert not closing.done(), "Exit returned before its admitted calls drained"
            with pytest.raises(CancelledError):
                child.complete("late call", purpose="refine")
            assert child_budget.count == 2
            releases[0].set()
            with pytest.raises(CancelledError):
                calls[0].result(timeout=3)
            assert not closing.done(), "Exit did not drain the second admitted call"
            releases[1].set()
            with pytest.raises(CancelledError):
                calls[1].result(timeout=3)
            assert closing.result(timeout=3) is False
            assert not ctx.cancellation.cancelled()
        finally:
            for release in releases:
                release.set()
            child.ctx.cancellation.cancel()


def test_close_drains_admitted_call_before_dispatch_with_deadline_protocol(ctx):
    entered, release, cancelled = threading.Event(), threading.Event(), threading.Event()

    class Deadline:
        def remaining(self):
            entered.set()
            assert release.wait(3)
            return 30

        def reserve(self):
            pytest.fail("A call cancelled before acquiring a slot must not reserve")

    parent = CodexBackend(ctx, runner=lambda *_args, **_kwargs: pytest.fail("Unexpected dispatch"))
    manager = parent.scope(budget=Deadline())
    child = manager.__enter__()
    child.ctx.cancellation.add_done_callback(lambda _: cancelled.set())
    with ThreadPoolExecutor(max_workers=2) as pool:
        call = pool.submit(child.complete, "fixture", purpose="refine")
        try:
            assert entered.wait(3)
            closing = pool.submit(manager.__exit__, None, None, None)
            assert cancelled.wait(3)
            assert not closing.done(), "Close missed a call admitted before backend dispatch"
            release.set()
            with pytest.raises(CancelledError):
                call.result(timeout=3)
            assert closing.result(timeout=3) is False
            assert count_codex_calls(ctx.path) == 0
        finally:
            release.set()
            child.ctx.cancellation.cancel()


def test_scope_without_parent_cancellation_closes_on_exception_and_keeps_parent_usable(ctx):
    assert ctx.cancellation is None
    parent = CodexBackend(ctx, runner=lambda command, **_: completed(command))
    with pytest.raises(RuntimeError, match="planner failure"):
        with parent.scope(budget=CallBudget(10, 30)) as child:
            assert child.complete("fixture", purpose="refine") == "done"
            raise RuntimeError("planner failure")
    assert child.ctx.cancellation.cancelled()
    assert ctx.cancellation is None
    assert parent.complete("fixture", purpose="root") == "done"


def test_normal_parent_future_completion_does_not_cancel_child(ctx):
    ctx.cancellation = Future()
    parent = CodexBackend(ctx, runner=lambda command, **_: completed(command))
    with parent.scope(budget=CallBudget(10, 30)) as child:
        ctx.cancellation.set_result(None)
        assert not child.ctx.cancellation.cancelled()
        assert child.complete("fixture", purpose="refine") == "done"


def test_scope_logging_override_preserves_failed_reply_and_parent_archive_policy(ctx):
    ctx.config.codex.log_full_text = False
    ctx.config.codex.max_retries = 1
    original_config = ctx.config.model_dump()
    parent_budget, child_budget = CallBudget(10, 30), CallBudget(10, 30)
    failed_reply = "failed attempt reply that must remain visible"
    attempts, waits = [], []

    def runner(command, **kwargs):
        assert ctx.config.model_dump() == original_config
        attempts.append(command)
        if len(attempts) == 1:
            result = completed(command, failed_reply)
            result.returncode, result.stderr = 1, "temporary failure after a partial reply"
            return result
        return completed(command, "success")

    parent = CodexBackend(ctx, runner=runner, sleep=waits.append, jitter=lambda: 0,
                          budget=parent_budget)
    with parent.scope(budget=child_budget, log_full_text=True) as child:
        assert child.ctx.config is not ctx.config
        assert child.ctx.config.models is not ctx.config.models
        expected_config = ctx.config.model_dump()
        expected_config["codex"]["log_full_text"] = True
        assert child.ctx.config.model_dump() == expected_config
        assert child.complete("retain exact evidence", purpose="refine") == "success"
        failed, succeeded = read_jsonl(ctx.path / "codex_calls.jsonl")
        assert failed["response"] == failed_reply
        assert failed["response_chars"] == len(failed_reply) == 45
        assert failed["exit_code"] == 1 and failed["error"]
        assert succeeded["response"] == "success"
        assert succeeded["exit_code"] == 0 and succeeded["error"] is None
        assert failed["prompt"] == succeeded["prompt"] == INSTRUCTION + "retain exact evidence"
    assert ctx.config.model_dump() == original_config
    assert waits == [1] and child_budget.count == 2 and parent_budget.count == 0
    assert parent.complete("parent prompt", purpose="root") == "success"
    parent_record = read_jsonl(ctx.path / "codex_calls.jsonl")[-1]
    assert "prompt" not in parent_record and "response" not in parent_record
    assert parent_record["response_chars"] == 7 and parent_budget.count == 1
    assert ctx.config.model_dump() == original_config


@pytest.mark.parametrize("parent_flag,override,expected", [
    (False, None, False), (True, None, True), (True, False, False),
])
def test_scope_logging_none_inherits_and_false_overrides_only_child(ctx, parent_flag,
                                                                 override, expected):
    ctx.config.codex.log_full_text = parent_flag
    original_config = ctx.config.model_dump()
    parent = CodexBackend(ctx, runner=lambda command, **_: completed(command, "kept reply"))
    with parent.scope(budget=CallBudget(10, 30), log_full_text=override) as child:
        assert child.complete("child", purpose="refine") == "kept reply"
        child_record, = read_jsonl(ctx.path / "codex_calls.jsonl")
        assert ("prompt" in child_record) is expected
        assert ("response" in child_record) is expected
    assert ctx.config.model_dump() == original_config
    assert parent.complete("parent", purpose="root") == "kept reply"
    parent_record = read_jsonl(ctx.path / "codex_calls.jsonl")[-1]
    assert ("prompt" in parent_record) is parent_flag
    assert ("response" in parent_record) is parent_flag
