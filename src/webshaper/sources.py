"""Immutable captures. Snippets and model summaries are never source snapshots."""
import io
import ipaddress
import json
import socket
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pypdf import PdfReader

from .models import Evidence, Source
from .storage import digest, dump
from .publication import PublicationParser, VERSION

MAX_BYTES = 5_000_000
MAX_REDIRECTS = 5


class CollectionError(ValueError):
    def __init__(self, category, detail):
        self.category = category
        super().__init__(category + ": " + detail)


@dataclass
class ExtractedDocument:
    text: str
    title: str
    published_at: date | None
    links: list[str]
    date_status: str
    date_evidence: list[dict]


def publication_eligible(published_at, cutoff, retrospective=False):
    return published_at is not None and (retrospective or published_at <= cutoff)


def eligible_sources(sources, cutoff, retrospective=False):
    """The dated document environment shared by validation and public export."""
    return [s for s in sources if publication_eligible(s.published_at, cutoff, retrospective)]


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.links = [], []
        self.hidden = 0
        self.title, self.in_title = "", False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag in ("p", "div", "br", "li", "h1", "h2", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if not self.hidden:
            self.parts.append(data)


def extract_document(raw, content_type, origin):
    content_type = content_type.split(";")[0].lower().strip()
    path = urlsplit(origin).path.lower()
    if content_type == "application/pdf" or path.endswith(".pdf") or raw.startswith(b"%PDF"):
        # PDF creation/modification metadata and narrative event dates are not publication dates.
        try:
            text = "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages)
        except Exception as error:
            raise CollectionError("unsupported_format", "unreadable PDF") from error
        return ExtractedDocument(text, "", None, [], "missing", [])
    if content_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain", "application/octet-stream"}:
        raise CollectionError("unsupported_format", content_type)
    text = raw.decode("utf-8", errors="strict")
    if "html" in content_type or path.endswith((".html", ".htm")) or text.lstrip().lower().startswith(("<!doctype html", "<html")):
        parser = HTMLText()
        parser.feed(text)
        dates = PublicationParser(origin)
        dates.feed(text)
        published, status, evidence = dates.result()
        text = "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())
        return ExtractedDocument(text, parser.title.strip(), published, parser.links, status, evidence)
    if content_type == "application/octet-stream":
        raise CollectionError("unsupported_format", "unrecognized binary content")
    return ExtractedDocument(text.replace("\r\n", "\n"), "", None, [], "missing", [])


def extract(raw, content_type, origin):
    """Compatibility tuple; captures retain the complete attribution separately."""
    result = extract_document(raw, content_type, origin)
    return result.text, result.title, result.published_at, result.links


def check_url(url, domains=None):
    parts = urlsplit(url)
    if (parts.scheme not in ("https", "http") or not parts.hostname or parts.username
            or parts.password or parts.port not in (None, 80, 443)
            or domains is not None and parts.hostname.lower() not in {d.lower() for d in domains}):
        raise ValueError("URL outside configured domain scope")
    addresses = socket.getaddrinfo(parts.hostname, parts.port or 443)
    if any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("URL scope excludes private and loopback addresses")


class SourceStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as f:
                f.write(data)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("immutable snapshot integrity failure")

    def capture_text(self, origin, title, text, published=None, *, raw=None, category="primary",
                     redistributable=False, date_basis="provided", retrieved_at=None, **provenance):
        if not text.strip():
            raise ValueError("empty extraction")
        raw = text.encode() if raw is None else raw
        content_hash, raw_hash = digest(text.encode()), digest(raw)
        source_id = "s_" + digest([origin, content_hash, raw_hash, str(published), category,
                                   redistributable, date_basis, provenance])[:24]
        meta_path = self.root / f"metadata/{source_id}.json"
        if meta_path.exists():
            return Source.model_validate_json(meta_path.read_text())
        source = Source(source_id=source_id, url_or_local_origin=origin, title=title or origin,
                        published_at=published, retrieved_at=retrieved_at or datetime.now(timezone.utc),
                        content_hash=content_hash, raw_hash=raw_hash,
                        text_path=f"text/{content_hash}.txt", raw_path=f"raw/{raw_hash}.bin",
                        category=category, redistributable=redistributable, date_basis=date_basis, **provenance)
        self._write(source.text_path, text.encode())
        self._write(source.raw_path, raw)
        self._write(f"metadata/{source_id}.json", dump(source).encode())
        return source

    def read(self, source):
        text = (self.root / source.text_path).read_text()
        if digest(text.encode()) != source.content_hash:
            raise ValueError("source snapshot hash mismatch")
        if digest((self.root / source.raw_path).read_bytes()) != source.raw_hash:
            raise ValueError("raw source snapshot hash mismatch")
        return text

    def evidence(self, source, claim_id, quote, start=None):
        text = self.read(source)
        if start is None:
            if not quote or quote not in text:
                raise ValueError("evidence span missing")
            # Repeated summaries are common in press releases. An exact match
            # is still auditable; select the first occurrence deterministically.
            start = text.index(quote)
        if not quote or start < 0 or text[start:start + len(quote)] != quote:
            raise ValueError("invalid evidence span")
        return Evidence(evidence_id="e_" + digest([source.source_id, claim_id, start, quote])[:24],
                        source_id=source.source_id, span_start=start, span_end=start + len(quote),
                        span_text=quote, claim_id=claim_id)

    def capture_local(self, spec):
        path = Path(spec.origin).resolve()
        raw = path.read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError("source exceeds byte limit")
        result = extract_document(raw, "", str(path))
        return self.capture_document(str(path), raw, result, spec), result.links

    def capture_document(self, origin, raw, result, spec=None, **provenance):
        published, status = result.published_at, result.date_status
        evidence = list(result.date_evidence)
        if spec and spec.published_at:
            evidence.append({"kind": "publication", "method": "configured", "field": "published_at",
                             "raw_value": str(spec.published_at), "parsed_date": str(spec.published_at),
                             "support": spec.date_basis})
            if status == "conflicting" or published and published != spec.published_at:
                published, status = None, "conflicting"
            else:
                published, status = spec.published_at, "configured"
        basis = "; ".join(sorted({e["method"] + ":" + e["field"] for e in evidence if e["kind"] == "publication"})) or "unknown"
        return self.capture_text(origin, (spec.title if spec else "") or result.title, result.text, published,
            raw=raw, category=spec.category if spec else "primary", redistributable=spec.redistributable if spec else False,
            date_basis=basis, date_status=status, date_evidence=evidence, extraction_version=VERSION,
            outbound_links=result.links, **provenance)

    def reusable(self, url):
        choices = [s for s in self.all() if s.extraction_version == VERSION
                   and url in (s.url_or_local_origin, s.original_url, s.final_url)]
        if not choices:
            return None
        # Imported immutable captures retain retrieval time; prefer the latest observed snapshot.
        source = max(choices, key=lambda s: s.retrieved_at)
        self.read(source)
        return source

    def capture_url(self, url, domains, spec=None):
        check_url(url, domains)
        cached = self.reusable(url)
        if cached and (not spec or not spec.published_at):
            return cached, cached.outbound_links
        with httpx.Client(timeout=30, follow_redirects=False, headers={"User-Agent": "CompanyWebShaper/0.1"}) as client:
            current, chain = url, []
            for _ in range(MAX_REDIRECTS + 1):
                if current in chain:
                    raise CollectionError("redirect_loop", current)
                check_url(current)
                chain.append(current)
                check_robots(client, current)
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        current = redirect_target(current, response)
                        continue
                    check_status(response)
                    raw = bounded_body(response)
                    content_type = response.headers.get("content-type", "")
                result = extract_document(raw, content_type, current)
                result.links = sorted({urljoin(current, link).split("#")[0] for link in result.links})
                source = self.capture_document(current, raw, result, spec, original_url=url, final_url=current,
                                               redirect_chain=chain, content_type=content_type)
                return source, result.links
            raise CollectionError("redirect_limit", url)

    def all(self):
        return [Source.model_validate(json.loads(p.read_text())) for p in sorted((self.root / "metadata").glob("*.json"))]


def check_status(response):
    if response.status_code in (401, 403, 429, 451):
        raise CollectionError("blocked_access", f"HTTP {response.status_code}: {response.url}")
    if response.status_code >= 400:
        raise CollectionError("unavailable", f"HTTP {response.status_code}: {response.url}")


def bounded_body(response):
    chunks, size = [], 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_BYTES:
            raise CollectionError("unsupported_format", "source exceeds byte limit")
        chunks.append(chunk)
    return b"".join(chunks)


def redirect_target(url, response):
    location = response.headers.get("location")
    if not location:
        raise CollectionError("redirect_invalid", "missing Location header")
    target = urljoin(url, location).split("#")[0]
    if urlsplit(url).scheme == "https" and urlsplit(target).scheme != "https":
        raise CollectionError("redirect_invalid", "HTTPS downgrade")
    check_url(target)
    return target


def check_robots(client, url):
    parts = urlsplit(url)
    current, visited = f"{parts.scheme}://{parts.netloc}/robots.txt", set()
    for _ in range(MAX_REDIRECTS + 1):
        if current in visited:
            raise CollectionError("redirect_loop", "robots.txt")
        check_url(current)
        visited.add(current)
        with client.stream("GET", current) as response:
            if response.is_redirect:
                target = redirect_target(current, response)
                # A robots redirect to a homepage/article is not a readable access policy.
                if not urlsplit(target).path.endswith("/robots.txt"):
                    raise CollectionError("blocked_access", "robots redirects to a non-policy page")
                current = target
                continue
            if response.status_code == 404:
                return
            check_status(response)
            body = bounded_body(response).decode("utf-8", errors="replace")
        if "<html" in body.lower() or "<!doctype" in body.lower():
            raise CollectionError("blocked_access", "robots response is HTML, not an access policy")
        policy = RobotFileParser()
        policy.parse(body.splitlines())
        if not policy.can_fetch("CompanyWebShaper", url):
            raise CollectionError("blocked_access", "robots access restriction")
        return
    raise CollectionError("redirect_limit", "robots.txt")
