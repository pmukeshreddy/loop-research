"""JSON-only host bridge; the worker cannot supply paths or execute host code."""
import json
import socket
import socketserver
import threading
from .trace import Trace


class Server:
    def __init__(self, path, dispatch, *, socket_timeout_s, trace=None):
        trace = trace or Trace()
        active, lock = set(), threading.Lock()
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                with lock:
                    active.add(self.request)
                try:
                    self.request.settimeout(socket_timeout_s)
                    request = json.loads(self.rfile.readline())
                    method = request['method']
                    caller = ('REPL' if method.startswith(('tools.', 'harness.', 'refine.')) else
                              ('REPL' if request.get('kwargs', {}).get('purpose') == 'sub' else 'RLM iteration')
                              if method == 'complete' else 'Worker')
                    with trace.span('Bridge', 'rpc', parent=caller, method=method):
                        result = {'result': dispatch(method, request.get('args', []), request.get('kwargs', {}))}
                except Exception as exc:
                    result = {'error': f'{type(exc).__name__}: {exc}'}
                try:
                    self.wfile.write((json.dumps(result, ensure_ascii=False) + '\n').encode())
                except OSError:
                    return
                finally:
                    with lock:
                        active.discard(self.request)
        self.server = socketserver.ThreadingUnixStreamServer(str(path), Handler)
        self.server.daemon_threads = True
        self.active, self.lock = active, lock
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        with self.lock:
            for sock in self.active:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    continue
        self.server.server_close()
        self.thread.join()


class Client:
    def __init__(self, path):
        self.path = str(path)
        self.local = threading.local()

    def call(self, method, *args, **kwargs):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(self.path)
            sock.sendall((json.dumps({'method': method, 'args': args, 'kwargs': kwargs}) + '\n').encode())
            with sock.makefile('rb') as reader:
                response = json.loads(reader.readline())
        if 'error' in response:
            raise RuntimeError(response['error'])
        return response['result']

    def complete(self, prompt, *, purpose, model=None):
        response = self.call('complete', prompt, purpose=purpose, model=model)
        self.local.usage = response['usage']
        return response['text']

    @property
    def last_usage(self):
        return getattr(self.local, 'usage', None)


class Remote:
    def __init__(self, client, prefix, methods):
        self.client, self.prefix, self.methods = client, prefix, methods

    def __getattr__(self, method):
        if method not in self.methods:
            raise AttributeError(method)
        return lambda *args, **kwargs: self.client.call(self.prefix + method, *args, **kwargs)
