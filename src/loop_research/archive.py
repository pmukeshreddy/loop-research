"""Run archives and cancellable worker processes. No benchmark imports."""
from concurrent.futures import CancelledError, Future
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import threading
from .config import Config
from .trace import Trace


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
        name = f.name
    os.replace(name, path)


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def append_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_jsonl(path: Path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def count_codex_calls(directory: Path, *, exclude_purposes=()):
    """Count dispatched attempts, including interrupted calls, once per identity."""
    calls = {record["call_id"]: record for path in (directory / "codex_attempts").glob("*.json")
             if (record := read_json(path)) is not None}
    legacy = []
    for record in read_jsonl(directory / "codex_calls.jsonl"):
        if record.get("call_id"):
            calls[record["call_id"]] = record
        else:
            legacy.append(record)
    return sum(record["purpose"] not in exclude_purposes for record in [*calls.values(), *legacy])


@dataclass
class RunContext:
    root: Path
    run_id: str
    config: Config
    task_id: str | None = None
    cancellation: Future | None = field(default=None, repr=False, compare=False)

    trace: Trace = field(default_factory=Trace, repr=False, compare=False)

    def __post_init__(self):
        self.root = self.root.resolve()
        for value in (self.run_id, self.task_id):
            if value is not None and (Path(value).name != value or value in (".", "..", "")):
                raise ValueError("Archive identifiers must be path-safe")

    @property
    def run_dir(self):
        return self.root / "runs" / self.run_id

    @property
    def path(self):
        return self.run_dir / self.task_id if self.task_id else self.run_dir

    def task(self, task_id):
        return RunContext(self.root, self.run_id, self.config, task_id, self.cancellation, self.trace)

    def check_cancelled(self):
        if self.cancellation is not None and self.cancellation.cancelled():
            raise CancelledError("Run cancelled")

    def run_process(self, command, *, input=None, capture_output=False, timeout=None, trace_component=None, **kwargs):
        """Run a child, terminating it and its owned process group on cancellation."""
        self.check_cancelled()
        if input is not None:
            kwargs["stdin"] = subprocess.PIPE
        if capture_output:
            kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        session = kwargs.pop("start_new_session", self.cancellation is not None)
        process = subprocess.Popen(command, start_new_session=session, **kwargs)
        if trace_component:
            self.trace.emit(trace_component, "spawned", pid=process.pid)
        finished = stopped = False
        cleanup_lock = threading.Lock()

        def stop():
            nonlocal stopped
            # Timeout cleanup and Future cancellation can race before the
            # communicate/wait drain completes. Signal an owned group once.
            with cleanup_lock:
                if finished or stopped:
                    return
                try:
                    if session:
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                except ProcessLookupError:
                    pass  # The child may exit between cancellation and cleanup.
                stopped = True

        if self.cancellation is not None:
            self.cancellation.add_done_callback(lambda _: stop())
        stdout = stderr = None
        try:
            if capture_output or input is not None:
                stdout, stderr = process.communicate(input, timeout=timeout)
                code = process.returncode
            else:
                code = process.wait(timeout=timeout)
        except BaseException:
            stop()
            if capture_output or input is not None:
                process.communicate()
            else:
                process.wait()
            raise
        finally:
            with cleanup_lock:
                finished = True
        self.check_cancelled()
        return subprocess.CompletedProcess(command, code, stdout, stderr)

    def save(self, name, value):
        write_json(self.path / name, value)

    def load(self, name, default=None):
        return read_json(self.path / name, default)

    def initialize(self, harness_sha, **metadata):
        self.path.mkdir(parents=True, exist_ok=True)
        snapshot = self.config.model_dump()
        existing = self.load("config.json")
        if existing is not None and Config.model_validate(existing).model_dump() != snapshot:
            raise ValueError("Cannot resume with changed configuration")
        if existing is None:
            self.save("config.json", snapshot)
        sha_file = self.path / "harness_sha.txt"
        if sha_file.exists() and sha_file.read_text().strip() != harness_sha:
            raise ValueError("Run harness identity changed")
        sha_file.write_text(harness_sha + "\n")
        if not (self.path / "run_summary.json").exists():
            self.save("run_summary.json", {"created": stamp(), "harness_sha": harness_sha, **metadata})


class GradeContext(RunContext):
    @property
    def run_dir(self):
        return self.root / 'reports' / self.run_id / 'grading'

    def task(self, task_id):
        return GradeContext(self.root, self.run_id, self.config, task_id, self.cancellation, self.trace)
