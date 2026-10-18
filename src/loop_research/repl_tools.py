import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
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

    def persist(self):
        write_json(self.ctx.path / "tool_cache.json", self.cache)
        write_json(self.ctx.path / "url_ledger.json", sorted(self.ledger))

    def _cached(self, key, call):
        with self.lock:
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
                self.cache[key] = result
                self.ledger.update(urls)
                self.persist()
            future.set_result(result)
            return result
        except BaseException as exc:
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
            return result, urls

        return self._cached(key, call)

    def search_batched(self, queries: list[str], k: int = 8) -> list[list[dict]]:
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
            return result, [url] if result != "FETCH_FAILED" else []

        return self._cached(key, call)

    def fetch_batched(self, urls: list[str], focus: str = "") -> list[str]:
        """Fetch concurrently and return one page text or FETCH_FAILED per URL in input order."""
        with ThreadPoolExecutor(max_workers=self.ctx.config.codex.max_concurrent) as pool:
            return list(pool.map(lambda url: self.fetch(url, focus), urls))

    def injected(self):
        return {tool.__name__: {"tool": tool, "description": tool.__doc__}
                for tool in (self.search, self.fetch, self.search_batched, self.fetch_batched)}
