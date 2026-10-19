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
            backend.complete('Fixture', purpose='fetch', web=True)
    else:
        assert backend.complete('Fixture', purpose='fetch', web=True) == 'Rendered text'
    call, = read_jsonl(ctx.path / 'codex_calls.jsonl')
    assert call['web_events'] == [
        {'stdout_line': 2, 'event': events[0]}, {'stdout_line': 3, 'event': events[1]}]
    assert backend.last_web_events == call['web_events']
    assert call['web_actions'] == [{'type': 'open_page', 'url': 'https://example.org/'}]
    assert 'prompt' not in call and 'response' not in call


def test_fetch_sizes_link_shared_and_resumed_cache_to_exact_owner_events(ctx, monkeypatch):
    from loop_research import repl_tools
    waiting = threading.Event()
    ctx.config.codex.max_retries = 1
    calls = []

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(repl_tools, 'Future', ObservedFuture)

    def runner(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            assert waiting.wait(3)
            return SimpleNamespace(returncode=1, stdout='', stderr='Retry fixture')
        Path(command[command.index('--output-last-message') + 1]).write_text('  Café ☕  \n')
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, web_events())), stderr='')

    tools = ResearchTools(CodexBackend(ctx, runner=runner, sleep=lambda _: None), ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(tools.fetch, 'https://example.org/') for _ in range(2)]
        assert [request.result(timeout=5) for request in requests] == ['Café ☕', 'Café ☕']
    restored = ResearchTools(tools.backend, ctx)
    assert restored.fetch('https://example.org/') == 'Café ☕'
    telemetry = ctx.load('fetch_telemetry.json')
    assert telemetry is not None, 'Every fetch needs a separate measurement archive'
    owner, shared, cached = telemetry
    assert [(item['source'], item['status']) for item in telemetry] == [
        ('backend', 'succeeded'), ('shared', 'succeeded'), ('cache', 'succeeded')]
    assert shared['owner_id'] == cached['owner_id'] == owner['id']
    for item in telemetry:
        assert item['returned_chars'] == 6
        assert item['evidence_eligible'] is True
        assert item['raw_page_chars'] is None
        assert item['raw_page_chars_reason'] == 'not_exposed_by_codex_web_events'
    records = read_jsonl(ctx.path / 'codex_calls.jsonl')
    assert [attempt['call_id'] for attempt in owner['attempts']] == [r['call_id'] for r in records]
    assert [attempt['status'] for attempt in owner['attempts']] == ['failed', 'succeeded']
    assert owner['attempts'][0]['web_event_indexes'] == []
    last = owner['attempts'][1]
    assert last['archive'] == 'codex_calls.jsonl' and last['web_event_indexes'] == [0, 1]
    assert records[1]['web_events'][last['web_event_indexes'][1]]['event'] == web_events()[1]
    assert 'attempts' not in shared and 'attempts' not in cached
    assert len(calls) == 2
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

    def runner(command, **kwargs):
        entered.set()
        assert release.wait(5)
        Path(command[command.index('--output-last-message') + 1]).write_text('Late response')
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, web_events())), stderr='')

    tools = ResearchTools(CodexBackend(ctx, runner=runner), ctx)
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


@pytest.mark.parametrize('mode', ['sentinel', 'missing_open', 'timeout', 'validation', 'legacy_cache'])
def test_unavailable_fetch_sizes_never_count_failure_as_page_evidence(ctx, mode):
    ctx.config.codex.max_retries = 0
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if mode == 'timeout':
            raise subprocess.TimeoutExpired(command, kwargs['timeout'])
        text = 'FETCH_FAILED' if mode == 'sentinel' else 'Rendered text'
        Path(command[command.index('--output-last-message') + 1]).write_text(text)
        events = [] if mode == 'missing_open' else web_events()
        return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, events)), stderr='')

    if mode == 'legacy_cache':
        ctx.save('tool_cache.json', {'["fetch", "https://example.org/", ""]': 'Cached text'})
    tools = ResearchTools(CodexBackend(ctx, runner=runner), ctx)
    if mode == 'validation':
        with pytest.raises(ValueError):
            tools.fetch('file:///private')
    elif mode == 'timeout':
        with pytest.raises(CodexError):
            tools.fetch('https://example.org/')
    else:
        assert tools.fetch('https://example.org/') == ('Cached text' if mode == 'legacy_cache' else 'FETCH_FAILED')
    telemetry = ctx.load('fetch_telemetry.json')
    assert telemetry is not None
    request, = telemetry
    assert request['raw_page_chars'] is None and request['raw_page_chars_reason']
    assert request['returned_chars'] == (11 if mode == 'legacy_cache' else 12 if mode in ('sentinel', 'missing_open') else None)
    assert request['evidence_eligible'] is (mode == 'legacy_cache')
    assert len(calls) == (0 if mode in ('validation', 'legacy_cache') else 1)
    if mode == 'legacy_cache':
        assert request['raw_page_chars_reason'] == 'cached_fetch_has_no_archived_web_events'


def test_fetch_telemetry_keeps_model_inputs_outputs_and_selfcheck_identical_with_trace(tmp_path, config, task, monkeypatch):
    from loop_research import codex_backend
    monkeypatch.setattr(codex_backend, 'uuid4', lambda: SimpleNamespace(hex='fixture-call'))
    observations = []
    for enabled in (False, True):
        ctx = RunContext(tmp_path, 'traced' if enabled else 'plain', config, 'fixture')
        if enabled:
            ctx.trace = Trace(ctx.path)
        dispatched = []

        def runner(command, **kwargs):
            dispatched.append(kwargs['input'])
            Path(command[command.index('--output-last-message') + 1]).write_text('Rendered text')
            return SimpleNamespace(returncode=0, stdout='\n'.join(map(json.dumps, web_events())), stderr='')

        tools = ResearchTools(CodexBackend(ctx, runner=runner), ctx)
        result = tools.fetch('https://example.org/', 'Fixture focus')
        evidence = tools.snapshot()
        report = check(task, {'rows': []}, evidence, {})
        observations.append((dispatched, result, evidence, report))
        assert ctx.load('fetch_telemetry.json') is not None
        assert 'raw_page_chars' not in json.dumps(report)
        assert 'web_events' not in json.dumps(report)
    assert observations[0] == observations[1]
