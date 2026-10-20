from contextvars import copy_context
import json
import threading
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from urllib.parse import urlsplit, urlunsplit
from .archive import read_json, write_json
from .page_fetch import FETCH_PATH, FetchError, PageFetcher, verify_receipt
from .trace import observed


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
    def __init__(self, backend, ctx, *, fetcher=None):
        self.backend, self.ctx = backend, ctx
        self.fetcher = fetcher or PageFetcher(ctx)
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
        # Keep size observations outside evidence/self-check, which are model inputs.
        self.fetch_telemetry = {item['id']: item for item in
                                read_json(ctx.path / 'fetch_telemetry.json', [])}
        self.entities = {entity for d in self.evidence['discoveries'] for entity in d['entities']}
        if ctx.cancellation is not None:
            ctx.cancellation.add_done_callback(self._cancel_fetches)

    def persist(self):
        write_json(self.ctx.path / "tool_cache.json", self.cache)
        write_json(self.ctx.path / "url_ledger.json", sorted(self.ledger))
        write_json(self.ctx.path / 'evidence.json', self.evidence)
        write_json(self.ctx.path / 'fetch_telemetry.json', list(self.fetch_telemetry.values()))

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.evidence))

    def _new_fetch(self, url, focus, source):
        request = {'id': len(self.evidence['fetches']) + 1, 'url': url, 'focus': focus,
                   'source': source, 'status': 'pending', 'fetch_path': FETCH_PATH}
        self.evidence['fetches'].append(request)
        self.active_fetches[request['id']] = request
        self.fetch_telemetry[request['id']] = {**request, 'returned_chars': None,
            'evidence_eligible': False, 'raw_page_chars': None,
            'raw_page_chars_reason': 'fetch_not_completed'}
        return request

    def _finish_fetch(self, request, status, *, reason=None, error=None, returned=None):
        request['status'] = status
        self.active_fetches.pop(request['id'], None)
        measurement = self.fetch_telemetry[request['id']]
        measurement.update(status=status, returned_chars=len(returned) if returned is not None else None,
                           evidence_eligible=status == 'succeeded' and returned is not None)
        if 'owner_id' in request:
            measurement['owner_id'] = request['owner_id']
            owner = self.fetch_telemetry.get(request['owner_id'])
            if owner is not None:
                for key in ('raw_page_chars_reason', 'raw_page_chars', 'raw_page_bytes',
                            'readable_chars', 'receipt'):
                    if key in owner:
                        measurement[key] = owner[key]
        if measurement['raw_page_chars_reason'] == 'fetch_not_completed':
            measurement['raw_page_chars_reason'] = (
                'cached_fetch_has_no_archived_receipt' if request['source'] == 'cache'
                else 'no_completed_download')
        if reason is not None:
            request['reason'] = reason
            failure = {'operation': 'fetch', 'url': request['url'], 'request_id': request['id'],
                       'source': request['source'], 'reason': reason}
            if error is not None:
                request['error'] = failure['error'] = error
            self.evidence['failures'].append(failure)

    def _record_download(self, key, receipt):
        with self.lock:
            self.ctx.check_cancelled()
            request = self.pending_fetches[key]
            if receipt is None:
                raise ValueError('Direct fetch must supply a durable download receipt')
            request['receipt_id'] = receipt['id']
            measurement = self.fetch_telemetry[request['id']]
            measurement.update(receipt=receipt, raw_page_bytes=receipt.get('raw_page_bytes'),
                raw_page_chars=receipt.get('raw_page_chars'), readable_chars=receipt.get('readable_chars'),
                raw_page_chars_reason=('decoded_download' if receipt.get('raw_page_chars') is not None
                    else 'binary_document' if receipt.get('status') == 'succeeded' else 'download_failed'))
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

    def _cached(self, key, call, *, focus=''):
        operation, target, *options = json.loads(key)
        with self.lock:
            self.ctx.check_cancelled()
            pending = self.pending.get(key)
            self.ctx.trace.emit('tools.' + operation, 'cache', target=target,
                                cache='hit' if key in self.cache else 'shared' if pending is not None else 'miss')
            request = None
            if operation == 'fetch':
                source = 'cache' if key in self.cache else 'shared' if pending is not None else 'backend'
                request = self._new_fetch(target, focus, source)
            if key in self.cache:
                if request is not None:
                    owner = next((item for item in reversed(self.evidence['fetches'])
                        if item['source'] == 'backend' and item['status'] == 'succeeded'
                        and item['url'] == target and item.get('fetch_path') == FETCH_PATH), None)
                    if owner is not None:
                        request['owner_id'] = owner['id']
                    try:
                        receipt = self.fetch_telemetry.get(owner['id'], {}).get('receipt') if owner else None
                        if receipt is None or receipt.get('requested_url') != target:
                            raise FetchError('receipt_integrity', 'Direct cache has no matching owner receipt')
                        verify_receipt(self.ctx.path, receipt, text=self.cache[key])
                    except FetchError as error:
                        self._finish_fetch(request, 'failed', reason=error.reason, error=error.error,
                                           returned='FETCH_FAILED')
                        self.cache.pop(key)
                        self.persist()
                        return 'FETCH_FAILED'
                    self._finish_fetch(request, 'succeeded', returned=self.cache[key])
                    self.persist()
                return self.cache[key]
            if pending is None:
                future = self.pending[key] = Future()
                if request is not None:
                    self.pending_fetches[key] = request
            elif request is not None:
                request['owner_id'] = self.pending_fetches[key]['id']
                self.fetch_telemetry[request['id']]['owner_id'] = request['owner_id']
            if request is not None:
                self.persist()
        try:
            result, urls = (pending.result(), []) if pending is not None else call()
            if pending is None and self.ctx.trace.enabled and operation == 'search':
                self.ctx.trace.emit('tools.' + operation, 'web', target=target,
                    urls_opened=[a['url'] for a in self.backend.last_web_actions
                                 if a.get('type') == 'open_page' and a.get('url')])
            with self.lock:
                self.ctx.check_cancelled()
                failed = operation == 'fetch' and result == 'FETCH_FAILED'
                if pending is None and not failed:
                    self.cache[key] = result
                    self.ledger.update(urls)
                    if request is not None:
                        self.evidence['fetched'].setdefault(target, []).append(result)
                if request is not None:
                    owner = self.evidence['fetches'][request['owner_id'] - 1] if 'owner_id' in request else {}
                    self._finish_fetch(request, 'failed' if failed else 'succeeded',
                                       reason=owner.get('reason', 'fetch_failed') if failed else None,
                                       error=owner.get('error') if failed else None, returned=result)
                self.persist()
            if pending is None:
                future.set_result(result)
            return result
        except FetchError as exc:
            with self.lock:
                self.ctx.check_cancelled()
                self._finish_fetch(request, 'failed', reason=exc.reason, error=exc.error, returned='FETCH_FAILED')
                self.persist()
            if pending is None:
                future.set_result('FETCH_FAILED')
            return 'FETCH_FAILED'
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

    @observed('tools.search')
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

    @observed('tools.search_many')
    def search_many(self, queries: list[str], k: int = 8) -> list[list[dict]]:
        """Search concurrently and return one hit list per query in input order."""
        context = copy_context()
        with ThreadPoolExecutor(max_workers=self.ctx.config.codex.max_concurrent) as pool:
            return list(pool.map(lambda query: context.copy().run(self.search, query, k), queries))

    @observed('tools.fetch')
    def fetch(self, url: str, focus: str = "") -> str:
        """Directly download full readable page text; focus never filters it. Failures return FETCH_FAILED."""
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
        key = json.dumps(["fetch", url, FETCH_PATH])

        def call():
            try:
                page = self.fetcher.fetch(url)
            except FetchError as error:
                self._record_download(key, error.receipt)
                raise
            self._record_download(key, page.receipt)
            return page.text, [url]

        return self._cached(key, call, focus=focus)

    @observed('tools.fetch_many')
    def fetch_many(self, urls: list[str], focus: str = "") -> list[str]:
        """Fetch concurrently and return one page text or FETCH_FAILED per URL in input order."""
        context = copy_context()
        with ThreadPoolExecutor(max_workers=self.ctx.config.codex.max_concurrent) as pool:
            return list(pool.map(lambda url: context.copy().run(self.fetch, url, focus), urls))

    @observed('tools.check_constraint')
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

    @observed('tools.record_discovery')
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
