"""Direct public-page retrieval in the trusted host, without a model intermediary.

Trust describes the process boundary, never the page's content. Any public
HTTP(S) URL selected by the researcher is eligible. Every redirect is checked;
connections use the checked IP while TLS still authenticates the original host.
"""
from dataclasses import dataclass
from collections import Counter
from concurrent.futures import CancelledError, Future, TimeoutError as FutureTimeout
from email.message import Message
import gzip
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
from pathlib import Path
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import unicodedata
from urllib.parse import quote, urljoin, urlsplit
from uuid import uuid4

from .archive import read_json, stamp, write_json


FETCH_PATH = 'direct-readable-v1'
TEXT_POLICY = 'unicode-layout-controls-v1'
LAYOUT_CONTROLS = frozenset('\t\n\r\f\v\x85')


class FetchError(Exception):
    def __init__(self, reason, error, receipt=None):
        self.reason, self.error, self.receipt = reason, str(error), receipt
        super().__init__(f'{reason}: {error}')


@dataclass
class PageResult:
    text: str
    receipt: dict


def inspect_extraction(raw):
    """Validate complete extractor bytes; never repair, select or shorten text."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None, dict(reason='extraction_decode_error', forbidden_controls=None, forbidden_control_count=None)
    controls = Counter(char for char in text
                       if unicodedata.category(char) == 'Cc' and char not in LAYOUT_CONTROLS)
    reason = ('forbidden_control_characters' if controls else
              'no_readable_text' if not text.strip() else None)
    return text, dict(reason=reason, forbidden_control_count=sum(controls.values()),
                      forbidden_controls={f'U+{ord(char):04X}': controls[char] for char in sorted(controls)})


def verify_receipt(directory, receipt, *, text=None, expected_policy=None):
    """Check exact transport and any declared validation policy.

    Absent policy is historical evidence of transport only. Fresh consumers bind
    expected_policy explicitly so a removed policy cannot downgrade their check.
    """
    try:
        identity = receipt['id']
        if not isinstance(identity, str) or Path(identity).name != identity:
            raise ValueError('Invalid download receipt identity')
        if read_json(directory / 'downloads' / (identity + '.json')) != receipt:
            raise ValueError('Download receipt differs from durable archive')
        policy = receipt.get('text_policy')
        if policy not in (None, TEXT_POLICY) or (expected_policy is not None and policy != expected_policy):
            raise ValueError('Download text validation policy differs from required policy')
        def artifact(relative):
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file():
                raise ValueError('Download artifact missing or outside task archive')
            return path
        for hop in receipt['hops']:
            raw = artifact(hop['raw_path']).read_bytes()
            if len(raw) != hop['raw_page_bytes'] or hashlib.sha256(raw).hexdigest() != hop['raw_sha256']:
                raise ValueError('Download bytes do not match receipt')
        extraction = None
        if policy is None and any(key.startswith('extraction_') for key in receipt):
            raise ValueError('Extraction validation metadata has no policy')
        if policy == TEXT_POLICY:
            if 'extraction_path' in receipt:
                extraction = artifact(receipt['extraction_path']).read_bytes()
                if (len(extraction) != receipt['extraction_bytes'] or
                    hashlib.sha256(extraction).hexdigest() != receipt['extraction_sha256']):
                    raise ValueError('Download extraction bytes do not match receipt')
                decoded, validation = inspect_extraction(extraction)
                if (receipt['extraction_chars'] != (len(decoded) if decoded is not None else None) or
                    receipt['extraction_validation'] != validation):
                    raise ValueError('Download extraction validation differs from retained bytes')
                if validation['reason'] is not None:
                    if (receipt['status'] != 'failed' or receipt.get('reason') != validation['reason'] or
                        any(key in receipt for key in ('text_path', 'text_sha256', 'readable_chars'))):
                        raise ValueError('Rejected extraction cannot establish readable evidence')
                elif receipt['status'] not in ('succeeded', 'cancelled'):
                    raise ValueError('Valid extraction has contradictory download status')
            elif (receipt['status'] == 'succeeded' or
                  receipt.get('reason') in ('forbidden_control_characters', 'no_readable_text',
                                            'extraction_decode_error') or
                  'parser' in receipt or any(key.startswith('extraction_') for key in receipt)):
                raise ValueError('Download extraction validation is missing')
        if receipt['status'] == 'succeeded':
            readable_bytes = artifact(receipt['text_path']).read_bytes()
            readable = readable_bytes.decode('utf-8')
            if (len(readable) != receipt['readable_chars'] or
                hashlib.sha256(readable.encode()).hexdigest() != receipt['text_sha256'] or
                (extraction is not None and readable_bytes != extraction) or
                (text is not None and text != readable)):
                raise ValueError('Download readable text differs from receipt or returned text')
        elif text is not None:
            raise ValueError('Failed download cannot establish readable evidence')
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise FetchError('receipt_integrity', error) from error


def resolve_public(url):
    from .repl_tools import normalized_url
    parts = urlsplit(normalized_url(url))
    try:
        port = parts.port or (443 if parts.scheme == 'https' else 80)
        answers = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as error:
        raise FetchError('dns_error', error) from error
    addresses = [answer[4][0] for answer in answers]
    if not addresses:
        raise FetchError('dns_error', 'No addresses returned')
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast:
            raise FetchError('nonpublic_address', f'Public HTTP(S) destinations required: {address}')
    return addresses[0], port


class ReadableHTML(HTMLParser):
    """Retain all static readable text, not a relevance-selected article extract."""
    BLOCKS = {'address', 'article', 'aside', 'blockquote', 'br', 'caption', 'dd', 'div', 'dl',
              'dt', 'fieldset', 'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3',
              'h4', 'h5', 'h6', 'header', 'hr', 'li', 'main', 'nav', 'ol', 'p', 'pre',
              'section', 'table', 'td', 'th', 'title', 'tr', 'ul'}
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta',
            'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.parts = [], []

    def handle_starttag(self, tag, attrs):
        # HTML permits omitted end tags. Close the prior optional element before
        # determining inherited visibility, so its hidden flag cannot leak.
        if tag in self.BLOCKS - {'br', 'td', 'th', 'tr'}:
            self._close_optional({'p'}, {'table', 'html'})
        rules = {'li': ({'li'}, {'ul', 'ol'}),
                 'dt': ({'dt', 'dd'}, {'dl'}), 'dd': ({'dt', 'dd'}, {'dl'}),
                 'td': ({'td', 'th'}, {'tr', 'table'}), 'th': ({'td', 'th'}, {'tr', 'table'}),
                 'tr': ({'tr'}, {'table', 'tbody', 'thead', 'tfoot'}),
                 'option': ({'option'}, {'select', 'datalist'}),
                 'thead': ({'thead', 'tbody', 'tfoot'}, {'table'}),
                 'tbody': ({'thead', 'tbody', 'tfoot'}, {'table'}),
                 'tfoot': ({'thead', 'tbody', 'tfoot'}, {'table'})}
        if tag in rules:
            self._close_optional(*rules[tag])
        attrs = dict(attrs)
        hidden = (tag in {'script', 'style', 'template'} or 'hidden' in attrs or
                  attrs.get('aria-hidden', '').lower() == 'true' or
                  bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)', attrs.get('style', ''), re.I)))
        hidden = hidden or bool(self.stack and self.stack[-1][1])
        if not hidden and tag in self.BLOCKS:
            self.parts.append('\n')
        if not hidden and tag == 'img' and attrs.get('alt'):
            self.parts.append(attrs['alt'])
        if tag not in self.VOID:
            self.stack.append((tag, hidden))

    def _close_optional(self, names, boundaries):
        for index in range(len(self.stack) - 1, -1, -1):
            name, _ = self.stack[index]
            if name in names:
                del self.stack[index:]
                self.parts.append('\n')
                return
            if name in boundaries:
                return

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        hidden = bool(self.stack and self.stack[-1][1])
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break
        if not hidden and tag in self.BLOCKS:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self.stack or not self.stack[-1][1]:
            self.parts.append(data)

    def text(self):
        # Normalize layout whitespace, retaining every readable text occurrence.
        # Python's split()/splitlines() also erase U+001C--U+001F. Preserve those
        # non-layout controls so the extraction validator can reject corruption.
        return '\n'.join(line for raw in re.split(r'\r\n|[\n\r\v\f\x85\u2028\u2029]', ''.join(self.parts))
                         if (line := re.sub(r'[^\S\x1c-\x1f]+', ' ', raw).strip(' ')))


class PageFetcher:
    def __init__(self, ctx, *, request=None):
        self.ctx = ctx
        self.request = request or self._request

    def _resolve(self, url, deadline):
        # libc DNS has no portable cancellation API. A daemon isolates that
        # blocking call; timeout/cancellation must not start a late connection.
        result = Future()
        def resolve():
            try:
                result.set_result(resolve_public(url))
            except Exception as error:
                result.set_exception(error)
        threading.Thread(target=resolve, daemon=True).start()
        while True:
            self.ctx.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Download deadline exceeded during name resolution')
            try:
                return result.result(timeout=min(.05, remaining))
            except FutureTimeout:
                continue

    def _request(self, url, timeout):
        deadline = time.monotonic() + timeout
        address, port = self._resolve(url, deadline)
        parts = urlsplit(url)
        hostname = parts.hostname.encode('idna').decode('ascii')
        connection = http.client.HTTPConnection(hostname, port, timeout=timeout)
        interrupted, finished = threading.Event(), threading.Event()
        stream = None
        def interrupt():
            if finished.is_set():
                return
            interrupted.set()
            if stream is not None:
                try:
                    stream.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
        timer = threading.Timer(max(0, deadline - time.monotonic()), interrupt)
        timer.daemon = True
        timer.start()
        if self.ctx.cancellation is not None:
            self.ctx.cancellation.add_done_callback(lambda future: interrupt() if future.cancelled() else None)
        try:
            self.ctx.check_cancelled()
            if interrupted.is_set():
                raise TimeoutError('Download deadline exceeded during name resolution')
            stream = socket.socket(socket.AF_INET6 if ':' in address else socket.AF_INET, socket.SOCK_STREAM)
            stream.settimeout(max(.001, deadline - time.monotonic()))
            connection.sock = stream
            stream.connect((address, port))
            if parts.scheme == 'https':
                connection.sock = ssl.create_default_context().wrap_socket(
                    stream, server_hostname=hostname, do_handshake_on_connect=False)
                stream = connection.sock
                stream.do_handshake()
            stream = connection.sock
            path = quote(parts.path or '/', safe="/%:@!$&'()*+,;=-._~")
            if parts.query:
                path += '?' + quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
            connection.request('GET', path, headers={'User-Agent': 'loop-research/0.1 (direct page retrieval)',
                                                     'Accept': 'text/html,application/pdf,text/plain,*/*',
                                                     'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            chunks = []
            while not response.isclosed():
                self.ctx.check_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Download exceeded operation deadline')
                stream.settimeout(remaining)
                chunk = response.read1(65536)
                self.ctx.check_cancelled()
                if interrupted.is_set() or time.monotonic() >= deadline:
                    raise TimeoutError('Download exceeded operation deadline')
                if not chunk:
                    break
                chunks.append(chunk)
            return {'status': response.status, 'headers': {k.lower(): v for k, v in response.getheaders()},
                    'body': b''.join(chunks), 'peer_ip': address}
        except (OSError, http.client.HTTPException):
            self.ctx.check_cancelled()
            raise
        finally:
            finished.set()
            timer.cancel()
            connection.close()

    def fetch(self, url):
        from .repl_tools import normalized_url
        url = normalized_url(url)
        identity = uuid4().hex
        directory = self.ctx.path / 'downloads'
        directory.mkdir(parents=True, exist_ok=True)
        record_path = directory / (identity + '.json')
        receipt = {'id': identity, 'fetch_path': FETCH_PATH, 'text_policy': TEXT_POLICY, 'requested_url': url,
                   'started_at': stamp(), 'status': 'pending', 'hops': []}
        write_json(record_path, receipt)
        deadline = time.monotonic() + self.ctx.config.codex.timeout_s
        current, visited = url, set()
        try:
            with self.ctx.trace.span('Direct fetch', 'download', url=url, fetch_path=FETCH_PATH) as details:
                while True:
                    self.ctx.check_cancelled()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise FetchError('download_error', 'Fetch operation deadline exceeded')
                    if current in visited:
                        raise FetchError('redirect_loop', current)
                    visited.add(current)
                    try:
                        reply = self.request(current, remaining)
                    except (OSError, http.client.HTTPException) as error:
                        raise FetchError('download_error', error) from error
                    self.ctx.check_cancelled()
                    raw = reply['body']
                    headers = {k.lower(): v for k, v in reply['headers'].items()}
                    raw_path = directory / f'{identity}-{len(receipt["hops"])}.raw'
                    raw_path.write_bytes(raw)
                    hop = {'url': current, 'status': reply['status'], 'headers': headers,
                           'peer_ip': reply.get('peer_ip'), 'raw_path': str(raw_path.relative_to(self.ctx.path)),
                           'raw_page_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest()}
                    receipt['hops'].append(hop)
                    receipt.update(final_url=current, **{k: hop[k] for k in ('raw_path', 'raw_page_bytes', 'raw_sha256')})
                    write_json(record_path, receipt)
                    if headers.get('content-length') is not None:
                        try:
                            declared = int(headers['content-length'])
                        except ValueError as error:
                            raise FetchError('invalid_response', 'Invalid Content-Length') from error
                        if declared != len(raw):
                            raise FetchError('incomplete_body', 'Content-Length differs from received bytes')
                    if reply['status'] in {301, 302, 303, 307, 308}:
                        if not headers.get('location'):
                            raise FetchError('redirect_error', 'Missing Location header')
                        try:
                            current = normalized_url(urljoin(current, headers['location']))
                        except ValueError as error:
                            raise FetchError('redirect_error', error) from error
                        continue
                    if not 200 <= reply['status'] < 300:
                        raise FetchError('http_status', f'HTTP {reply["status"]} for {current}')
                    if not raw:
                        raise FetchError('empty_body', 'Successful HTTP response has no body')
                    content = raw
                    encoding = headers.get('content-encoding', 'identity').lower()
                    if encoding == 'gzip':
                        try:
                            content = gzip.decompress(raw)
                        except (OSError, EOFError) as error:
                            raise FetchError('decode_error', error) from error
                    elif encoding != 'identity':
                        raise FetchError('unsupported_content_encoding', encoding)
                    extracted, parser, raw_chars = self._extract(content, headers.get('content-type', ''),
                                                                 raw_path, deadline)
                    text_path = directory / (identity + '.txt')
                    text_path.write_bytes(extracted)
                    text, validation = inspect_extraction(extracted)
                    receipt.update(parser=parser, raw_page_chars=raw_chars,
                                   extraction_path=str(text_path.relative_to(self.ctx.path)),
                                   extraction_bytes=len(extracted), extraction_sha256=hashlib.sha256(extracted).hexdigest(),
                                   extraction_chars=len(text) if text is not None else None,
                                   extraction_validation=validation)
                    if validation['reason'] == 'extraction_decode_error':
                        raise FetchError('extraction_decode_error',
                                         'Extractor output is not valid UTF-8; exact bytes retained')
                    if validation['reason'] == 'forbidden_control_characters':
                        counts = ', '.join(f'{code}={count}' for code, count in validation['forbidden_controls'].items())
                        raise FetchError('forbidden_control_characters',
                            f'Extracted text contains {validation["forbidden_control_count"]} forbidden non-layout '
                            f'control characters ({counts}); exact extraction retained, no repair or fallback')
                    if validation['reason'] == 'no_readable_text':
                        raise FetchError('no_readable_text', 'No static readable text; no model or browser fallback')
                    self.ctx.check_cancelled()
                    receipt.update(status='succeeded', finished_at=stamp(), parser=parser,
                                   raw_page_chars=raw_chars, readable_chars=len(text),
                                   text_path=str(text_path.relative_to(self.ctx.path)),
                                   text_sha256=hashlib.sha256(text.encode()).hexdigest())
                    details.update(receipt=receipt)
                    write_json(record_path, receipt)
                    return PageResult(text, receipt)
        except FetchError as error:
            receipt.update(status='failed', reason=error.reason, error=error.error, finished_at=stamp())
            write_json(record_path, receipt)
            error.receipt = receipt
            raise
        except CancelledError:
            receipt.update(status='cancelled', reason='cancelled', finished_at=stamp())
            write_json(record_path, receipt)
            raise

    def _extract(self, body, content_type, raw_path, deadline):
        message = Message()
        message['content-type'] = content_type or 'application/octet-stream'
        media = message.get_content_type()
        if media == 'application/pdf' or body.startswith(b'%PDF-'):
            binary = shutil.which('pdftotext')
            if binary is None:
                raise FetchError('pdf_parser_unavailable', 'Install Poppler pdftotext')
            # The parser consumes the decoded bytes if the HTTP entity was compressed.
            pdf_path = raw_path.with_suffix('.pdf')
            pdf_path.write_bytes(body)
            try:
                result = self.ctx.run_process([binary, '-layout', '-enc', 'UTF-8', str(pdf_path), '-'],
                                              capture_output=True, timeout=max(.001, deadline - time.monotonic()))
                if result.returncode:
                    raise FetchError('pdf_extraction_error', result.stderr.decode(errors='replace'))
                return result.stdout, 'poppler-pdftotext-layout', None
            except (OSError, subprocess.TimeoutExpired) as error:
                raise FetchError('pdf_extraction_error', error) from error
        html = media in {'text/html', 'application/xhtml+xml'}
        if not (media.startswith('text/') or media in {'application/json', 'application/xml', 'application/xhtml+xml'}):
            raise FetchError('unsupported_content_type', media)
        charset = message.get_content_charset()
        if html and not charset:
            meta = re.search(br'<meta\b[^>]*charset\s*=\s*[\"\x27]?\s*([\w-]+)', body, re.I)
            if meta:
                charset = meta[1].decode('ascii')
        try:
            decoded = body.decode(charset or 'utf-8-sig')
        except (UnicodeError, LookupError) as error:
            raise FetchError('decode_error', error) from error
        if html:
            parser = ReadableHTML()
            parser.feed(decoded)
            parser.close()
            return parser.text().encode('utf-8'), 'stdlib-html-readable-v1', len(decoded)
        return decoded.encode('utf-8'), 'decoded-text-v1', len(decoded)
