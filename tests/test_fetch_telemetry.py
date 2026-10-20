import json
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

import pytest

from loop_research.archive import RunContext, read_jsonl
from loop_research.codex_backend import CodexBackend, CodexError
from loop_research.repl_tools import ResearchTools
from loop_research.selfcheck import check
from loop_research.trace import Trace
from test_agent_tools import Replies, install_fetch


def web_events(url='https://example.org/'):
    # Complete observed web-event shapes from an archived run.
    # A result's line-count snippet is not its raw page body.
    return [
        {'type': 'item.started', 'item': {'id': 'exec-fixture', 'type': 'web_search',
            'query': '', 'action': {'type': 'other'}}},
        {'type': 'item.completed', 'item': {'id': 'exec-fixture', 'type': 'web_search',
            'query': url, 'action': {'type': 'open_page', 'url': url},
            'results': [{'type': 'text_result', 'domain': 'example.org',
                'ref_id': 'turn54view0', 'snippet': 'Total lines: 461',
                'title': 'Fixture page', 'url': 'https://example.org/result'}]}},
    ]


@pytest.mark.parametrize('timeout', [False, True])
def test_backend_archives_complete_web_events_even_without_full_text_logging(ctx, timeout):
    ctx.config.codex.max_retries = 0
    assert not ctx.config.codex.log_full_text
    events = web_events()
    stdout = 'non-JSON diagnostic\n' + '\n'.join(map(json.dumps, events))

    def runner(command, **kwargs):
        if timeout:
            raise subprocess.TimeoutExpired(command, kwargs['timeout'], output=stdout.encode())
        Path(command[command.index('--output-last-message') + 1]).write_text('Rendered text')
        return SimpleNamespace(returncode=0, stdout=stdout, stderr='')

    backend = CodexBackend(ctx, runner=runner)
    if timeout:
        with pytest.raises(CodexError):
            backend.complete('Fixture', purpose='search', web=True)
    else:
        assert backend.complete('Fixture', purpose='search', web=True) == 'Rendered text'
    call, = read_jsonl(ctx.path / 'codex_calls.jsonl')
    assert call['web_events'] == [
        {'stdout_line': 2, 'event': events[0]}, {'stdout_line': 3, 'event': events[1]}]
    assert backend.last_web_events == call['web_events']
    assert call['web_actions'] == [{'type': 'open_page', 'url': 'https://example.org/'}]
    assert 'prompt' not in call and 'response' not in call


def test_fetch_sizes_link_shared_and_resumed_cache_to_exact_owner_receipt(ctx, monkeypatch):
    from loop_research import repl_tools
    waiting = threading.Event()
    raw = '  Café ☕  \n'

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(repl_tools, 'Future', ObservedFuture)

    def download(url):
        assert waiting.wait(3)
        return raw

    downloads = install_fetch(monkeypatch, download)
    backend = Replies()
    tools = ResearchTools(backend, ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(tools.fetch, 'https://example.org/', focus)
                    for focus in ('first focus', 'different focus')]
        assert [request.result(timeout=5) for request in requests] == [raw, raw]
    restored = ResearchTools(backend, ctx)
    assert restored.fetch('https://example.org/', 'third focus') == raw
    telemetry = ctx.load('fetch_telemetry.json')
    assert telemetry is not None, 'Every fetch needs a separate measurement archive'
    owner, shared, cached = telemetry
    assert [(item['source'], item['status']) for item in telemetry] == [
        ('backend', 'succeeded'), ('shared', 'succeeded'), ('cache', 'succeeded')]
    assert shared['owner_id'] == cached['owner_id'] == owner['id']
    for item in telemetry:
        assert item['returned_chars'] == item['readable_chars'] == len(raw)
        assert item['evidence_eligible'] is True
        assert item['raw_page_chars'] == len(raw)
        assert item['raw_page_bytes'] == len(raw.encode('utf-8'))
        assert item['fetch_path'] == 'direct-readable-v1'
        assert 'attempts' not in item
    assert owner['receipt']
    assert shared['receipt'] == cached['receipt'] == owner['receipt']
    assert downloads == ['https://example.org/'] and backend.calls == []
    assert not (ctx.path / 'codex_calls.jsonl').exists()
    assert list(restored.cache) == [
        '["fetch", "https://example.org/", "direct-readable-v1", "unicode-layout-controls-v1"]']
    assert all('returned_chars' not in request for request in restored.snapshot()['fetches'])


def test_pending_shared_fetch_retains_owner_and_cancellation_never_writes_late_sizes(ctx, monkeypatch):
    from loop_research import repl_tools
    ctx.cancellation = Future()
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(repl_tools, 'Future', ObservedFuture)

    def download(url):
        entered.set()
        assert release.wait(5)
        return 'Late response'

    install_fetch(monkeypatch, download)
    tools = ResearchTools(Replies(), ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(tools.fetch, 'https://example.org/') for _ in range(2)]
        try:
            assert entered.wait(3) and waiting.wait(3)
            owner, shared = ctx.load('fetch_telemetry.json')
            assert shared['owner_id'] == owner['id']
            assert owner['status'] == shared['status'] == 'pending'
            ctx.cancellation.cancel()
            archived = (ctx.path / 'fetch_telemetry.json').read_bytes()
        finally:
            ctx.cancellation.cancel()
            release.set()
        for request in requests:
            with pytest.raises(CancelledError):
                request.result(timeout=5)
    assert (ctx.path / 'fetch_telemetry.json').read_bytes() == archived
    for item in ctx.load('fetch_telemetry.json'):
        assert item['status'] == 'cancelled' and item['returned_chars'] is None
        assert item['evidence_eligible'] is False and item['raw_page_chars'] is None


@pytest.mark.parametrize('mode', ['http_status', 'download_error', 'no_readable_text', 'unexpected', 'validation'])
def test_unavailable_fetch_sizes_never_count_failure_as_page_evidence(ctx, monkeypatch, mode):
    from loop_research.page_fetch import FetchError
    error = RuntimeError('Fixture bug') if mode == 'unexpected' else FetchError(mode, 'Fixture unavailable')
    downloads = install_fetch(monkeypatch, error)
    backend = Replies()
    tools = ResearchTools(backend, ctx)
    if mode == 'validation':
        with pytest.raises(ValueError):
            tools.fetch('file:///private')
    elif mode == 'unexpected':
        with pytest.raises(RuntimeError, match='Fixture bug'):
            tools.fetch('https://example.org/')
    else:
        assert tools.fetch('https://example.org/') == 'FETCH_FAILED'
    telemetry = ctx.load('fetch_telemetry.json')
    assert telemetry is not None
    request, = telemetry
    assert request['raw_page_chars'] is None and request['raw_page_chars_reason']
    assert request.get('raw_page_bytes') is None and request.get('readable_chars') is None
    assert request['returned_chars'] == (None if mode in ('validation', 'unexpected') else 12)
    assert request['evidence_eligible'] is False
    assert len(downloads) == (0 if mode == 'validation' else 1)
    assert backend.calls == []


def test_legacy_model_fetch_cache_is_refetched_with_direct_receipt(ctx, monkeypatch):
    ctx.save('tool_cache.json', {'["fetch", "https://example.org/", ""]': 'Old model-rendered text'})
    downloads = install_fetch(monkeypatch, 'Direct page text')
    tools = ResearchTools(Replies(), ctx)
    assert tools.fetch('https://example.org/') == 'Direct page text'
    request, = ctx.load('fetch_telemetry.json')
    assert request['source'] == 'backend' and request['status'] == 'succeeded'
    assert request['evidence_eligible'] is True and request['receipt']
    assert request['raw_page_bytes'] == request['raw_page_chars'] == request['readable_chars'] == 16
    assert downloads == ['https://example.org/']


def test_fetch_telemetry_keeps_model_inputs_outputs_and_selfcheck_identical_with_trace(tmp_path, config, task, monkeypatch):
    from loop_research import page_fetch
    monkeypatch.setattr(page_fetch, 'uuid4', lambda: SimpleNamespace(hex='fixture-download'))
    downloads = install_fetch(monkeypatch, 'Rendered text')
    observations = []
    for enabled in (False, True):
        ctx = RunContext(tmp_path, 'traced' if enabled else 'plain', config, 'fixture')
        if enabled:
            ctx.trace = Trace(ctx.path)
        backend = Replies()
        tools = ResearchTools(backend, ctx)
        result = tools.fetch('https://example.org/', 'Fixture focus')
        evidence = tools.snapshot()
        report = check(task, {'rows': []}, evidence, {})
        observations.append((backend.calls, result, evidence, report))
        assert ctx.load('fetch_telemetry.json') is not None
        assert 'raw_page_chars' not in json.dumps(report)
        assert 'web_events' not in json.dumps(report)
        assert backend.calls == []
    assert observations[0] == observations[1]
    assert downloads == ['https://example.org/', 'https://example.org/']
