import socket
import tempfile
import time
from pathlib import Path

from loop_research.bridge import Server, Client


def test_partial_request_cannot_block_server_shutdown():
    with tempfile.TemporaryDirectory(prefix='lr-test-', dir='/tmp') as tmp:
        path = Path(tmp) / 'bridge.sock'
        started = time.monotonic()
        with Server(path, lambda *args: True):
            stalled = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            stalled.connect(str(path))
            stalled.sendall(b'{')
            assert Client(path).call('ping') is True
        stalled.close()
        assert time.monotonic() - started < 2
