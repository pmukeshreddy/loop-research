"""Exercise the actual OS boundary, without model calls or research traffic."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading

import pytest


def run_python(workdir, code, *args):
    from loop_research.isolation import isolated_command, worker_env

    return subprocess.run(
        isolated_command(workdir, [sys.executable, "-c", code, *map(str, args)]),
        env=worker_env(workdir), cwd=workdir, capture_output=True, text=True, timeout=30,
    )


def assert_ok(result):
    assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)


def test_full_python_in_stock_localrepl(tmp_path):
    result = run_python(tmp_path, '''
import builtins
from rlm.environments.local_repl import LocalREPL
with LocalREPL() as repl:
    repl.globals["__builtins__"] = vars(builtins).copy()
    result = repl.execute_code(''' + repr('''
import asyncio, pathlib, subprocess, sys, threading
class Answer:
    value = 42
assert eval("Answer.value") == 42
exec(compile("created = 6 * 7", "<cell>", "exec"))
assert created == 42
assert globals() is locals()
values = []
t = threading.Thread(target=lambda: values.append(42))
t.start()
t.join()
assert values == [42]
async def answer():
    await asyncio.sleep(0)
    return 42
assert asyncio.run(answer()) == 42
p = pathlib.Path("answer.txt")
p.write_text("42")
assert p.read_text() == "42"
child = subprocess.run([sys.executable, "-c", "print(6 * 7)"], capture_output=True, text=True)
assert child.returncode == 0, child.stderr
assert child.stdout.strip() == "42"
print("FULL_PYTHON_OK")
''') + ''')
    assert not result.stderr, result.stderr
    assert "FULL_PYTHON_OK" in result.stdout, result
    print(result.stdout.strip())
''')
    assert_ok(result)
    assert result.stdout.strip() == "FULL_PYTHON_OK"


@pytest.mark.parametrize("protected", ["gold.json", "grades.json", "other_run/trace.json"])
def test_protected_data_denied_directly_and_through_symlink(tmp_path, protected):
    workdir = tmp_path / "worker"
    workdir.mkdir()
    secret = tmp_path / protected
    secret.parent.mkdir(exist_ok=True)
    secret.write_text("SYNTHETIC_PRIVATE_FIXTURE")
    (workdir / "shortcut").symlink_to(secret)
    result = run_python(workdir, '''
import errno, pathlib, sys
for path in (pathlib.Path(sys.argv[1]), pathlib.Path("shortcut")):
    try:
        path.read_text()
    except PermissionError as exc:
        assert exc.errno in (errno.EPERM, errno.EACCES)
    else:
        raise AssertionError("protected data readable: " + str(path))
print("DENIED")
''', secret)
    assert_ok(result)
    assert result.stdout.strip() == "DENIED"


def test_child_process_inherits_read_and_write_denials(tmp_path):
    workdir = tmp_path / "worker"
    workdir.mkdir()
    secret = tmp_path / "gold.json"
    secret.write_text("SYNTHETIC_PRIVATE_FIXTURE")
    result = run_python(workdir, '''
import subprocess, sys
code = """
import pathlib, sys
for mode in ("r", "w"):
    try:
        pathlib.Path(sys.argv[1]).open(mode)
    except PermissionError:
        pass
    else:
        raise AssertionError("child escaped isolation")
print("CHILD_DENIED")
"""
child = subprocess.run([sys.executable, "-c", code, sys.argv[1]], capture_output=True, text=True)
assert child.returncode == 0, child.stderr
print(child.stdout.strip())
''', secret)
    assert_ok(result)
    assert result.stdout.strip() == "CHILD_DENIED"
    assert secret.read_text() == "SYNTHETIC_PRIVATE_FIXTURE"


@pytest.mark.parametrize("relative", [
    "repl_tools.py", "benchmarks/widesearch/grader.py", "selfcheck.py",
])
def test_source_files_cannot_be_written(tmp_path, relative):
    source = Path(__file__).resolve().parents[1] / "src/loop_research" / relative
    # O_WRONLY without O_TRUNC cannot damage a source file even if isolation regresses.
    assert source.is_file(), source
    before = source.read_bytes()
    result = run_python(tmp_path, '''
import os, sys
try:
    fd = os.open(sys.argv[1], os.O_WRONLY)
except PermissionError:
    print("WRITE_DENIED")
else:
    os.close(fd)
    raise AssertionError("source writable")
''', source)
    assert_ok(result)
    assert result.stdout.strip() == "WRITE_DENIED"
    assert source.read_bytes() == before


def test_network_allows_local_brokers_and_denies_external_connect(tmp_path, monkeypatch):
    workdir = tmp_path / "worker"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    unix_path = Path("broker.sock")
    with socket.socket(socket.AF_UNIX) as unix_server, socket.socket() as tcp_server:
        unix_server.bind(str(unix_path))
        unix_server.listen()
        tcp_server.bind(("127.0.0.1", 0))
        tcp_server.listen()

        def reply(server):
            server.settimeout(15)
            with server.accept()[0] as connection:
                connection.sendall(b"broker-ok")

        threads = [threading.Thread(target=reply, args=(server,)) for server in (unix_server, tcp_server)]
        for thread in threads:
            thread.start()
        result = run_python(workdir, '''
import errno, socket, sys
with socket.socket(socket.AF_UNIX) as connection:
    connection.connect(sys.argv[1])
    assert connection.recv(100) == b"broker-ok"
with socket.create_connection(("127.0.0.1", int(sys.argv[2])), timeout=3) as connection:
    assert connection.recv(100) == b"broker-ok"
# TEST-NET-1 is a documentation-only destination. The kernel must reject the
# connect immediately with a permission error, before any connection attempt.
with socket.socket() as connection:
    connection.settimeout(1)
    try:
        connection.connect(("192.0.2.1", 443))
    except PermissionError as exc:
        assert exc.errno in (errno.EPERM, errno.EACCES)
    else:
        raise AssertionError("outbound connection allowed")
print("NETWORK_OK")
''', unix_path, tcp_server.getsockname()[1])
        for thread in threads:
            thread.join(timeout=16)
        assert_ok(result)
        assert result.stdout.strip() == "NETWORK_OK"


def test_stock_lmhandler_and_localrepl_communicate_inside_sandbox(tmp_path):
    result = run_python(tmp_path, '''
import builtins
from rlm.core.lm_handler import LMHandler
from rlm.core.types import ModelUsageSummary
from rlm.environments.local_repl import LocalREPL

class OfflineClient:
    model_name = "offline-socket-fixture"
    def completion(self, prompt):
        return "fixture:" + prompt
    async def acompletion(self, prompt):
        return self.completion(prompt)
    def get_last_usage(self):
        return ModelUsageSummary(total_calls=1, total_input_tokens=0, total_output_tokens=0)

handler = LMHandler(OfflineClient())
try:
    handler.start()
    with LocalREPL(lm_handler_address=handler.address) as repl:
        repl.globals["__builtins__"] = vars(builtins).copy()
        result = repl.execute_code("assert llm_query('probe') == 'fixture:probe'\\n"
                                   "assert llm_query_batched(['a', 'b']) == ['fixture:a', 'fixture:b']")
        assert not result.stderr, result.stderr
finally:
    handler.stop()
print("LMHANDLER_OK")
''')
    assert_ok(result)
    assert result.stdout.strip() == "LMHANDLER_OK"


def test_unix_socket_outside_worker_is_denied(tmp_path, monkeypatch):
    workdir = tmp_path / "worker"
    workdir.mkdir()
    monkeypatch.chdir(tmp_path)
    with socket.socket(socket.AF_UNIX) as host_socket:
        host_socket.bind("host.sock")
        host_socket.listen()
        result = run_python(workdir, '''
import socket
with socket.socket(socket.AF_UNIX) as connection:
    try:
        connection.connect("../host.sock")
    except PermissionError:
        print("HOST_SOCKET_DENIED")
    else:
        raise AssertionError("worker can connect to a host Unix socket")
''')
    assert_ok(result)
    assert result.stdout.strip() == "HOST_SOCKET_DENIED"


def test_worker_cannot_signal_host_process(tmp_path):
    # Signal zero checks permission without delivering a signal to the host.
    result = run_python(tmp_path, '''
import os, sys
try:
    os.kill(int(sys.argv[1]), 0)
except PermissionError:
    print("HOST_SIGNAL_DENIED")
else:
    raise AssertionError("worker may signal the trusted host")
''', os.getpid())
    assert_ok(result)
    assert result.stdout.strip() == "HOST_SIGNAL_DENIED"


def test_environment_excludes_host_secrets_and_python_injection(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-inherit")
    monkeypatch.setenv("PYTHONSTARTUP", "/host/injected.py")
    monkeypatch.setenv("PYTHONPATH", "/host/untrusted")
    result = run_python(tmp_path, "import json, os; print(json.dumps(dict(os.environ)))")
    assert_ok(result)
    environment = json.loads(result.stdout)
    assert "OPENAI_API_KEY" not in environment
    assert "PYTHONSTARTUP" not in environment
    assert "/host/untrusted" not in environment.get("PYTHONPATH", "")
    assert Path(environment["HOME"]) == tmp_path.resolve()
    assert Path(environment["TMPDIR"]) == tmp_path.resolve()


def test_unsupported_platform_fails_closed(tmp_path, monkeypatch):
    from loop_research import isolation
    monkeypatch.setattr(isolation.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="macOS|Darwin"):
        isolation.isolated_command(tmp_path, [sys.executable, "-c", "pass"])


def test_missing_sandbox_executable_fails_closed(tmp_path, monkeypatch):
    from loop_research import isolation
    monkeypatch.setattr(isolation, "_SANDBOX_EXEC", tmp_path / "missing-sandbox-exec")
    with pytest.raises(RuntimeError, match="unavailable"):
        isolation.isolated_command(tmp_path, [sys.executable, "-c", "pass"])


def test_workdir_must_not_expose_repository(tmp_path):
    from loop_research.isolation import isolated_command
    root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="work|directory|overlap"):
        isolated_command(root, [sys.executable, "-c", "pass"])


def test_offline_verification_probe():
    from loop_research.isolation import verify_isolation
    report = verify_isolation()
    assert "Seatbelt" in report
    assert "LocalREPL" in report
    assert "denied" in report
