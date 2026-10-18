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
        self.cache = read_json(ctx.path / "tool_cache.json", {})
        self.ledger = set(read_json(ctx.path / "url_ledger.json", []))
        self.lock = threading.RLock()
        self.pending = {}
        self.evidence = read_json(ctx.path / 'evidence.json', {
            'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'failures': []})
        self.entities = {entity for d in self.evidence['discoveries'] for entity in d['entities']}

    def persist(self):
        write_json(self.ctx.path / "tool_cache.json", self.cache)
        write_json(self.ctx.path / "url_ledger.json", sorted(self.ledger))
        write_json(self.ctx.path / 'evidence.json', self.evidence)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.evidence))

    def _cached(self, key, call):
        with self.lock:
            self.ctx.check_cancelled()
            if key in self.cache:
                return self.cache[key]
            pending = self.pending.get(key)
            if pending is None:
                future = self.pending[key] = Future()
        if pending is not None:
            return pending.result()
        try:
            result, urls = call()
            with self.lock:
                self.ctx.check_cancelled()
                self.cache[key] = result
                self.ledger.update(urls)
                self.persist()
            future.set_result(result)
            return result
        except BaseException as exc:
            with self.lock:
                if not isinstance(exc, CancelledError):
                    try:
                        self.ctx.check_cancelled()
                    except CancelledError:
                        pass
                    else:
                        operation, target, *_ = json.loads(key)
                        self.evidence['failures'].append({'operation': operation, 'target': target, 'error': str(exc)})
                        self.persist()
            # Release every waiter even if the owner is interrupted.
            future.set_exception(exc)
            raise
        finally:
            with self.lock:
                del self.pending[key]

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
            hits = json.loads(text)["results"]
            result, urls = [], []
            for hit in hits:
                if not all(isinstance(hit.get(x), str) for x in ("title", "url", "snippet")):
                    continue
                try:
                    url = normalized_url(hit["url"])
                except ValueError:
                    continue
                urls.append(url)
                result.append({x: hit[x] for x in ("title", "url", "snippet")})
                if len(result) == k:
                    break
            with self.lock:
                self.ctx.check_cancelled()
                self.evidence['searches'].append({'query': query, 'hits': len(result)})
            return result, urls

        return self._cached(key, call)

    def search_many(self, queries: list[str], k: int = 8) -> list[list[dict]]:
        """Search concurrently and return one hit list per query in input order."""
        with ThreadPoolExecutor(max_workers=self.ctx.config.codex.max_concurrent) as pool:
            return list(pool.map(lambda query: self.search(query, k), queries))

    def fetch(self, url: str, focus: str = "") -> str:
        """Return model-rendered page text (not raw HTML), or FETCH_FAILED."""
        url = normalized_url(url)
        key = json.dumps(["fetch", url, " ".join(focus.split())])

        def call():
            result = self.backend.complete(f"Open this exact URL with the web tool: {url}\n"
                f"Focus: {focus}\nCopy relevant page text as faithfully as possible in plain text. "
                "Preserve wording, figures, context, qualifications and dates. Do not paraphrase, "
                "infer missing text or invent quotations. If inaccessible, return exactly FETCH_FAILED.",
                purpose="fetch", web=True, model=self.ctx.config.models.sub).strip()
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
            with self.lock:
                self.ctx.check_cancelled()
                if result == 'FETCH_FAILED':
                    self.evidence['failures'].append({'operation': 'fetch', 'url': url})
                else:
                    self.evidence['fetched'].setdefault(url, []).append(result)
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
