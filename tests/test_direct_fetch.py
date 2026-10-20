"""Full page provenance, failures, and cache semantics of the direct fetch path."""
import hashlib
import json
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from loop_research.page_fetch import PageFetcher

REAL_REQUEST = PageFetcher._request


class NoModel:
    last_web_actions = []

    def complete(self, *args, **kwargs):
        raise AssertionError('A direct fetch must never call a model')


def response(text, content_type='text/html; charset=utf-8', status=200, **headers):
    return {'status': status, 'headers': {'content-type': content_type, **headers},
            'body': text.encode() if isinstance(text, str) else text, 'peer_ip': '93.184.215.14'}


def test_full_html_keeps_every_readable_section_without_padding_or_focus_filter(ctx):
    from loop_research.page_fetch import PageFetcher
    from loop_research.repl_tools import ResearchTools
    paragraphs = [f'<p>Section {i}: unique observation {i * 17}.</p>' for i in range(1400)]
    raw = ('<html><head><title>Complete document</title><style>.x{color:red}</style></head>'
           '<body><nav>Contents</nav><main>' + ''.join(paragraphs) +
           '<p>Exact <b>inline</b> quotation &amp; qualification.</p></main>'
           '<script>not readable source</script><p hidden>hidden text</p>'
           '<footer>Final qualification.</footer></body></html>').encode()
    requests = []
    def request(url, timeout):
        requests.append(url)
        return response(raw)
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=request))
    full = tools.fetch('https://example.org/document', focus='Section 1 only')
    assert full.startswith('Complete document\nContents\nSection 0: unique observation 0.')
    assert full.endswith('Final qualification.')
    assert 'Exact inline quotation & qualification.' in full
    assert 'not readable source' not in full and 'hidden text' not in full
    for i in range(1400):
        assert full.count(f'Section {i}: unique observation {i * 17}.') == 1
    assert len(full) > 50_000
    assert tools.fetch('https://EXAMPLE.org/document#end', focus='Different focus') == full
    assert requests == ['https://example.org/document']
    assert tools.snapshot()['fetched'] == {'https://example.org/document': [full]}
    owner, cached = ctx.load('fetch_telemetry.json')
    assert owner['fetch_path'] == cached['fetch_path'] == 'direct-readable-v1'
    assert owner['raw_page_bytes'] == len(raw)
    assert owner['readable_chars'] == len(full)
    assert cached['owner_id'] == owner['id']
    receipt = owner['receipt']
    assert (ctx.path / receipt['raw_path']).read_bytes() == raw
    assert receipt['raw_sha256'] == hashlib.sha256(raw).hexdigest()
    assert (ctx.path / receipt['text_path']).read_text() == full


@pytest.mark.parametrize('status,body,reason', [
    (403, 'Access denied', 'http_status'), (200, '', 'empty_body'),
    (200, '<html><script>content()</script></html>', 'no_readable_text')])
def test_download_failures_count_once_and_never_fallback_to_a_model(ctx, status, body, reason):
    from loop_research.page_fetch import PageFetcher
    from loop_research.repl_tools import ResearchTools
    seen = []
    def request(url, timeout):
        seen.append(url)
        return response(body, status=status)
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=request))
    assert tools.fetch('https://example.org/') == 'FETCH_FAILED'
    assert len(seen) == 1 and tools.cache == {}
    assert tools.snapshot()['fetched'] == {}
    failure, = tools.snapshot()['failures']
    assert failure['reason'] == reason and failure['error']
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    assert receipt['status'] == 'failed' and receipt['reason'] == reason
    assert tools.fetch('https://example.org/') == 'FETCH_FAILED'
    assert len(seen) == 2  # Explicit agent retry; no internal transport retry.


def test_redirects_preserve_selected_url_actual_url_and_every_download(ctx):
    from loop_research.page_fetch import PageFetcher
    seen = []
    def request(url, timeout):
        seen.append(url)
        if len(seen) == 1:
            return response('', status=302, location='/actual')
        return response('Full readable text', 'text/plain; charset=utf-8')
    page = PageFetcher(ctx, request=request).fetch('https://example.org/selected')
    assert page.text == 'Full readable text'
    assert seen == ['https://example.org/selected', 'https://example.org/actual']
    assert page.receipt['requested_url'] == seen[0]
    assert page.receipt['final_url'] == seen[1]
    assert [hop['status'] for hop in page.receipt['hops']] == [302, 200]


def test_redirect_loops_and_unsupported_media_are_failed_downloads(ctx):
    from loop_research.page_fetch import PageFetcher, FetchError
    for reply, reason in [(response('', status=302, location='/'), 'redirect_loop'),
                          (response(b'\x89PNG', 'image/png'), 'unsupported_content_type')]:
        with pytest.raises(FetchError) as failure:
            PageFetcher(ctx, request=lambda *args: reply).fetch('https://example.org/')
        assert failure.value.reason == reason


@pytest.mark.parametrize('address', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'fd00::1'])
def test_host_boundary_rejects_nonpublic_targets_without_site_allowlist(monkeypatch, address):
    from loop_research.page_fetch import resolve_public, FetchError
    family = socket.AF_INET6 if ':' in address else socket.AF_INET
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs:
                        [(family, socket.SOCK_STREAM, 6, '', (address, 443))])
    with pytest.raises(FetchError, match='nonpublic_address'):
        resolve_public('https://unlisted.example/')


def test_public_dns_resolution_accepts_any_domain_and_rejects_mixed_answers(monkeypatch):
    from loop_research.page_fetch import resolve_public, FetchError
    answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 443))]
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: answers)
    assert resolve_public('https://arbitrary.example/')[0] == '93.184.215.14'
    answers.append((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443)))
    with pytest.raises(FetchError, match='nonpublic_address'):
        resolve_public('https://arbitrary.example/')


def test_legacy_model_cache_is_not_reused_by_direct_fetch(ctx):
    from loop_research.page_fetch import PageFetcher
    from loop_research.repl_tools import ResearchTools
    ctx.save('tool_cache.json', {json.dumps(['fetch', 'https://example.org/', '']): 'old excerpt'})
    calls = []
    def request(url, timeout):
        calls.append(url)
        return response('Full new page', 'text/plain')
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=request))
    assert tools.fetch('https://example.org/') == 'Full new page'
    assert calls == ['https://example.org/']


def test_concurrent_different_focus_requests_share_one_full_page(ctx):
    from loop_research.page_fetch import PageFetcher
    from loop_research.repl_tools import ResearchTools
    calls = []
    entered, release = threading.Event(), threading.Event()
    def request(url, timeout):
        calls.append(url)
        entered.set()
        assert release.wait(5)
        return response('Whole document', 'text/plain')
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=request))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(tools.fetch, 'https://example.org/', 'first')
        assert entered.wait(5)
        second = pool.submit(tools.fetch, 'https://example.org/', 'second')
        release.set()
        assert first.result(5) == second.result(5) == 'Whole document'
    assert calls == ['https://example.org/']
    assert len(tools.snapshot()['fetched']['https://example.org/']) == 1


def test_network_timeout_records_failed_fetch_with_reason(ctx):
    from loop_research.page_fetch import PageFetcher
    from loop_research.repl_tools import ResearchTools
    def request(*args):
        raise TimeoutError('fixture read timeout')
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=request))
    assert tools.fetch('https://example.org/') == 'FETCH_FAILED'
    assert tools.snapshot()['failures'][0]['reason'] == 'download_error'


def test_pdf_extraction_preserves_all_pages_and_archives_exact_download(ctx):
    from loop_research.page_fetch import PageFetcher
    # Minimal independently specified two-page PDF; exercise installed Poppler.
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    for text in (b'First page evidence.', b'Last page qualification.'):
        stream = b'BT /F1 12 Tf 72 720 Td (' + text + b') Tj ET'
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
    raw = b'%PDF-1.4\n'
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(raw))
        raw += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(raw)
    raw += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    raw += b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets)
    raw += f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    page = PageFetcher(ctx, request=lambda *args: response(raw, 'application/pdf')).fetch('https://example.org/file.pdf')
    assert 'First page evidence.' in page.text and 'Last page qualification.' in page.text
    assert page.text.count('First page evidence.') == page.text.count('Last page qualification.') == 1
    assert (ctx.path / page.receipt['raw_path']).read_bytes() == raw
    assert page.receipt['raw_page_chars'] is None
    assert page.receipt['readable_chars'] == len(page.text)


def test_incomplete_body_and_invalid_decoding_do_not_become_success(ctx):
    from loop_research.page_fetch import PageFetcher, FetchError
    for reply, reason in [(response('short', 'text/plain', **{'content-length': '100'}), 'incomplete_body'),
                          (response(b'\xff', 'text/plain; charset=utf-8'), 'decode_error')]:
        with pytest.raises(FetchError) as failure:
            PageFetcher(ctx, request=lambda *args: reply).fetch('https://example.org/')
        assert failure.value.reason == reason


def test_archive_audit_verifies_direct_receipts_and_rejects_changed_download(ctx):
    from loop_research.archive_audit import fetch_audit, ArchiveCorruptionError
    from loop_research.page_fetch import PageFetcher
    from loop_research.repl_tools import ResearchTools
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx,
        request=lambda *args: response('Complete evidence', 'text/plain')))
    assert tools.fetch('https://example.org/') == 'Complete evidence'
    audit, = fetch_audit(ctx.path, [], [], [], tools.snapshot())
    assert audit['direct_receipt_verified'] is True
    (ctx.path / audit['receipt']['raw_path']).write_bytes(b'changed on disk')
    with pytest.raises(ArchiveCorruptionError, match='download'):
        fetch_audit(ctx.path, [], [], [], tools.snapshot())


def test_real_http_download_uses_checked_address_and_reads_entire_response(ctx, monkeypatch):
    from loop_research import page_fetch
    received = []
    content = ('A complete local response.\n' * 3000).encode()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.path, self.headers['Host']))
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
        monkeypatch.setattr(page_fetch, 'resolve_public', lambda url: ('127.0.0.1', port))
        fetcher = PageFetcher(ctx)
        fetcher.request = lambda url, timeout: REAL_REQUEST(fetcher, url, timeout)
        try:
            result = fetcher.fetch(f'http://unlisted.example:{port}/complete?q=1')
        finally:
            server.shutdown()
            thread.join(5)
    assert result.text.encode() == content
    assert received == [('/complete?q=1', f'unlisted.example:{port}')]


@pytest.mark.parametrize('html,want', [
    ('<p hidden>secret<p>visible conclusion', 'visible conclusion'),
    ('<ul><li hidden>secret<li>visible item</ul>', 'visible item'),
    ('<table><tr><td hidden>secret<td>visible cell</table>', 'visible cell')])
def test_legal_optional_html_end_tags_do_not_hide_following_content(html, want):
    from loop_research.page_fetch import ReadableHTML
    parser = ReadableHTML()
    parser.feed(html)
    assert parser.text() == want


@pytest.mark.parametrize('damage', ['text', 'raw', 'owner', 'telemetry'])
def test_direct_cache_never_returns_unverified_evidence(ctx, damage):
    from loop_research.repl_tools import ResearchTools
    calls = []
    def request(url, timeout):
        calls.append(url)
        return response('Actual source evidence.', 'text/plain')
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx, request=request))
    tools.fetch('https://example.org/')
    receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
    if damage == 'text':
        tools.cache[json.dumps(['fetch', 'https://example.org/', 'direct-readable-v1'])] = 'Fabricated quotation!!'
    elif damage == 'raw':
        (ctx.path / receipt['raw_path']).write_bytes(b'corrupted source bytes')
    elif damage == 'owner':
        tools.evidence['fetches'].clear()
    else:
        tools.fetch_telemetry.clear()
    assert tools.fetch('https://example.org/') == 'FETCH_FAILED'
    assert tools.snapshot()['failures'][-1]['reason'] == 'receipt_integrity'
    assert len(calls) == 1  # No silent re-download or model fallback.


def test_direct_archive_missing_telemetry_fails_closed(ctx):
    from loop_research.repl_tools import ResearchTools
    from loop_research.archive_audit import fetch_audit, ArchiveCorruptionError
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx,
        request=lambda *args: response('Full evidence', 'text/plain')))
    tools.fetch('https://example.org/')
    (ctx.path / 'fetch_telemetry.json').unlink()
    with pytest.raises(ArchiveCorruptionError, match='receipt|telemetry'):
        fetch_audit(ctx.path, [], [], [], tools.snapshot())


def test_plain_text_line_endings_survive_cache_and_archive_verification(ctx):
    from loop_research.repl_tools import ResearchTools
    from loop_research.archive_audit import fetch_audit
    original = 'First line.\r\nSecond line.\rFinal line.\n'
    tools = ResearchTools(NoModel(), ctx, fetcher=PageFetcher(ctx,
        request=lambda *args: response(original, 'text/plain; charset=utf-8')))
    assert tools.fetch('https://example.org/') == original
    assert tools.fetch('https://example.org/', focus='last line') == original
    assert all(row['direct_receipt_verified'] for row in
               fetch_audit(ctx.path, [], [], [], tools.snapshot()))


def test_http_trickle_cannot_extend_total_download_deadline(ctx, monkeypatch):
    from loop_research import page_fetch
    from loop_research.page_fetch import FetchError
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', '15')
            self.end_headers()
            try:
                for _ in range(15):
                    self.wfile.write(b'x')
                    self.wfile.flush()
                    time.sleep(.04)
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setattr(page_fetch, 'resolve_public', lambda url: ('127.0.0.1', server.server_port))
        ctx.config.codex.timeout_s = .1
        fetcher = PageFetcher(ctx)
        fetcher.request = lambda url, timeout: REAL_REQUEST(fetcher, url, timeout)
        started = time.monotonic()
        try:
            with pytest.raises(FetchError, match='download_error'):
                fetcher.fetch('http://unlisted.example/')
            assert time.monotonic() - started < .4
        finally:
            server.shutdown()
            thread.join(5)


def test_name_resolution_obeys_download_deadline(ctx, monkeypatch):
    from loop_research import page_fetch
    from loop_research.page_fetch import FetchError
    def slow_resolve(url):
        time.sleep(.5)
        return ('127.0.0.1', 1)
    monkeypatch.setattr(page_fetch, 'resolve_public', slow_resolve)
    ctx.config.codex.timeout_s = .05
    fetcher = PageFetcher(ctx)
    fetcher.request = lambda url, timeout: REAL_REQUEST(fetcher, url, timeout)
    started = time.monotonic()
    with pytest.raises(FetchError, match='download_error'):
        fetcher.fetch('http://unlisted.example/')
    assert time.monotonic() - started < .3


def test_cancellation_interrupts_response_headers_and_records_cancelled(ctx, monkeypatch):
    from concurrent.futures import Future, CancelledError
    from loop_research import page_fetch
    ctx.cancellation = Future()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            ctx.cancellation.cancel()
            time.sleep(.5)
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        monkeypatch.setattr(page_fetch, 'resolve_public', lambda url: ('127.0.0.1', server.server_port))
        fetcher = PageFetcher(ctx)
        fetcher.request = lambda url, timeout: REAL_REQUEST(fetcher, url, timeout)
        started = time.monotonic()
        try:
            with pytest.raises(CancelledError):
                fetcher.fetch('http://unlisted.example/')
            assert time.monotonic() - started < .3
            receipt, = (ctx.path / 'downloads').glob('*.json')
            assert json.loads(receipt.read_text())['status'] == 'cancelled'
        finally:
            server.shutdown()
            thread.join(5)
