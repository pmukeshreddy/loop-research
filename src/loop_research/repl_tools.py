import json
import threading
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

    def persist(self):
        write_json(self.ctx.path / "tool_cache.json", self.cache)
        write_json(self.ctx.path / "url_ledger.json", sorted(self.ledger))

    def search(self, query: str, k: int = 8) -> list[dict]:
        """Search the live web; return title, URL and snippet for up to k real hits."""
        if not isinstance(query, str) or not query.strip() or not 1 <= k <= 50:
            raise ValueError("Nonempty query and 1 <= k <= 50 required")
        key = json.dumps(["search", " ".join(query.split()).casefold(), k])
        with self.lock:
            if key in self.cache:
                return self.cache[key]
            schema = {"type": "object", "additionalProperties": False, "required": ["results"],
                      "properties": {"results": {"type": "array", "items": {"type": "object",
                       "additionalProperties": False, "required": ["title", "url", "snippet"],
                       "properties": {x: {"type": "string"} for x in ("title", "url", "snippet")}}}}}
            text = self.backend.complete(f"Search the live web for {query!r}. Return at most {k} results. "
                "Use only URLs actually returned by web search. Never invent a URL or snippet.",
                purpose="search", web=True, schema=schema, model=self.ctx.config.models.sub)
            hits = json.loads(text)["results"]
            result = []
            for hit in hits:
                if not all(isinstance(hit.get(x), str) for x in ("title", "url", "snippet")):
                    continue
                try:
                    url = normalized_url(hit["url"])
                except ValueError:
                    continue
                self.ledger.add(url)
                result.append({x: hit[x] for x in ("title", "url", "snippet")})
                if len(result) == k:
                    break
            self.cache[key] = result
            self.persist()
            return result

    def fetch(self, url: str, focus: str = "") -> str:
        """Return model-rendered page text (not raw HTML), or FETCH_FAILED."""
        url = normalized_url(url)
        key = json.dumps(["fetch", url, " ".join(focus.split())])
        with self.lock:
            if key in self.cache:
                return self.cache[key]
            result = self.backend.complete(f"Open this exact URL with the web tool: {url}\n"
                f"Focus: {focus}\nCopy relevant page text as faithfully as possible in plain text. "
                "Preserve wording, figures, context, qualifications and dates. Do not paraphrase, "
                "infer missing text or invent quotations. If inaccessible, return exactly FETCH_FAILED.",
                purpose="fetch", web=True, model=self.ctx.config.models.sub).strip()
            if not result:
                result = "FETCH_FAILED"
            if result != "FETCH_FAILED":
                self.ledger.add(url)
            self.cache[key] = result
            self.persist()
            return result

    def injected(self):
        return {"search": {"tool": self.search, "description": self.search.__doc__},
                "fetch": {"tool": self.fetch, "description": self.fetch.__doc__}}
