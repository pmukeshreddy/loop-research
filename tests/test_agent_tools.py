import json
from datetime import date
import threading
from concurrent.futures import CancelledError, ThreadPoolExecutor

import pytest

from loop_research.agent import citation_check, make_prompt, parse_output
from loop_research.repl_tools import ResearchTools
from loop_research.rlm_codex_client import CodexLM, transcript


class Replies:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []
        self.last_usage = {"input_tokens": 7, "output_tokens": 3}
        self.local = threading.local()

    def record(self, prompt, kwargs):
        self.calls.append((prompt, kwargs))
        assert kwargs.get("purpose") != "fetch", "Page fetch must not dispatch a model"
        self.local.web_actions = []

    @property
    def last_web_actions(self):
        return getattr(self.local, "web_actions", [])

    def complete(self, prompt, **kwargs):
        self.record(prompt, kwargs)
        return next(self.replies)


def install_fetch(monkeypatch, reply):
    """Replace only direct HTTP transport; exercise real decoding and extraction."""
    from loop_research.page_fetch import PageFetcher
    calls = []

    def request(self, url, timeout):
        calls.append(url)
        response = reply(url) if callable(reply) else reply
        if isinstance(response, BaseException):
            raise response
        if isinstance(response, str):
            response = {'status': 200, 'headers': {'content-type': 'text/plain; charset=utf-8'},
                        'body': response.encode('utf-8'), 'peer_ip': '93.184.216.34'}
        return response

    monkeypatch.setattr(PageFetcher, '_request', request)
    return calls


def test_transcript_and_usage():
    prompt = [{"role": "system", "content": "rules"}, {"role": "user", "content": {"task": "fixture"}}]
    assert transcript(prompt) == '<system>\nrules\n</system>\n\n<user>\n{"task": "fixture"}\n</user>'
    backend = Replies("done")
    client = CodexLM(backend, model="fixture", purpose="sub")
    assert client.completion(prompt) == "done"
    assert backend.calls[0][1] == {"purpose": "sub", "model": "fixture"}
    assert client.get_last_usage().total_input_tokens == 7
    assert client.get_usage_summary().model_usage_summaries["fixture"].total_output_tokens == 3


def test_valid_output_and_repair(benchmark, task, output):
    contract = benchmark.output_contract(task)
    backend = Replies(json.dumps(output))
    assert parse_output(json.dumps(output), contract, backend) == (output, [], False)
    assert backend.calls == []
    parsed, errors, repaired = parse_output("invalid", contract, backend)
    assert parsed == output and errors and repaired
    assert backend.calls[0][1]["purpose"] == "repair"
    assert "Do not research" in backend.calls[0][0]


def test_invalid_output_after_one_failed_repair_is_visible(benchmark, task):
    backend = Replies('{"rows": [{}]}')
    with pytest.raises(ValueError, match="Output validation failed after repair") as error:
        parse_output("invalid", benchmark.output_contract(task), backend)
    assert 'Invalid JSON' in str(error.value) and 'Field required' in str(error.value)
    assert len(backend.calls) == 1


def test_citations(output):
    assert citation_check(output, ["https://example.org/"]) == []
    assert len(citation_check(output, [])) == 2
    output["rows"][0]["cells"]["value"]["sources"] = []
    assert citation_check(output, ["https://example.org"]) == ["/rows/0/cells/value"]


def test_prompt_order(benchmark, task, config):
    prompt, asof, source = make_prompt(task, benchmark.output_contract(task), [{"kind": "memory", "body": "fixture memory"}], as_of="today", config=config)
    headings = ["TASK\n", "SPEC\n", "AS-OF DATE\n", "RELEVANT HARNESS\n", "TOOLS\n", "METHOD\n", "OUTPUT CONTRACT\n"]
    assert [prompt.index(x) for x in headings] == sorted(prompt.index(x) for x in headings)
    assert source == "today" and asof in prompt


def test_prompt_documents_batched_discovery_and_fetching(benchmark, task, config):
    prompt, _, _ = make_prompt(task, benchmark.output_contract(task), [], as_of="today", config=config)
    tools, method = prompt.split("TOOLS\n")[1].split("METHOD\n")
    assert "search_many(queries, k=8)" in tools
    assert "fetch_many(urls, focus='')" in tools
    assert "input order" in tools
    method = method.split("OUTPUT CONTRACT\n")[0]
    assert "search_many" in method and "fetch_many" in method


@pytest.mark.parametrize('policy,task_date,expected,source', [
    ('2024-02-29', None, '2024-02-29', 'config'),
    ('today', date(2020, 1, 2), '2020-01-02', 'task'),
    ('2024-02-29', date(2020, 1, 2), '2020-01-02', 'task'),
])
def test_prompt_uses_explicit_date_policy_and_ignores_raw_fallback(benchmark, task, config, policy, task_date, expected, source):
    task.as_of_date = task_date
    task.raw['fallback_as_of_date'] = '1900-01-01'
    prompt, actual, actual_source = make_prompt(task, benchmark.output_contract(task), [], as_of=policy, config=config)
    assert (actual, actual_source) == (expected, source)
    assert f'{expected} (source: {source})' in prompt


def test_today_policy_is_archived_and_reused_after_calendar_changes(tmp_path, benchmark, task, config, monkeypatch):
    from loop_research import agent
    class FirstDay(date):
        @classmethod
        def today(cls):
            return cls(2024, 2, 29)
    class SecondDay(date):
        @classmethod
        def today(cls):
            return cls(2024, 3, 1)
    path = tmp_path / 'as_of.json'
    monkeypatch.setattr(agent, 'date', FirstDay)
    first = make_prompt(task, benchmark.output_contract(task), [], as_of='today', config=config, date_archive=path)
    monkeypatch.setattr(agent, 'date', SecondDay)
    resumed = make_prompt(task, benchmark.output_contract(task), [], as_of='today', config=config, date_archive=path)
    assert first == resumed
    assert first[1:] == ('2024-02-29', 'today')


@pytest.mark.parametrize('model', [None, '', '   '])
def test_rlm_clients_reject_missing_models(model):
    from loop_research.rlm_codex_client import CodexRLM
    with pytest.raises(ValueError, match='model'):
        CodexLM(Replies(), model=model)
    with pytest.raises(ValueError, match='model'):
        CodexRLM(Replies(), root_model=model, sub_model='fixture-sub')
    with pytest.raises(ValueError, match='model'):
        CodexRLM(Replies(), root_model='fixture-root', sub_model=model)


def test_recursive_subcall_rejects_unconfigured_model_before_dispatch():
    from loop_research.rlm_codex_client import CodexRLM
    backend = Replies('unused')
    rlm = CodexRLM(backend, root_model='fixture-root', sub_model='fixture-sub')
    with pytest.raises(ValueError, match='configured sub model'):
        rlm._subcall('fixture', model='unconfigured')
    assert backend.calls == []


@pytest.mark.parametrize('model,depth', [('unconfigured', 0), ('unconfigured', 1), ('fixture-root', 1)])
def test_rlm_handler_rejects_model_fallback_and_role_override(model, depth):
    from loop_research.rlm_codex_client import CodexHandler
    backend = Replies('unused')
    handler = CodexHandler(CodexLM(backend, 'fixture-root', 'root'),
                           other_backend_client=CodexLM(backend, 'fixture-sub', 'sub'))
    with pytest.raises(ValueError, match='configured model'):
        handler.get_client(model, depth).completion('fixture')
    assert backend.calls == []


def test_search_fetch_cache_and_ledger(ctx, monkeypatch):
    hits = {"results": [{"title": "good", "url": "https://example.org/a", "snippet": "text"},
                        {"title": "bad", "url": "file:///tmp/secret", "snippet": "invalid"}]}
    from loop_research.page_fetch import FetchError
    downloads = install_fetch(monkeypatch, lambda url: 'faithful page text' if url.endswith('/a')
                              else FetchError('http_status', 'HTTP 503'))
    backend = Replies(json.dumps(hits))
    tools = ResearchTools(backend, ctx)
    assert len(tools.search("Fixture query")) == 1
    assert tools.search(" fixture   QUERY ") == tools.search("Fixture query")
    assert tools.fetch("https://example.org/a#fragment") == "faithful page text"
    assert tools.fetch("https://EXAMPLE.org/a") == "faithful page text"
    assert tools.fetch("https://example.org/b") == "FETCH_FAILED"
    assert len(backend.calls) == 1
    assert downloads == ['https://example.org/a', 'https://example.org/b']
    assert ctx.load("url_ledger.json") == ["https://example.org/a"]
    assert ResearchTools(Replies(), ctx).fetch("https://example.org/a") == "faithful page text"


def test_failed_fetch_is_retried_and_each_request_is_audited(ctx, monkeypatch):
    from loop_research.page_fetch import FetchError
    responses = iter([FetchError('http_status', 'HTTP 503'), 'Recovered page'])
    downloads = install_fetch(monkeypatch, lambda url: next(responses))
    backend = Replies()
    tools = ResearchTools(backend, ctx)
    url = "https://example.org/retry"
    assert tools.fetch(url) == "FETCH_FAILED"
    assert tools.cache == {} and ctx.load("tool_cache.json") == {}
    assert tools.fetch(url) == "Recovered page"
    assert tools.fetch(url) == "Recovered page"
    assert backend.calls == [] and downloads == [url, url]
    fetches = tools.snapshot()["fetches"]
    assert [(item["source"], item["status"]) for item in fetches] == [
        ("backend", "failed"), ("backend", "succeeded"), ("cache", "succeeded")]
    assert all(item["url"] == url for item in fetches)
    assert tools.snapshot()["failures"][0]["request_id"] == fetches[0]["id"]


@pytest.mark.parametrize('shared', [False, True])
def test_direct_fetch_failure_is_not_retried_and_remains_evidence_after_recovery(ctx, task, monkeypatch, shared):
    from concurrent.futures import Future
    from loop_research import repl_tools
    from loop_research.page_fetch import FetchError
    from loop_research.selfcheck import check

    ctx.config.codex.max_retries = 3
    waiting = threading.Event()
    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)
    monkeypatch.setattr(repl_tools, 'Future', ObservedFuture)
    attempts = []
    def download(url):
        with ThreadPoolExecutor(max_workers=1) as pool:
            def unlocked():
                acquired = tools.lock.acquire(timeout=1)
                if acquired:
                    tools.lock.release()
                return acquired
            assert pool.submit(unlocked).result(timeout=2), 'Tools lock held across a download'
        attempts.append(url)
        if len(attempts) == 1:
            if shared:
                assert waiting.wait(2), 'Duplicate fetch did not wait for its owner'
            raise FetchError('http_status', 'HTTP 503 transient fetch failure')
        return 'Recovered page'

    install_fetch(monkeypatch, download)
    backend = Replies()
    tools = ResearchTools(backend, ctx)
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(tools.fetch, 'https://example.org/') for _ in range(2 if shared else 1)]
        assert [request.result(timeout=5) for request in requests] == ['FETCH_FAILED'] * len(requests)
    assert len(attempts) == 1, 'A single explicit fetch must not retry internally'
    assert tools.fetch('https://example.org/') == 'Recovered page'
    assert tools.fetch('https://example.org/') == 'Recovered page'
    evidence = tools.snapshot()
    owner = evidence['fetches'][0]
    recovered, cached = evidence['fetches'][-2:]
    assert owner['status'] == 'failed' and owner['reason'] == 'http_status'
    assert 'transient fetch failure' in owner['error']
    if shared:
        follower = evidence['fetches'][1]
        assert follower['owner_id'] == owner['id'] and follower['source'] == 'shared'
        assert follower['status'] == 'failed' and follower['reason'] == 'http_status'
    assert recovered['source'] == 'backend' and recovered['status'] == 'succeeded'
    assert cached['source'] == 'cache' and cached['owner_id'] == recovered['id']
    assert all(item['fetch_path'] == 'direct-readable-v1' and 'attempts' not in item
               for item in evidence['fetches'])
    assert len(attempts) == 2 and backend.calls == []
    assert len(evidence['failures']) == (2 if shared else 1)
    assert evidence['failures'][0]['request_id'] == owner['id']
    assert any(item['type'] == 'failed_fetch' and item['request_id'] == owner['id']
               for item in check(task, {'rows': []}, evidence, {})['signals'])
    assert ctx.load('evidence.json') == evidence


@pytest.mark.parametrize("url, focus", [("file:///private", ""), (None, ""), ("https://example.org/", None)])
def test_invalid_fetch_is_audited_without_transport_dispatch(ctx, url, focus, monkeypatch):
    downloads = install_fetch(monkeypatch, "Must not be downloaded")
    backend = Replies()
    tools = ResearchTools(backend, ctx)
    with pytest.raises(ValueError):
        tools.fetch(url, focus)
    assert backend.calls == [] and downloads == [] and tools.cache == {}
    request = tools.snapshot()["fetches"][0]
    assert (request["source"], request["status"], request["reason"]) == ("validation", "failed", "validation_error")
    assert tools.snapshot()["failures"][0]["request_id"] == request["id"]
    assert ctx.load("evidence.json") == tools.snapshot()


def test_legacy_failed_fetch_cache_does_not_prevent_retry(ctx, monkeypatch):
    ctx.save("tool_cache.json", {'["fetch", "https://example.org/", ""]': "FETCH_FAILED"})
    downloads = install_fetch(monkeypatch, 'Recovered page')
    tools = ResearchTools(Replies(), ctx)
    assert tools.fetch("https://example.org/") == "Recovered page"
    assert tools.snapshot()["fetches"][0]["source"] == "backend"
    assert "FETCH_FAILED" not in ctx.load("tool_cache.json").values()
    assert downloads == ['https://example.org/']


def test_search_audits_every_dropped_hit_including_after_limit(ctx):
    hits = [None, "not a hit", {"title": "missing", "url": "https://example.org/missing"},
            {"title": "invalid", "url": "file:///private", "snippet": "text"},
            {"title": "kept", "url": "https://example.org/kept", "snippet": "text"},
            {"title": "excess", "url": "https://example.org/excess", "snippet": "text"},
            {"title": 7, "url": "https://example.org/malformed", "snippet": "text"},
            {"title": "late invalid", "url": "not a URL", "snippet": "text"}]
    tools = ResearchTools(Replies(json.dumps({"results": hits})), ctx)
    assert tools.search("fixture", k=1) == [hits[4]]
    dropped = tools.snapshot()["dropped_search_hits"]
    assert [(item["index"], item["reason"]) for item in dropped] == [
        (0, "malformed_hit"), (1, "malformed_hit"), (2, "malformed_fields"),
        (3, "invalid_url"), (5, "excess_k"), (6, "malformed_fields"), (7, "invalid_url")]
    assert all(item["query"] == "fixture" and item["hit"] == hits[item["index"]] for item in dropped)
    assert ctx.load("url_ledger.json") == ["https://example.org/kept"]
    assert ctx.load("evidence.json") == tools.snapshot()


@pytest.mark.parametrize("response", [None, [], {}, {"results": None}, {"results": {}}])
def test_search_rejects_malformed_response_structure_with_evidence(ctx, response):
    tools = ResearchTools(Replies(json.dumps(response)), ctx)
    with pytest.raises(ValueError, match="Search response must contain a results list"):
        tools.search("fixture")
    assert tools.cache == {} and tools.ledger == set()
    assert tools.snapshot()["failures"][0]["operation"] == "search"


@pytest.mark.parametrize("requests", [1, 2])
def test_cancelled_fetch_is_audited_before_close_and_never_writes_late(ctx, monkeypatch, requests):
    from concurrent.futures import CancelledError, Future
    from loop_research import repl_tools
    ctx.cancellation = Future()
    entered, release, waiting = threading.Event(), threading.Event(), threading.Event()

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(repl_tools, "Future", ObservedFuture)

    def download(url):
        entered.set()
        assert release.wait(5)
        return "Late page"

    install_fetch(monkeypatch, download)
    tools = ResearchTools(Replies(), ctx)
    with ThreadPoolExecutor(max_workers=requests) as pool:
        futures = [pool.submit(tools.fetch, "https://example.org/") for _ in range(requests)]
        try:
            assert entered.wait(5)
            if requests > 1:
                assert waiting.wait(5)
            assert [item["status"] for item in tools.snapshot()["fetches"]] == ["pending"] * requests
            ctx.cancellation.cancel()
            cancelled = ctx.load("evidence.json")
            assert [item["status"] for item in cancelled["fetches"]] == ["cancelled"] * requests
            assert [item["reason"] for item in cancelled["failures"]] == ["cancelled"] * requests
            assert [item["source"] for item in cancelled["fetches"]] == ["backend", "shared"][:requests]
            archived = (ctx.path / "evidence.json").read_bytes()
        finally:
            release.set()
        for future in futures:
            with pytest.raises(CancelledError):
                future.result(timeout=5)
    assert tools.snapshot() == cancelled
    assert (ctx.path / "evidence.json").read_bytes() == archived
    assert tools.cache == {} and tools.snapshot()["fetched"] == {}


@pytest.mark.parametrize("kind", ["search", "fetch"])
def test_batched_tools_overlap_preserve_order_cache_and_ledger(ctx, kind, monkeypatch):
    ctx.config.codex.max_concurrent = 2
    barrier, second_done = threading.Barrier(2, timeout=5), threading.Event()
    counter_lock = threading.Lock()
    calls, completed = [], []
    active = peak = 0

    def cache_lock_available():
        # Other workers may briefly hold the lock to persist their results.
        acquired = tools.lock.acquire(timeout=2)
        if acquired:
            tools.lock.release()
        return acquired

    def respond(target):
        nonlocal active, peak
        with ThreadPoolExecutor(max_workers=1) as probe:
            assert probe.submit(cache_lock_available).result(timeout=5), "Cache lock held during transport call"
        index = next(i for i in range(3) if f"fixture-{i}" in target)
        with counter_lock:
            calls.append(index)
            active += 1
            peak = max(peak, active)
        try:
            if index < 2:
                barrier.wait()
            if index == 0:
                assert second_done.wait(5)
            completed.append(index)
            if kind == "search":
                return json.dumps({"results": [{"title": f"fixture-{index}",
                    "url": f"https://example.org/fixture-{index}", "snippet": "Fixture evidence"}]})
            if index == 2:
                from loop_research.page_fetch import FetchError
                raise FetchError('http_status', 'HTTP 503')
            return f"Fixture page {index}"
        finally:
            with counter_lock:
                active -= 1
            if index == 1:
                second_done.set()

    class Backend(Replies):
        def complete(self, prompt, **kwargs):
            self.record(prompt, kwargs)
            return respond(prompt)

    if kind == "fetch":
        install_fetch(monkeypatch, respond)
    tools = ResearchTools(Backend(), ctx)
    batch = getattr(tools, kind + "_many")
    inputs = [f"fixture-{i}" if kind == "search" else f"https://example.org/fixture-{i}" for i in range(3)]
    alias = " FIXTURE-0 " if kind == "search" else "https://EXAMPLE.org/fixture-0#section"
    options = {"k": 1} if kind == "search" else {"focus": "Fixture focus"}
    result = batch([*inputs, alias, inputs[1]], **options)
    expected = [[{"title": f"fixture-{i}", "url": f"https://example.org/fixture-{i}",
                  "snippet": "Fixture evidence"}] for i in range(3)] if kind == "search" else [
                      "Fixture page 0", "Fixture page 1", "FETCH_FAILED"]
    assert result == [*expected, expected[0], expected[1]]
    assert peak == 2 and completed.index(1) < completed.index(0)
    assert sorted(calls) == [0, 1, 2]
    assert ctx.load("tool_cache.json") == tools.cache
    assert len(tools.cache) == (3 if kind == "search" else 2)
    assert "FETCH_FAILED" not in tools.cache.values()
    ledger = [f"https://example.org/fixture-{i}" for i in range(3 if kind == "search" else 2)]
    assert ctx.load("url_ledger.json") == ledger and tools.ledger == set(ledger)
    for value, expected_value in zip(inputs, expected):
        assert getattr(tools, kind)(value, **options) == expected_value
    if kind == "fetch":
        from loop_research.page_fetch import FetchError
        install_fetch(monkeypatch, FetchError('http_status', 'HTTP 503'))
    restored = ResearchTools(Replies(), ctx)
    assert getattr(restored, kind + "_many")(inputs, **options) == expected
    assert batch([], **options) == [] and len(calls) == (3 if kind == "search" else 4)
    if kind == "fetch":
        fetches = restored.snapshot()["fetches"]
        assert len(fetches) == 11
        assert {item["url"]: (item["source"], item["status"]) for item in fetches[-3:]} == {
            "https://example.org/fixture-0": ("cache", "succeeded"),
            "https://example.org/fixture-1": ("cache", "succeeded"),
            "https://example.org/fixture-2": ("backend", "failed")}
        assert len(restored.snapshot()["failures"]) == 3


@pytest.mark.parametrize("kind", ["search", "fetch"])
@pytest.mark.parametrize("error", [RuntimeError, CancelledError])
def test_duplicate_inflight_requests_share_cache_and_propagate_failure(ctx, kind, error, monkeypatch):
    from concurrent.futures import Future
    from loop_research import repl_tools
    waiting = threading.Event()

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(repl_tools, "Future", ObservedFuture, raising=False)
    calls = []

    def respond(target):
        calls.append(target)
        if len(calls) == 1:
            assert waiting.wait(5), "Duplicate request did not wait for its cache entry"
            raise error("Fixture backend failure")
        return '{"results": []}' if kind == "search" else "Fixture page"

    class Backend(Replies):
        def complete(self, prompt, **kwargs):
            self.record(prompt, kwargs)
            return respond(prompt)

    if kind == "fetch":
        install_fetch(monkeypatch, respond)
    tools = ResearchTools(Backend(), ctx)
    value = "fixture" if kind == "search" else "https://example.org/"
    call = getattr(tools, kind)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(call, value) for _ in range(2)]
        for future in futures:
            with pytest.raises(error, match="Fixture backend failure"):
                future.result(timeout=10)
    assert len(calls) == 1 and tools.cache == {} and tools.ledger == set()
    if kind == "fetch":
        fetches = tools.snapshot()["fetches"]
        status = "cancelled" if error is CancelledError else "failed"
        assert [(item["source"], item["status"]) for item in fetches] == [
            ("backend", status), ("shared", status)]
        assert fetches[1]["owner_id"] == fetches[0]["id"]
        assert {item["request_id"] for item in tools.snapshot()["failures"]} == {item["id"] for item in fetches}
    expected = [] if kind == "search" else "Fixture page"
    assert call(value) == call(value) == expected
    assert len(calls) == 2
    if kind == "fetch":
        assert [(item["source"], item["status"]) for item in tools.snapshot()["fetches"][-2:]] == [
            ("backend", "succeeded"), ("cache", "succeeded")]


@pytest.mark.parametrize('reason', ['http_status', 'download_error', 'no_readable_text'])
def test_direct_download_failure_never_falls_back_to_model_text(ctx, monkeypatch, reason):
    from loop_research.page_fetch import FetchError, TEXT_POLICY, verify_receipt
    error = 'Fixture download failed'
    reply = FetchError(reason, error)
    if reason == 'no_readable_text':
        # A failed extraction follows a real downloaded body, not an HTTP exception.
        body = b'<html><script>Not rendered.</script><p hidden>Hidden text.</p></html>'
        reply = {'status': 200, 'headers': {'content-type': 'text/html; charset=utf-8'}, 'body': body}
        error = 'No static readable text; no model or browser fallback'
    downloads = install_fetch(monkeypatch, reply)
    backend = Replies('A fabricated page that no HTTP transport downloaded')
    tools = ResearchTools(backend, ctx)
    assert tools.fetch("https://example.org/") == "FETCH_FAILED"
    assert downloads == ['https://example.org/'] and backend.calls == []
    assert tools.snapshot()["fetched"] == {}
    assert tools.ledger == set()
    assert tools.snapshot()["failures"] == [{"operation": "fetch", "url": "https://example.org/",
        "request_id": 1, "source": "backend", "reason": reason, 'error': error}]
    assert tools.cache == {}
    if reason == 'no_readable_text':
        receipt = ctx.load('fetch_telemetry.json')[0]['receipt']
        assert receipt['status'] == 'failed' and receipt['reason'] == reason
        assert receipt['parser'] == 'stdlib-html-readable-v1'
        assert (ctx.path / receipt['raw_path']).read_bytes() == body
        assert (ctx.path / receipt['extraction_path']).read_bytes() == b''
        assert receipt['extraction_bytes'] == receipt['extraction_chars'] == 0
        verify_receipt(ctx.path, receipt, expected_policy=TEXT_POLICY)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_root_sub_recursive_and_fallback_routes_are_codex(depth):
    from loop_research.rlm_codex_client import CodexRLM
    class RoutingBackend(Replies):
        def complete(self, prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            if kwargs["purpose"] == "root":
                return '```repl\nanswer["content"] = rlm_query("child")\nanswer["ready"] = True\n```'
            if prompt == "leaf":
                return "leaf answer"
            return '```repl\nanswer["content"] = llm_query("leaf")\nanswer["ready"] = True\n```' if depth > 1 else "child answer"
    backend = RoutingBackend()
    result = CodexRLM(backend, root_model="root-fixture", sub_model="sub-fixture",
                      max_depth=depth, max_iterations=1).completion("root")
    assert result.response == ("leaf answer" if depth > 1 else "child answer")
    assert backend.calls[0][1] == {"purpose": "root", "model": "root-fixture"}
    assert all(kwargs == {"purpose": "sub", "model": "sub-fixture"} for _, kwargs in backend.calls[1:])
    fallback = CodexRLM(backend, root_model="root-fixture", sub_model="sub-fixture", depth=depth, max_depth=depth)
    assert fallback.completion("leaf") == "leaf answer"
    assert backend.calls[-1][1] == {"purpose": "sub", "model": "sub-fixture"}


def test_wandr_repair_preserves_free_form_answer_without_strict_schema(ctx):
    from loop_research.benchmarks import Task
    from loop_research.benchmarks.wandr.data import WandrData
    task = Task(task_id='fixture-wandr', benchmark='wandr', question='Fixture research', language='en',
                spec={'nodes': [{'item_fields': ['name'], 'required_output_file': 'fixture.jsonl'}]})
    contract = WandrData(ctx.root, ctx.config).output_contract(task)
    output = {'files': {'fixture.jsonl': [{'item': {'name': 'fixture'}, 'url': 'https://example.org/',
               'excerpts': ['fixture quote'], 'answer': {'arbitrary_fact': {'nested': 'fixture value'}}}]}}
    backend = Replies(json.dumps(output))
    actual, errors, repaired = parse_output('invalid', contract, backend)
    assert actual == output and errors and repaired
    prompt, options = backend.calls[0]
    assert options.get('schema') is None
    assert json.dumps(contract.schema, ensure_ascii=False) in prompt
    assert 'Do not research' in prompt
    with pytest.raises(ValueError, match='Output validation failed after repair'):
        parse_output('invalid', contract, Replies('{"files": {}}'))


def test_parallel_subcalls_keep_codex_routing_and_same_model_usage():
    from loop_research.rlm_codex_client import CodexRLM
    class ParallelBackend(Replies):
        def complete(self, prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            if kwargs['purpose'] == 'root':
                return '```repl\nimport json\nanswer["content"] = json.dumps(llm_query_batched(["first", "second"]))\nanswer["ready"] = True\n```'
            return prompt + ' result'
    backend = ParallelBackend()
    result = CodexRLM(backend, root_model='same-fixture', sub_model='same-fixture', max_iterations=1).completion('root')
    assert json.loads(result.response) == ['first result', 'second result']
    assert sorted(options['purpose'] for _, options in backend.calls) == ['root', 'sub', 'sub']
    assert all(options['model'] == 'same-fixture' for _, options in backend.calls)
    usage = result.usage_summary.model_usage_summaries['same-fixture']
    assert usage.total_calls == 3 and usage.total_input_tokens == 21 and usage.total_output_tokens == 9
