"""Local process cleanup uses real child groups; no model or network transport."""
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import errno
import logging
import os
import signal
import subprocess
import sys
import threading

import pytest


PAUSE = [sys.executable, "-B", "-c", "import signal; signal.pause()"]


def track_children(monkeypatch):
    children = []
    popen = subprocess.Popen

    def tracked(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", tracked)
    return children


@pytest.mark.parametrize("capture_output", [False, True])
@pytest.mark.parametrize("already_gone", [False, True])
def test_timeout_and_cancellation_share_one_group_stop(ctx, monkeypatch, caplog,
                                                     capture_output, already_gone):
    """Hold timeout cleanup open while cancellation enters its same callback."""
    ctx.cancellation = Future()
    first_signal, release_signal, callback_entered, callback_finished = (
        threading.Event() for _ in range(4)
    )
    calls = []
    killpg = os.killpg
    children = track_children(monkeypatch)
    add_callback = ctx.cancellation.add_done_callback

    def observed_callback(callback):
        def invoke(future):
            callback_entered.set()
            try:
                callback(future)
            finally:
                callback_finished.set()
        add_callback(invoke)

    def signal_group(pid, sig):
        calls.append((pid, sig))
        if len(calls) == 1:
            killpg(pid, sig)
            first_signal.set()
            assert release_signal.wait(3), "test did not release first cleanup"
            if already_gone:
                raise ProcessLookupError(errno.ESRCH, "fixture group exited")
        else:
            # Model the observed Darwin result only for a forbidden second call.
            # The first call above really killed this test's owned process group.
            raise PermissionError(errno.EPERM, "duplicate group signal")

    monkeypatch.setattr(ctx.cancellation, "add_done_callback", observed_callback)
    monkeypatch.setattr(os, "killpg", signal_group)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(ctx.run_process, PAUSE, capture_output=capture_output,
                              text=True, timeout=.05, start_new_session=True)
        cancelling = None
        try:
            assert first_signal.wait(3)
            cancelling = pool.submit(ctx.cancellation.cancel)
            assert callback_entered.wait(3)
            # Let the competing callback run while the first signal is in flight.
            # Correct cleanup may block here until the first caller releases it.
            callback_finished.wait(.1)
        finally:
            release_signal.set()
            if cancelling is not None:
                cancelling.result(timeout=3)
            with pytest.raises(subprocess.TimeoutExpired):
                running.result(timeout=3)
        assert children[0].returncode == -signal.SIGKILL
        assert calls == [(children[0].pid, signal.SIGKILL)]
        assert not [record for record in caplog.records if record.exc_info]


@pytest.mark.parametrize("capture_output", [False, True])
def test_cancellation_after_finished_process_does_not_signal_group(ctx, monkeypatch,
                                                                 capture_output):
    ctx.cancellation = Future()
    calls = []
    monkeypatch.setattr(os, "killpg", lambda *args: calls.append(args))
    result = ctx.run_process([sys.executable, "-B", "-c", "pass"], timeout=3,
                             capture_output=capture_output, start_new_session=True)
    assert result.returncode == 0
    assert ctx.cancellation.cancel()
    assert calls == []


def test_reaped_leader_still_terminates_descendant_holding_pipe(ctx, monkeypatch):
    """A reaped leader does not make its still-owned process group disappear."""
    popen, killpg = subprocess.Popen, os.killpg
    children, calls, drained = [], [], []
    descendant = (
        "import os,signal\n"
        "pid=os.fork()\n"
        "if pid == 0:\n"
        "    signal.pause()\n"
        "else:\n"
        "    print(pid, flush=True)\n"
        "    os._exit(0)\n"
    )
    unrelated = popen(PAUSE, start_new_session=True)

    def tracked(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        assert child.wait(timeout=3) == 0  # Reap only the leader before communicate.
        communicate = child.communicate

        def observed(*args, **kwargs):
            result = communicate(*args, **kwargs)
            drained.append(result)
            return result

        monkeypatch.setattr(child, "communicate", observed)
        return child

    def signal_group(pid, sig):
        assert pid == children[0].pid and pid != unrelated.pid
        calls.append((pid, sig))
        return killpg(pid, sig)

    monkeypatch.setattr(subprocess, "Popen", tracked)
    monkeypatch.setattr(os, "killpg", signal_group)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            ctx.run_process([sys.executable, "-B", "-c", descendant], capture_output=True,
                            text=True, timeout=.05, start_new_session=True)
        assert calls == [(children[0].pid, signal.SIGKILL)]
        assert len(drained) == 1 and int(drained[0][0].strip()) > 0
        assert drained[0][1] == ""
        assert children[0].returncode == 0  # The descendant, not the leader, needed killing.
        assert unrelated.poll() is None
    finally:
        unrelated.kill()
        unrelated.wait(timeout=3)
        if not drained:
            for child in children:
                try:
                    killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


def test_first_group_permission_error_remains_visible_to_timeout_caller(ctx, monkeypatch):
    children = track_children(monkeypatch)
    killpg = os.killpg
    failure = PermissionError(errno.EPERM, "fixture first group kill denied")
    calls = []

    def denied(pid, sig):
        calls.append((pid, sig))
        raise failure

    monkeypatch.setattr(os, "killpg", denied)
    try:
        with pytest.raises(PermissionError) as caught:
            ctx.run_process(PAUSE, capture_output=True, timeout=.05, start_new_session=True)
        assert caught.value is failure
        assert isinstance(caught.value.__context__, subprocess.TimeoutExpired)
        assert calls == [(children[0].pid, signal.SIGKILL)]
        assert children[0].poll() is None  # Do not pretend the denied cleanup succeeded.
    finally:
        for child in children:
            killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=3)


def test_first_group_permission_error_remains_visible_in_cancellation_callback(ctx,
                                                                             monkeypatch,
                                                                             caplog):
    ctx.cancellation = Future()
    children = track_children(monkeypatch)
    killpg = os.killpg
    started = threading.Event()
    failure = PermissionError(errno.EPERM, "fixture callback group kill denied")
    add_callback = ctx.cancellation.add_done_callback

    def registered(callback):
        add_callback(callback)
        started.set()

    monkeypatch.setattr(ctx.cancellation, "add_done_callback", registered)

    def denied(pid, sig):
        raise failure

    monkeypatch.setattr(os, "killpg", denied)
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(ctx.run_process, PAUSE, capture_output=True, timeout=3,
                              start_new_session=True)
        try:
            assert started.wait(3)
            with caplog.at_level(logging.ERROR, logger="concurrent.futures"):
                ctx.cancellation.cancel()
            assert any(record.exc_info and record.exc_info[1] is failure
                       for record in caplog.records)
            assert children[0].poll() is None
        finally:
            for child in children:
                killpg(child.pid, signal.SIGKILL)
            with pytest.raises(CancelledError):
                running.result(timeout=3)
