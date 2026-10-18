import socket
import tempfile
import time
from pathlib import Path

from loop_research.bridge import Server, Client


def test_partial_request_cannot_block_server_shutdown():
    with tempfile.TemporaryDirectory(prefix='lr-test-', dir='/tmp') as tmp:
        path = Path(tmp) / 'bridge.sock'
        started = time.monotonic()
        with Server(path, lambda *args: True, socket_timeout_s=5):
            stalled = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            stalled.connect(str(path))
            stalled.sendall(b'{')
            assert Client(path).call('ping') is True
        stalled.close()
        assert time.monotonic() - started < 2


def test_partial_request_uses_configured_socket_timeout():
    with tempfile.TemporaryDirectory(prefix='lr-test-', dir='/tmp') as tmp:
        path = Path(tmp) / 'bridge.sock'
        with Server(path, lambda *args: True, socket_timeout_s=.05):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stalled:
                stalled.settimeout(1)
                stalled.connect(str(path))
                stalled.sendall(b'{')
                assert b'TimeoutError' in stalled.recv(4096)
