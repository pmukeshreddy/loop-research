from concurrent.futures import ThreadPoolExecutor
import json
import queue
import socket
import tempfile
import threading
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


def test_simultaneous_clients_can_queue_before_server_accepts():
    count = 16
    barrier = threading.Barrier(count + 1)
    attempted = queue.Queue()
    with tempfile.TemporaryDirectory(prefix='lr-test-', dir='/tmp') as tmp:
        path = Path(tmp) / 'bridge.sock'
        server = Server(path, lambda method, args, kwargs: args[0], socket_timeout_s=5)

        def client(index):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                barrier.wait(timeout=5)
                try:
                    sock.connect(str(path))
                except OSError as exc:
                    attempted.put(exc)
                    raise
                attempted.put(None)
                sock.sendall((json.dumps({'method': 'echo', 'args': [index], 'kwargs': {}}) + '\n').encode())
                with sock.makefile('rb') as reader:
                    return json.loads(reader.readline())['result']

        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(client, index) for index in range(count)]
            barrier.wait(timeout=5)
            # The listener is active but its accept loop has not started. Every connection
            # must fit in the OS queue; thread scheduling cannot hide a small backlog.
            outcomes = [attempted.get(timeout=5) for _ in range(count)]
            with server:
                failures = [str(value) for value in outcomes if value is not None]
                assert failures == [], failures
                assert [future.result(timeout=5) for future in futures] == list(range(count))
