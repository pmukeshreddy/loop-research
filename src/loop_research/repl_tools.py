import json
import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit
from .archive import read_json, write_json


def normalized_url(url):
    try:
        parts = urlsplit(url.strip())
        if parts.scheme.lower() not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            raise ValueError("Expected a public HTTP(S) URL")
        if any(c.isspace() for c in url):
            raise ValueError("Whitespace in URL")
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))
    except (TypeError, AttributeError) as exc:
        raise ValueError("Invalid URL") from exc


class ResearchTools:
    def __init__(self, backend, ctx):
        self.backend, self.ctx = backend, ctx
        self.cache = {key: value for key, value in read_json(ctx.path / "tool_cache.json", {}).items()
                      if value != "FETCH_FAILED"}
        self.ledger = set(read_json(ctx.path / "url_ledger.json", []))
        self.lock = threading.RLock()
        self.pending = {}
        self.pending_fetches = {}
        self.active_fetches = {}
        self.evidence = read_json(ctx.path / 'evidence.json', {
            'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'failures': []})
        self.evidence.setdefault('fetches', [])
        self.evidence.setdefault('dropped_search_hits', [])
        self.entities = {entity for d in self.evidence['discoveries'] for entity in d['entities']}
        if ctx.cancellation is not None:
            ctx.cancellation.add_done_callback(self._cancel_fetches)

    def persist(self):
        write_json(self.ctx.path / "tool_cache.json", self.cache)
        write_json(self.ctx.path / "url_ledger.json", sorted(self.ledger))
        write_json(self.ctx.path / 'evidence.json', self.evidence)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.evidence))

    def _new_fetch(self, url, focus, source):
        request = {'id': len(self.evidence['fetches']) + 1, 'url': url, 'focus': focus,
                   'source': source, 'status': 'pending'}
        self.evidence['fetches'].append(request)
        self.active_fetches[request['id']] = request
        return request

    def _finish_fetch(self, request, status, *, reason=None, error=None):
        request['status'] = status
        self.active_fetches.pop(request['id'], None)
        if reason is not None:
            request['reason'] = reason
            failure = {'operation': 'fetch', 'url': request['url'], 'request_id': request['id'],
                       'source': request['source'], 'reason': reason}
            if error is not None:
                request['error'] = failure['error'] = error
            self.evidence['failures'].append(failure)

    def _record_fetch_attempt(self, key, event):
        with self.lock:
            self.ctx.check_cancelled()
            request = self.pending_fetches[key]
            attempts = request.setdefault('attempts', [])
            attempt = next((item for item in attempts if item['call_id'] == event['call_id']), None)
            if attempt is None:
                attempt = {'request_id': request['id']}
                attempts.append(attempt)
            attempt.update(event)
            if event['status'] == 'failed':
                self.evidence['failures'].append({'operation': 'fetch', 'url': request['url'],
                    'request_id': request['id'], 'source': 'backend', 'reason': 'backend_attempt_failed',
                    **event})
            self.persist()

    def _cancel_fetches(self, cancellation):
        if not cancellation.cancelled():
            return
        # Cancellation owns this final audit write. Completed backend calls must
        # still pass check_cancelled before changing any evidence or cache state.
        with self.lock:
            pending = list(self.active_fetches.values())
            for request in pending:
                self._finish_fetch(request, 'cancelled', reason='cancelled', error='Run cancelled')
            if pending:
                self.persist()

    def _cached(self, key, call):
        operation, target, *options = json.loads(key)
        with self.lock:
            self.ctx.check_cancelled()
            pending = self.pending.get(key)
            request = None
            if operation == 'fetch':
                source = 'cache' if key in self.cache else 'shared' if pending is not None else 'backend'
                request = self._new_fetch(target, options[0], source)
            if key in self.cache:
                if request is not None:
                    owner = next((item for item in reversed(self.evidence['fetches'])
                        if item['source'] == 'backend' and item['status'] == 'succeeded'
                        and item['url'] == target and item['focus'] == options[0]), None)
                    if owner is not None:
                        request['owner_id'] = owner['id']
                    self._finish_fetch(request, 'succeeded')
                    self.persist()
                return self.cache[key]
            if pending is None:
                future = self.pending[key] = Future()
                if request is not None:
                    self.pending_fetches[key] = request
            elif request is not None:
                request['owner_id'] = self.pending_fetches[key]['id']
            if request is not None:
                self.persist()
        try:
            result, urls = (pending.result(), []) if pending is not None else call()
            with self.lock:
                self.ctx.check_cancelled()
                failed = operation == 'fetch' and result == 'FETCH_FAILED'
                if pending is None and not failed:
                    self.cache[key] = result
                    self.ledger.update(urls)
                    if request is not None:
                        self.evidence['fetched'].setdefault(target, []).append(result)
                if request is not None:
                    self._finish_fetch(request, 'failed' if failed else 'succeeded',
                                       reason='fetch_failed' if failed else None)
                self.persist()
            if pending is None:
                future.set_result(result)
            return result
        except BaseException as exc:
            with self.lock:
                try:
                    self.ctx.check_cancelled()
                except CancelledError:
                    pass
                else:
                    if request is not None:
                        cancelled = isinstance(exc, CancelledError)
                        self._finish_fetch(request, 'cancelled' if cancelled else 'failed',
                                           reason='cancelled' if cancelled else 'backend_error', error=str(exc))
                    elif pending is None:
                        self.evidence['failures'].append({'operation': operation, 'target': target, 'error': str(exc)})
                    self.persist()
            # Release every waiter even if the owner is interrupted.
            if pending is None:
                future.set_exception(exc)
            raise
        finally:
            if pending is None:
                with self.lock:
                    del self.pending[key]
                    self.pending_fetches.pop(key, None)

    def search(self, query: str, k: int = 8) -> list[dict]:
        """Search the live web; return title, URL and snippet for up to k real hits."""
        if not isinstance(query, str) or not query.strip() or not 1 <= k <= 50:
            raise ValueError("Nonempty query and 1 <= k <= 50 required")
        key = json.dumps(["search", " ".join(query.split()).casefold(), k])

        def call():
            schema = {"type": "object", "additionalProperties": False, "required": ["results"],
                      "properties": {"results": {"type": "array", "items": {"type": "object",
                       "additionalProperties": False, "required": ["title", "url", "snippet"],
                       "properties": {x: {"type": "string"} for x in ("title", "url", "snippet")}}}}}
            text = self.backend.complete(f"Search the live web for {query!r}. Return at most {k} results. "
                "Use only URLs actually returned by web search. Never invent a URL or snippet.",
                purpose="search", web=True, schema=schema, model=self.ctx.config.models.sub)
            response = json.loads(text)
            if not isinstance(response, dict) or not isinstance(response.get('results'), list):
                raise ValueError('Search response must contain a results list')
            result, urls, dropped = [], [], []
            for index, hit in enumerate(response['results']):
                reason = None
                if not isinstance(hit, dict):
                    reason = 'malformed_hit'
                elif not all(isinstance(hit.get(x), str) for x in ("title", "url", "snippet")):
                    reason = 'malformed_fields'
                else:
                    try:
                        url = normalized_url(hit["url"])
                    except ValueError:
                        reason = 'invalid_url'
                    else:
                        if len(result) == k:
                            reason = 'excess_k'
                if reason is not None:
                    dropped.append({'query': query, 'index': index, 'hit': hit, 'reason': reason})
                    continue
                urls.append(url)
                result.append({x: hit[x] for x in ("title", "url", "snippet")})
            with self.lock:
                self.ctx.check_cancelled()
                self.evidence['searches'].append({'query': query, 'hits': len(result)})
                self.evidence['dropped_search_hits'].extend(dropped)
            return result, urls

        return self._cached(key, call)

    def search_many(self, queries: list[str], k: int = 8) -> list[list[dict]]:
        """Search concurrently and return one hit list per query in input order."""
        with ThreadPoolExecutor(max_workers=self.ctx.config.codex.max_concurrent) as pool:
            return list(pool.map(lambda query: self.search(query, k), queries))

    def fetch(self, url: str, focus: str = "") -> str:
        """Return model-rendered page text (not raw HTML), or FETCH_FAILED."""
        with self.lock:
            self.ctx.check_cancelled()
        try:
            normalized = normalized_url(url)
            if not isinstance(focus, str):
                raise ValueError('Expected focus text')
        except ValueError as exc:
            with self.lock:
                self.ctx.check_cancelled()
                request = self._new_fetch(url if isinstance(url, str) else repr(url),
                                          focus if isinstance(focus, str) else repr(focus), 'validation')
                self._finish_fetch(request, 'failed', reason='validation_error', error=str(exc))
                self.persist()
            raise
        url = normalized
        key = json.dumps(["fetch", url, " ".join(focus.split())])

        def call():
            result = self.backend.complete(f"Open this exact URL with the web tool: {url}\n"
                f"Focus: {focus}\nCopy relevant page text as faithfully as possible in plain text. "
                "Preserve wording, figures, context, qualifications and dates. Do not paraphrase, "
                "infer missing text or invent quotations. If inaccessible, return exactly FETCH_FAILED.",
                purpose="fetch", web=True, model=self.ctx.config.models.sub,
                on_attempt=lambda event: self._record_fetch_attempt(key, event)).strip()
            if not result:
                result = "FETCH_FAILED"
            opened = []
            for action in self.backend.last_web_actions:
                if action.get('type') == 'open_page' and action.get('url'):
                    try:
                        opened.append(normalized_url(action['url']))
                    except ValueError:
                        continue
            if url not in opened:
                result = 'FETCH_FAILED'
            return result, [url] if result != "FETCH_FAILED" else []

        return self._cached(key, call)

    def fetch_many(self, urls: list[str], focus: str = "") -> list[str]:
        """Fetch concurrently and return one page text or FETCH_FAILED per URL in input order."""
        with ThreadPoolExecutor(max_workers=self.ctx.config.codex.max_concurrent) as pool:
            return list(pool.map(lambda url: self.fetch(url, focus), urls))

    def check_constraint(self, row, constraint, verdict, url, quote):
        """Record a row path's constraint verdict and its fetched supporting quote."""
        if not all(isinstance(v, str) and v for v in (row, constraint, url, quote)) or type(verdict) is not bool:
            raise ValueError('Expected row/constraint ids, a boolean verdict, URL and quote')
        url = normalized_url(url)
        with self.lock:
            self.ctx.check_cancelled()
            if not any(quote in page for page in self.evidence['fetched'].get(url, [])):
                raise ValueError('Constraint quote must appear in fetched evidence')
            self.evidence['checks'].append({'row': row, 'constraint': constraint, 'verdict': verdict,
                                            'url': url, 'quote': quote})
            self.persist()
        return True

    def record_discovery(self, query, entities):
        """Record entity ids found by a search, including [] when discovery stalls."""
        if not isinstance(query, str) or not isinstance(entities, list) or not all(isinstance(e, str) and e.strip() for e in entities):
            raise ValueError('Expected query text and a list of entity ids')
        with self.lock:
            self.ctx.check_cancelled()
            if not any(s['query'] == query for s in self.evidence['searches']):
                raise ValueError('Query was not searched in this run')
            normalized = sorted({' '.join(e.split()).casefold() for e in entities})
            new = sorted(set(normalized) - self.entities)
            self.entities.update(normalized)
            self.evidence['discoveries'].append({'query': query, 'entities': normalized, 'new_entities': new})
            self.persist()
        return new

    def injected(self):
        return {tool.__name__: {"tool": tool, "description": tool.__doc__}
                for tool in (self.search, self.fetch, self.search_many, self.fetch_many,
                             self.check_constraint, self.record_discovery)}
