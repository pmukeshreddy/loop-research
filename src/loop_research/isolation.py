"""Fail-closed macOS isolation for the untrusted, full-Python LocalREPL worker.

Seatbelt enforces these restrictions in the kernel, including for subprocesses
and symlink targets. The trusted host owns gold, grades, archives, and tools;
only a fresh worker directory is writable. No host environment is inherited.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


_SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
_SOURCE_ROOT = Path(__file__).resolve().parents[1]


def _read_roots() -> tuple[Path, ...]:
    return tuple(dict.fromkeys(Path(path).resolve() for path in (
        "/System", "/usr", "/bin", "/sbin", "/Library", "/opt/homebrew",
        sys.base_prefix, sys.prefix, _SOURCE_ROOT, "/private/etc",
        "/private/var/db/timezone", "/dev",
    )))


def _workdir(workdir: Path) -> Path:
    workdir = Path(workdir).resolve(strict=True)
    if not workdir.is_dir():
        raise ValueError("Worker directory must be an existing directory")
    for protected in _read_roots():
        if workdir.is_relative_to(protected) or protected.is_relative_to(workdir):
            raise ValueError(f"Worker directory overlaps read-only runtime/source: {protected}")
    return workdir


def isolated_command(workdir: Path, command: list[str]) -> list[str]:
    """Wrap a worker command in Seatbelt; unsupported hosts never run it bare.

    The caller must also use ``worker_env``, set cwd to ``workdir``, and retain
    subprocess' default ``close_fds=True``. Only the intended broker sockets
    should be exposed to the worker. Loopback TCP supports RLM's LMHandler;
    Unix socket access is confined to the worker directory.
    """
    if sys.platform != "darwin":
        raise RuntimeError("Full-Python REPL isolation requires macOS Seatbelt")
    if not _SANDBOX_EXEC.is_file() or not os.access(_SANDBOX_EXEC, os.X_OK):
        raise RuntimeError("macOS Seatbelt sandbox-exec is unavailable; refusing an unisolated worker")
    if not command:
        raise ValueError("Worker command must not be empty")
    workdir = _workdir(workdir)
    quote = lambda path: json.dumps(str(path), ensure_ascii=False)
    read_paths = " ".join(f"(subpath {quote(path)})" for path in (*_read_roots(), workdir))
    profile = f"""(version 1)
(deny default)
(allow process-fork process-exec)
(allow sysctl-read)
(allow file-map-executable)
(allow file-read-metadata)
; dyld needs the root directory itself, never its recursive contents.
(allow file-read* (literal "/") {read_paths})
(allow file-write* (subpath {quote(workdir)}) (literal "/dev/null"))
(allow network-outbound (remote ip "localhost:*") (subpath {quote(workdir)}))
(allow network-inbound network-bind (local ip "localhost:*") (subpath {quote(workdir)}))
"""
    return [str(_SANDBOX_EXEC), "-p", profile, *map(str, command)]


def worker_env(workdir: Path) -> dict[str, str]:
    """Construct the worker environment from an allowlist, excluding secrets."""
    workdir = _workdir(workdir)
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(workdir),
        "TMPDIR": str(workdir),
        "PYTHONPATH": str(_SOURCE_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
    }


def verify_isolation() -> str:
    """Run an offline kernel-enforcement probe, raising on any failed check."""
    with tempfile.TemporaryDirectory(prefix="lr-probe-", dir="/tmp") as temporary:
        root = Path(temporary).resolve()
        workdir = root / "worker"
        workdir.mkdir()
        gold = root / "synthetic-gold.json"
        gold.write_text("private isolation probe fixture")
        (workdir / "gold-link").symlink_to(gold)
        code = r'''
import asyncio, builtins, os, pathlib, subprocess, sys, threading
from rlm.environments.local_repl import LocalREPL

for path in (pathlib.Path(sys.argv[1]), pathlib.Path("gold-link")):
    try:
        path.read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError("protected data is readable")
try:
    fd = os.open(sys.argv[2], os.O_WRONLY)
except PermissionError:
    pass
else:
    os.close(fd)
    raise AssertionError("trusted source is writable")
with LocalREPL() as repl:
    repl.globals["__builtins__"] = vars(builtins).copy()
    result = repl.execute_code("class Probe:\n    value = 42\nassert eval('Probe.value') == 42\n")
    assert not result.stderr, result.stderr
seen = []
thread = threading.Thread(target=lambda: seen.append(True))
thread.start()
thread.join()
assert seen == [True]
async def probe():
    await asyncio.sleep(0)
    return True
assert asyncio.run(probe())
pathlib.Path("scratch.txt").write_text("working")
assert pathlib.Path("scratch.txt").read_text() == "working"
child_code = """
import pathlib, sys
try:
    pathlib.Path(sys.argv[1]).read_bytes()
except PermissionError:
    print("child denied")
else:
    raise AssertionError("child escaped isolation")
"""
child = subprocess.run([sys.executable, "-c", child_code, sys.argv[1]], capture_output=True, text=True)
assert child.returncode == 0 and child.stdout.strip() == "child denied", child.stderr
print("ISOLATION_OK")
'''
        try:
            result = subprocess.run(
                isolated_command(workdir, [sys.executable, "-c", code, str(gold), __file__]),
                cwd=workdir, env=worker_env(workdir), capture_output=True, text=True, timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"Seatbelt isolation probe could not complete: {exc}") from exc
        if result.returncode != 0 or result.stdout.strip() != "ISOLATION_OK":
            raise RuntimeError(
                f"Seatbelt isolation probe failed (exit {result.returncode}): "
                f"{result.stderr[-4000:]} {result.stdout[-1000:]}"
            )
    return (
        "macOS Seatbelt verified: full-Python LocalREPL, threads, asyncio, and scratch I/O work; "
        "protected reads, symlink reads, source writes, and child-process protected reads denied."
    )
