"""Immutable captures. Snippets and model summaries are never source snapshots."""
import io
import ipaddress
import json
import socket
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pypdf import PdfReader

from .models import Evidence, Source
from .storage import digest, dump

MAX_BYTES = 5_000_000


def eligible_sources(sources, cutoff, retrospective=False):
    """The dated document environment shared by validation and public export."""
    return [s for s in sources if s.published_at is not None
            and (retrospective or s.published_at <= cutoff)]


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.links = [], []
        self.hidden = 0
        self.title, self.in_title = "", False
        self.published = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "meta" and attrs.get("property", attrs.get("name")) in (
                "article:published_time", "date", "datePublished"):
            self.published = attrs.get("content")
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


def extract(raw, content_type, origin):
    if "pdf" in content_type or origin.lower().endswith(".pdf"):
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages), "", None, []
    text = raw.decode("utf-8", errors="strict")
    if "html" in content_type or origin.lower().endswith((".html", ".htm")):
        parser = HTMLText()
        parser.feed(text)
        text = "\n".join(" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip())
        published = date.fromisoformat(parser.published[:10]) if parser.published else None
        return text, parser.title.strip(), published, parser.links
    return text.replace("\r\n", "\n"), "", None, []


def check_url(url, domains):
    parts = urlsplit(url)
    if (parts.scheme not in ("https", "http") or not parts.hostname or parts.username
            or parts.password or parts.hostname.lower() not in {d.lower() for d in domains}):
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
                     redistributable=False, date_basis="provided"):
        if not text.strip():
            raise ValueError("empty extraction")
        raw = text.encode() if raw is None else raw
        content_hash, raw_hash = digest(text.encode()), digest(raw)
        source_id = "s_" + digest([origin, content_hash, raw_hash, str(published), category,
                                   redistributable, date_basis])[:24]
        meta_path = self.root / f"metadata/{source_id}.json"
        if meta_path.exists():
            return Source.model_validate_json(meta_path.read_text())
        source = Source(source_id=source_id, url_or_local_origin=origin, title=title or origin,
                        published_at=published, retrieved_at=datetime.now(timezone.utc),
                        content_hash=content_hash, raw_hash=raw_hash,
                        text_path=f"text/{content_hash}.txt", raw_path=f"raw/{raw_hash}.bin",
                        category=category, redistributable=redistributable, date_basis=date_basis)
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
        text, title, published, links = extract(raw, "", str(path))
        source = self.capture_text(str(path), spec.title or title, text, spec.published_at or published,
                                   raw=raw, category=spec.category, redistributable=spec.redistributable,
                                   date_basis=spec.date_basis if spec.published_at else "document_metadata")
        return source, links

    def capture_url(self, url, domains, spec=None):
        check_url(url, domains)
        with httpx.Client(timeout=30, follow_redirects=False, headers={"User-Agent": "CompanyWebShaper/0.1"}) as client:
            parts = urlsplit(url)
            robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
            robots = client.get(robots_url)
            if robots.status_code != 404:
                robots.raise_for_status()
                policy = RobotFileParser()
                policy.parse(robots.text.splitlines())
                if not policy.can_fetch("CompanyWebShaper", url):
                    raise ValueError("robots access restriction")
            with client.stream("GET", url) as response:
                # Redirects require explicit re-entry so scope/access restrictions cannot be bypassed.
                if response.is_redirect:
                    raise ValueError("redirect requires an explicitly configured final URL")
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("source exceeds byte limit")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                text, title, published, links = extract(raw, response.headers.get("content-type", ""), url)
        source = self.capture_text(url, (spec.title if spec else "") or title, text,
                                   (spec.published_at if spec else None) or published, raw=raw,
                                   category=spec.category if spec else "primary",
                                   redistributable=spec.redistributable if spec else False,
                                   date_basis=spec.date_basis if spec and spec.published_at else "document_metadata")
        return source, sorted({urljoin(url, link).split("#")[0] for link in links})

    def all(self):
        return [Source.model_validate(json.loads(p.read_text())) for p in sorted((self.root / "metadata").glob("*.json"))]
