import json
import threading
from concurrent.futures import ThreadPoolExecutor

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
        self.local.web_actions = ([{"type": "open_page", "url": prompt.splitlines()[0].split(": ", 1)[1]}]
                                  if kwargs.get("purpose") == "fetch" else [])

    @property
    def last_web_actions(self):
        return getattr(self.local, "web_actions", [])

    def complete(self, prompt, **kwargs):
        self.record(prompt, kwargs)
        return next(self.replies)


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


def test_empty_output_after_one_failed_repair(benchmark, task):
    backend = Replies('{"rows": [{}]}')
    parsed, errors, repaired = parse_output("invalid", benchmark.output_contract(task), backend)
    assert parsed == {"rows": []} and len(errors) == 2 and repaired
    assert len(backend.calls) == 1


def test_citations(output):
    assert citation_check(output, ["https://example.org/"]) == []
    assert len(citation_check(output, [])) == 2
    output["rows"][0]["cells"]["value"]["sources"] = []
    assert citation_check(output, ["https://example.org"]) == ["/rows/0/cells/value"]


def test_prompt_order(benchmark, task):
    prompt, asof, source = make_prompt(task, benchmark.output_contract(task), [{"kind": "memory", "body": "fixture memory"}])
    headings = ["TASK\n", "SPEC\n", "AS-OF DATE\n", "RELEVANT HARNESS\n", "TOOLS\n", "METHOD\n", "OUTPUT CONTRACT\n"]
    assert [prompt.index(x) for x in headings] == sorted(prompt.index(x) for x in headings)
    assert source == "today_fallback" and asof in prompt


def test_prompt_documents_batched_discovery_and_fetching(benchmark, task):
    prompt, _, _ = make_prompt(task, benchmark.output_contract(task), [])
    tools, method = prompt.split("TOOLS\n")[1].split("METHOD\n")
    assert "search_many(queries, k=8)" in tools
    assert "fetch_many(urls, focus='')" in tools
    assert "input order" in tools
    method = method.split("OUTPUT CONTRACT\n")[0]
    assert "search_many" in method and "fetch_many" in method


def test_search_fetch_cache_and_ledger(ctx):
    hits = {"results": [{"title": "good", "url": "https://example.org/a", "snippet": "text"},
                        {"title": "bad", "url": "file:///tmp/secret", "snippet": "invalid"}]}
    backend = Replies(json.dumps(hits), "faithful page text", "FETCH_FAILED")
    tools = ResearchTools(backend, ctx)
    assert len(tools.search("Fixture query")) == 1
    assert tools.search(" fixture   QUERY ") == tools.search("Fixture query")
    assert tools.fetch("https://example.org/a#fragment") == "faithful page text"
    assert tools.fetch("https://EXAMPLE.org/a") == "faithful page text"
    assert tools.fetch("https://example.org/b") == "FETCH_FAILED"
    assert len(backend.calls) == 3
    assert ctx.load("url_ledger.json") == ["https://example.org/a"]
    assert ResearchTools(Replies(), ctx).fetch("https://example.org/a") == "faithful page text"


@pytest.mark.parametrize("kind", ["search", "fetch"])
def test_batched_tools_overlap_preserve_order_cache_and_ledger(ctx, kind):
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

    class Backend(Replies):
        def complete(self, prompt, **kwargs):
            self.record(prompt, kwargs)
            nonlocal active, peak
            with ThreadPoolExecutor(max_workers=1) as probe:
                assert probe.submit(cache_lock_available).result(timeout=5), "Cache lock held during backend call"
            index = next(i for i in range(3) if f"fixture-{i}" in prompt)
            with counter_lock:
                calls.append(index)
                active += 1
                peak = max(peak, active)
            try:
                if index < 2:
                    barrier.wait()
                if index == 0:
                    assert second_done.wait(5)
                if kind == "search":
                    result = json.dumps({"results": [{"title": f"fixture-{index}",
                        "url": f"https://example.org/fixture-{index}", "snippet": "Fixture evidence"}]})
                else:
                    result = f"Fixture page {index}" if index < 2 else "FETCH_FAILED"
                completed.append(index)
                return result
            finally:
                with counter_lock:
                    active -= 1
                if index == 1:
                    second_done.set()

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
    assert ctx.load("tool_cache.json") == tools.cache and len(tools.cache) == 3
    ledger = [f"https://example.org/fixture-{i}" for i in range(3 if kind == "search" else 2)]
    assert ctx.load("url_ledger.json") == ledger and tools.ledger == set(ledger)
    for value, expected_value in zip(inputs, expected):
        assert getattr(tools, kind)(value, **options) == expected_value
    restored = ResearchTools(Replies(), ctx)
    assert getattr(restored, kind + "_many")(inputs, **options) == expected
    assert batch([], **options) == [] and len(calls) == 3


@pytest.mark.parametrize("kind", ["search", "fetch"])
def test_duplicate_inflight_requests_share_cache_and_propagate_failure(ctx, kind, monkeypatch):
    from concurrent.futures import Future
    from loop_research import repl_tools
    waiting = threading.Event()

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiting.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(repl_tools, "Future", ObservedFuture, raising=False)
    calls = []

    class Backend(Replies):
        def complete(self, prompt, **kwargs):
            self.record(prompt, kwargs)
            calls.append(prompt)
            if len(calls) == 1:
                assert waiting.wait(5), "Duplicate request did not wait for its cache entry"
                raise RuntimeError("Fixture backend failure")
            return '{"results": []}' if kind == "search" else "Fixture page"

    tools = ResearchTools(Backend(), ctx)
    value = "fixture" if kind == "search" else "https://example.org/"
    call = getattr(tools, kind)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(call, value) for _ in range(2)]
        for future in futures:
            with pytest.raises(RuntimeError, match="Fixture backend failure"):
                future.result(timeout=10)
    assert len(calls) == 1 and tools.cache == {} and tools.ledger == set()
    expected = [] if kind == "search" else "Fixture page"
    assert call(value) == call(value) == expected
    assert len(calls) == 2


@pytest.mark.parametrize("actions", [[], [{"type": "open_page", "url": "https://example.org/wrong"}],
                                     [{"type": "search", "query": "https://example.org/"}]])
def test_fetch_rejects_text_without_matching_completed_open(ctx, actions):
    class UnsupportedFetch(Replies):
        def complete(self, prompt, **kwargs):
            self.record(prompt, kwargs)
            self.local.web_actions = actions
            return "A fabricated page that the web tool never opened"

    tools = ResearchTools(UnsupportedFetch(), ctx)
    assert tools.fetch("https://example.org/") == "FETCH_FAILED"
    assert tools.snapshot()["fetched"] == {}
    assert tools.ledger == set()
    assert tools.snapshot()["failures"] == [{"operation": "fetch", "url": "https://example.org/"}]


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
    failed, errors, repaired = parse_output('invalid', contract, Replies('{"files": {}}'))
    assert failed == contract.empty and len(errors) == 2 and repaired


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
