"""Exercise real OS slot locks without invoking a model or making network calls."""
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
import multiprocessing
import fcntl
import os
from pathlib import Path
import queue
import tempfile
import threading
import time
from types import SimpleNamespace

import pytest

from loop_research import codex_backend
from loop_research.codex_backend import BudgetExceeded, CodexBackend


def _tickets():
    directory = Path(tempfile.gettempdir()) / f"loop-codex-slots-{os.getuid()}"
    return list(directory.glob("wait-*"))


def _queue_directory():
    directory = Path(tempfile.gettempdir()) / f"loop-codex-slots-{os.getuid()}"
    directory.mkdir(exist_ok=True)
    return directory


def _slot_process(ctx, label, admitted, release, attempted, sleeping=None, resume=None):
    """Only control the polling schedule; file locking and admission stay real."""
    real_sleep = time.sleep
    blocked = False

    def scheduled_sleep(delay):
        nonlocal blocked
        attempted.set()
        if sleeping is not None and not blocked:
            blocked = True
            sleeping.set()
            assert resume.wait(5), "Test did not resume the queued process"
        real_sleep(min(delay, .005))

    codex_backend.time = SimpleNamespace(monotonic=time.monotonic, sleep=scheduled_sleep)
    with CodexBackend(ctx)._acquire_slot(5):
        attempted.set()
        admitted.put(label)
        assert release.wait(5), "Test did not release the admitted process"


def test_queued_thread_precedes_late_arrival_even_when_late_arrival_polls_first(ctx, monkeypatch):
    """Removing queue-order enforcement lets the late caller take the freed slot."""
    ctx.config.codex.max_concurrent = 1
    backend = CodexBackend(ctx)
    occupied = backend._acquire_slot(5)
    older_sleeping, resume_older, late_attempted = (threading.Event() for _ in range(3))
    releases = {label: threading.Event() for label in ("older", "late")}
    admitted = queue.Queue()
    real_sleep = time.sleep
    first_old_sleep = True
    labels = threading.local()

    def scheduled_sleep(delay):
        nonlocal first_old_sleep
        if labels.value == "older" and first_old_sleep:
            first_old_sleep = False
            older_sleeping.set()
            assert resume_older.wait(5)
        if labels.value == "late":
            late_attempted.set()
        real_sleep(min(delay, .005))

    def acquire(label):
        labels.value = label
        with backend._acquire_slot(5):
            if label == "late":
                late_attempted.set()
            admitted.put(label)
            assert releases[label].wait(5)

    monkeypatch.setattr(codex_backend, "time", SimpleNamespace(
        monotonic=time.monotonic, sleep=scheduled_sleep))
    with ThreadPoolExecutor(max_workers=2) as pool:
        older = pool.submit(acquire, "older")
        late = None
        try:
            assert older_sleeping.wait(5)
            occupied.close()
            late = pool.submit(acquire, "late")
            assert late_attempted.wait(5)
            resume_older.set()
            first = admitted.get(timeout=5)
            releases[first].set()
            second = admitted.get(timeout=5)
            releases[second].set()
            older.result(timeout=5)
            late.result(timeout=5)
            assert [first, second] == ["older", "late"]
        finally:
            occupied.close()
            resume_older.set()
            for event in releases.values():
                event.set()
    assert _tickets() == []


def test_queued_process_precedes_late_process_even_when_late_process_polls_first(ctx):
    """A process-local queue cannot protect an older request in another process."""
    ctx.config.codex.max_concurrent = 1
    occupied = CodexBackend(ctx)._acquire_slot(5)
    mp = multiprocessing.get_context("spawn")
    admitted = mp.Queue()
    old_sleeping, resume_old, old_attempted, late_attempted = (mp.Event() for _ in range(4))
    releases = {label: mp.Event() for label in ("older", "late")}
    old = mp.Process(target=_slot_process, args=(
        ctx, "older", admitted, releases["older"], old_attempted, old_sleeping, resume_old))
    late = mp.Process(target=_slot_process, args=(
        ctx, "late", admitted, releases["late"], late_attempted))
    old.start()
    try:
        assert old_sleeping.wait(5)
        occupied.close()
        late.start()
        assert late_attempted.wait(5)
        resume_old.set()
        first = admitted.get(timeout=5)
        releases[first].set()
        second = admitted.get(timeout=5)
        releases[second].set()
        assert [first, second] == ["older", "late"]
    finally:
        occupied.close()
        resume_old.set()
        for event in releases.values():
            event.set()
        for process in (old, late):
            if process.pid is not None:
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
    assert old.exitcode == late.exitcode == 0
    assert _tickets() == []


def test_fifo_admission_fills_all_slots_without_waiting_for_earlier_calls_to_finish(ctx):
    """Serializing execution instead of admission would leave three slots idle."""
    ctx.config.codex.max_concurrent = 4
    mp = multiprocessing.get_context("spawn")
    admitted, release = mp.Queue(), mp.Event()
    attempts = [mp.Event() for _ in range(5)]
    processes = [mp.Process(target=_slot_process, args=(ctx, i, admitted, release, attempts[i]))
                 for i in range(5)]
    try:
        for process in processes[:4]:
            process.start()
        assert {admitted.get(timeout=5) for _ in range(4)} == {0, 1, 2, 3}
        processes[4].start()
        assert attempts[4].wait(5)
        with pytest.raises(queue.Empty):
            admitted.get(timeout=.1)
        release.set()
        assert admitted.get(timeout=5) == 4
    finally:
        release.set()
        for process in processes:
            if process.pid is not None:
                process.join(5)
                if process.is_alive():
                    process.kill()
                    process.join(5)
    assert all(process.exitcode == 0 for process in processes)
    assert _tickets() == []


@pytest.mark.parametrize("reason", ["cancel", "timeout"])
def test_departing_head_does_not_block_next_request(ctx, reason):
    """A canceled or expired head must remove its ticket and never consume capacity."""
    ctx.config.codex.max_concurrent = 1
    occupied = CodexBackend(ctx)._acquire_slot(5)
    ctx.cancellation = Future()
    backend = CodexBackend(ctx)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(backend._acquire_slot, .1 if reason == "timeout" else 5)
        try:
            deadline = time.monotonic() + 3
            while not _tickets() and not future.done() and time.monotonic() < deadline:
                time.sleep(.005)
            if reason == "cancel":
                ctx.cancellation.cancel()
            with pytest.raises(CancelledError if reason == "cancel" else BudgetExceeded):
                future.result(timeout=3)
        finally:
            ctx.cancellation.cancel()
            occupied.close()
    ctx.cancellation = None
    with backend._acquire_slot(.5):
        assert _tickets() == []


@pytest.mark.parametrize("kill_state", ["queued", "admitted"])
def test_killed_process_releases_ticket_or_slot_for_successor(ctx, kill_state):
    """SIGKILL cannot run finally: progress must rely on OS liveness locks."""
    ctx.config.codex.max_concurrent = 1
    mp = multiprocessing.get_context("spawn")
    admitted, release, attempted = mp.Queue(), mp.Event(), mp.Event()
    occupied = CodexBackend(ctx)._acquire_slot(5) if kill_state == "queued" else None
    process = mp.Process(target=_slot_process, args=(ctx, "victim", admitted, release, attempted))
    process.start()
    try:
        if kill_state == "admitted":
            assert admitted.get(timeout=5) == "victim"
        else:
            assert attempted.wait(5)
        process.kill()
        process.join(5)
        if occupied:
            occupied.close()
        with CodexBackend(ctx)._acquire_slot(.5):
            assert _tickets() == []
    finally:
        if occupied:
            occupied.close()
        if process.is_alive():
            process.kill()
        process.join(5)
    assert process.exitcode != 0


@pytest.mark.parametrize("reason", ["cancel", "timeout"])
def test_waiting_for_queue_mutex_obeys_cancellation_and_deadline(ctx, monkeypatch, reason):
    """A blocking queue mutex must not introduce an uncancellable, unbounded wait."""
    ctx.cancellation = Future()
    waiting = threading.Event()
    real_sleep = time.sleep

    def observed_sleep(delay):
        waiting.set()
        real_sleep(delay)

    monkeypatch.setattr(codex_backend, "time", SimpleNamespace(
        monotonic=time.monotonic, sleep=observed_sleep))
    with (_queue_directory() / "queue.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(CodexBackend(ctx)._acquire_slot, .1 if reason == "timeout" else 5)
            try:
                assert waiting.wait(3)
                if reason == "cancel":
                    ctx.cancellation.cancel()
                with pytest.raises(CancelledError if reason == "cancel" else BudgetExceeded):
                    future.result(timeout=3)
            finally:
                ctx.cancellation.cancel()
    ctx.cancellation = None
    with CodexBackend(ctx)._acquire_slot(.5):
        assert _tickets() == []


@pytest.mark.parametrize("stage", ["ticket", "slot"])
def test_cancellation_racing_registration_or_claim_releases_all_locks(ctx, monkeypatch, stage):
    """Cancellation after successful flock must not return a slot or leak a ticket."""
    ctx.config.codex.max_concurrent = 1
    ctx.cancellation = Future()
    real_flock = fcntl.flock
    fired = False

    def cancel_after_claim(file, operation):
        nonlocal fired
        result = real_flock(file, operation)
        name = Path(file.name).name
        target = name.startswith("wait-") if stage == "ticket" else name == "0"
        if not fired and operation == fcntl.LOCK_EX | fcntl.LOCK_NB and target:
            fired = True
            ctx.cancellation.cancel()
        return result

    monkeypatch.setattr(fcntl, "flock", cancel_after_claim)
    with pytest.raises(CancelledError):
        CodexBackend(ctx)._acquire_slot(.5)
    assert fired
    assert _tickets() == []
    ctx.cancellation = None
    with CodexBackend(ctx)._acquire_slot(.5):
        pass


def _crash_during_registration(ctx, created, release):
    real_flock = fcntl.flock

    def stop_before_ticket_lock(file, operation):
        if Path(file.name).name.startswith("wait-"):
            created.set()
            assert release.wait(5)
        return real_flock(file, operation)

    fcntl.flock = stop_before_ticket_lock
    CodexBackend(ctx)._acquire_slot(5)


def test_killed_registration_releases_mutex_and_unowned_ticket(ctx):
    """A crash between create and flock must not corrupt a counter or strand a head."""
    mp = multiprocessing.get_context("spawn")
    created, release = mp.Event(), mp.Event()
    process = mp.Process(target=_crash_during_registration, args=(ctx, created, release))
    process.start()
    try:
        assert created.wait(5)
        process.kill()
        process.join(5)
        with CodexBackend(ctx)._acquire_slot(.5):
            assert _tickets() == []
    finally:
        if process.is_alive():
            process.kill()
        process.join(5)
    assert process.exitcode != 0


def test_malformed_live_ticket_fails_visibly_without_deleting_ownership(ctx):
    """Unexpected queue state must not silently evict a potentially live owner."""
    path = _queue_directory() / "wait-malformed"
    try:
        with path.open("x") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with pytest.raises(ValueError, match="Invalid Codex slot queue ticket"):
                CodexBackend(ctx)._acquire_slot(.5)
            assert path.exists()
            with path.open("r+") as probe:
                with pytest.raises(BlockingIOError):
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        path.unlink(missing_ok=True)
    with CodexBackend(ctx)._acquire_slot(.5):
        assert _tickets() == []
