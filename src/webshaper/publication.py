"""Conservative publication-date attribution from the captured page, never retrieval time."""
import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

VERSION = "publication-v1"
MONTHS = {name: i for i, names in enumerate([
    (), ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
    ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
    ("october", "oct"), ("november", "nov"), ("december", "dec")]) for name in names}


def parse_date(value):
    value = str(value).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}[Tt ].+", value):
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", value.lower()).replace(",", "").replace(".", "")
        match = re.fullmatch(r"([a-z]+)\s+(\d{1,2})\s+(\d{4})", cleaned)
        if match and match[1] in MONTHS:
            return date(int(match[3]), MONTHS[match[1]], int(match[2]))
        match = re.fullmatch(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", cleaned)
        if match and match[2] in MONTHS:
            return date(int(match[3]), MONTHS[match[2]], int(match[1]))
    except ValueError:
        pass
    return None


def page_identity(url):
    parsed = urlsplit(url)
    if not parsed.hostname:
        return url
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parsed.query)
                             if not k.startswith("utm_") and k not in {"_hsmi", "_hsenc"}))
    return parsed.hostname.lower().removeprefix("www.") + unquote(parsed.path).rstrip("/") + ("?" + query if query else "")


class PublicationParser(HTMLParser):
    def __init__(self, origin):
        super().__init__(convert_charrefs=True)
        self.origin, self.stack, self.evidence = origin, [], []
        self.json_script = None

    def add(self, kind, method, field, raw, support):
        parsed = parse_date(raw)
        item = {"kind": kind, "method": method, "field": field, "raw_value": str(raw),
                "parsed_date": parsed.isoformat() if parsed else None, "support": support}
        if item not in self.evidence:
            self.evidence.append(item)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        excluded_parent = any(n["excluded"] or n["hidden"] for n in self.stack)
        if tag == "meta" and not excluded_parent:
            field = next((attrs[k] for k in ("property", "name", "itemprop") if attrs.get(k)), "")
            field = field.casefold()
            kind = "publication" if field in {"article:published_time", "datepublished", "pubdate", "publishdate",
                                              "publication_date", "dc.date.issued", "dcterms.issued"} else (
                "modification" if field in {"article:modified_time", "datemodified", "last-modified", "modified"} else "unknown")
            if kind != "unknown" or field == "date":
                self.add(kind, "metadata", field, attrs.get("content", ""), self.get_starttag_text())
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json" and not excluded_parent:
            self.json_script = []
        if tag in {"meta", "link", "img", "br", "hr", "input", "source", "area", "base", "wbr", "embed", "param"}:
            return
        marker = " ".join(str(attrs.get(k, "")) for k in ("class", "id", "itemprop", "data-content-field")).lower()
        excluded = tag in {"aside", "nav", "footer"} or bool(re.search(r"related|recommend|card[-_]|carousel", marker))
        hidden = tag in {"script", "style", "noscript"} or "hidden" in attrs or attrs.get("aria-hidden") == "true"
        excluded = excluded or any(n["excluded"] for n in self.stack)
        hidden = hidden or any(n["hidden"] for n in self.stack)
        self.stack.append({"tag": tag, "attrs": attrs, "marker": marker, "text": [],
                           "excluded": excluded, "hidden": hidden, "start": self.get_starttag_text()})

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self.json_script is not None:
            self.json_script.append(data)
        if not any(n["hidden"] for n in self.stack):
            for node in self.stack:
                # Only small article/date blocks need their own visible text, not the entire DOM.
                if node["tag"] in {"time", "p", "span", "label", "div", "header"} and sum(map(len, node["text"])) < 500:
                    node["text"].append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.json_script is not None:
            raw = "".join(self.json_script)
            self.json_script = None
            try:
                self.inspect_json(json.loads(raw), "$")
            except (ValueError, TypeError):
                self.evidence.append({"kind": "unknown", "method": "json_ld", "field": "$",
                                      "raw_value": "", "parsed_date": None, "support": "Malformed JSON-LD; ignored."})
        positions = [i for i, n in enumerate(self.stack) if n["tag"] == tag]
        if not positions:
            return
        position = positions[-1]
        node = self.stack[position]
        ancestors = self.stack[:position]
        del self.stack[position:]
        if node["excluded"] or node["hidden"]:
            return
        visible = " ".join("".join(node["text"]).split())
        marker = node["marker"]
        context_marker = " ".join(n["marker"] for n in ancestors[-2:]) + " " + marker
        parent_text = " ".join(" ".join(ancestors[-1]["text"]).split()) if ancestors else ""
        modification = bool(re.search(r"modif|updated", context_marker)) or bool(re.search(r"\b(?:Updated|Last modified)\b", parent_text, re.I))
        event_date = bool(re.search(r"startdate|enddate|event[-_ ]?date", context_marker))
        publication = bool(re.search(r"published|datepublished|pubdate|post[-_]date|article[-_].*date", marker)) or "pubdate" in node["attrs"]
        article_header = any(n["tag"] == "article" for n in ancestors) and ancestors and ancestors[-1]["tag"] == "header"
        if tag == "time" and (publication or modification or event_date or article_header):
            self.add("event" if event_date else "modification" if modification else "publication", "time", "datetime",
                     node["attrs"].get("datetime", visible), node["start"] + visible + "</time>")
        # Require a publication label or semantic published class, not arbitrary dates in the body.
        labeled = re.match(r"^(Published(?:\s+on)?|Publication date|Posted(?:\s+on)?|Updated(?:\s+on)?|Last modified)\s*:?\s*(.+)$", visible, re.I)
        if labeled:
            self.add("modification" if re.match(r"Updated|Last modified", labeled[1], re.I) else "publication",
                     "visible_label", labeled[1], labeled[2], visible)
        elif publication and tag in {"p", "span"} and len(visible) < 100:
            self.add("event" if event_date else "modification" if modification else "publication",
                     "visible_label", marker, visible, node["start"] + visible)

    def inspect_json(self, value, path, parent_matches=True):
        if isinstance(value, list):
            for i, node in enumerate(value):
                self.inspect_json(node, f"{path}[{i}]", parent_matches)
        if not isinstance(value, dict):
            return
        kinds = value.get("@type", [])
        kinds = [kinds] if isinstance(kinds, str) else kinds
        same = parent_matches
        if set(kinds) & {"Article", "NewsArticle", "BlogPosting", "WebPage", "Report", "Blog"}:
            own = value.get("url") or value.get("mainEntityOfPage") or value.get("@id")
            if isinstance(own, dict):
                own = own.get("@id") or own.get("url")
            same = parent_matches and (not own or isinstance(own, str) and page_identity(own) == page_identity(self.origin))
            if "Blog" in kinds:
                same = same and bool(own and value.get("headline"))
            if same:
                for field, kind in (("datePublished", "publication"), ("dateModified", "modification")):
                    if field in value:
                        self.add(kind, "json_ld", path + "." + field, value[field],
                                 json.dumps({"@type": value.get("@type"), "url": own, field: value[field]}, ensure_ascii=False))
        for key in ("@graph", "mainEntity"):
            if key in value:
                self.inspect_json(value[key], path + "." + key, same)

    def result(self):
        published = [e for e in self.evidence if e["kind"] == "publication"]
        dates = {e["parsed_date"] for e in published if e["parsed_date"]}
        if len(dates) > 1:
            return None, "conflicting", self.evidence
        if len(dates) == 1:
            return date.fromisoformat(next(iter(dates))), "resolved", self.evidence
        malformed = any(e["method"] == "json_ld" and e["kind"] == "unknown" for e in self.evidence)
        return None, "unresolved" if published or malformed else "missing", self.evidence
