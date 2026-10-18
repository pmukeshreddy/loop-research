import json

import pytest

from loop_research.agent import citation_check, make_prompt, parse_output
from loop_research.repl_tools import ResearchTools
from loop_research.rlm_codex_client import CodexLM, ResearchREPL, transcript, validate_code


class Replies:
    def __init__(self, *replies):
        self.replies = iter(replies)
        self.calls = []
        self.last_usage = {"input_tokens": 7, "output_tokens": 3}

    def complete(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
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
    prompt, asof, source = make_prompt(task, benchmark.output_contract(task), "fixture playbook")
    headings = ["TASK\n", "SPEC\n", "AS-OF DATE\n", "RESEARCH PLAYBOOK\n", "TOOLS\n", "METHOD\n", "OUTPUT CONTRACT\n"]
    assert [prompt.index(x) for x in headings] == sorted(prompt.index(x) for x in headings)
    assert source == "today_fallback" and asof in prompt


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


@pytest.mark.parametrize("code", ["open('gold.csv')", "import os", "search.__globals__", "getattr(search, 'x')"])
def test_repl_rejects_local_access(code):
    with pytest.raises(ValueError):
        validate_code(code)


def test_repl_computation_and_completion():
    with ResearchREPL() as repl:
        result = repl.execute_code('import json\nanswer["content"] = json.dumps({"rows": []})\nanswer["ready"] = True')
        assert result.final_answer == '{"rows": []}'
        assert result.stderr == ""


@pytest.mark.parametrize("worker_code", [0, 1])
def test_research_operational_errors_surface(ctx, task, benchmark, monkeypatch, worker_code):
    from pathlib import Path
    from loop_research import agent
    from loop_research.archive import read_json, write_json

    class Worker:
        def __init__(self, command, **kwargs):
            request = read_json(Path(command[-1]))
            write_json(Path(request["result_path"]), {"text": "invalid output"})

        def wait(self, **kwargs):
            return worker_code

    class FailingBackend:
        def complete(self, *args, **kwargs):
            raise RuntimeError("fixture transport failure")

    monkeypatch.setattr(agent.subprocess, "Popen", Worker)
    monkeypatch.setattr(agent, "CodexBackend", lambda *args, **kwargs: FailingBackend())
    expected = "fixture transport failure" if worker_code == 0 else "Research worker failed"
    with pytest.raises(RuntimeError, match=expected):
        agent.run_task(task, benchmark, None, ctx)
    assert not (ctx.path / "output.json").exists()


@pytest.mark.parametrize("code", [
    "import json\nprint(json.codecs.open(context).read())",
    "from json import codecs\nprint(codecs.open(context).read())",
    "import re\nprint(re.enum.sys.modules['os'].getcwd())",
])
def test_repl_imports_cannot_escape_through_module_dependencies(tmp_path, code):
    secret = tmp_path / "answer-key.txt"
    secret.write_text("SECRET_FIXTURE")
    with ResearchREPL(context_payload=str(secret)) as repl:
        result = repl.execute_code(code.replace("context", repr(str(secret))))
    assert result.stderr, "An internal module dependency escaped the computation-only REPL"
    assert "SECRET_FIXTURE" not in result.stdout


def test_worker_records_real_rlm_trajectory(ctx, monkeypatch):
    from loop_research import agent
    from loop_research.archive import read_jsonl, write_json
    ctx.path.mkdir(parents=True)
    backend = Replies('```repl\nanswer["content"] = "fixture completion"\nanswer["ready"] = True\n```')
    monkeypatch.setattr(agent, "CodexBackend", lambda *args, **kwargs: backend)
    request = ctx.path / "request.json"
    write_json(request, {"root": str(ctx.root), "run_id": ctx.run_id, "task_id": ctx.task_id,
                        "config": ctx.config.model_dump(), "prompt": "fixture question",
                        "result_path": str(ctx.path / "worker_result.json")})
    agent.worker(request)
    trajectory = read_jsonl(ctx.path / "trajectory.jsonl")
    assert [item["type"] for item in trajectory] == ["metadata", "iteration"]
    assert trajectory[-1]["final_answer"] == "fixture completion"
    assert ctx.load("worker_result.json")["text"] == "fixture completion"
    assert len(list(ctx.path.glob("*.jsonl"))) == 1


@pytest.mark.parametrize("entry", ["worker", "repair"])
def test_resumed_task_budget_counts_interrupted_codex_attempt(ctx, task, benchmark, monkeypatch, entry):
    from pathlib import Path
    from loop_research import agent
    from loop_research.archive import read_json, write_json
    from loop_research.codex_backend import BudgetExceeded
    ctx.config.agent.max_codex_calls = 1
    write_json(ctx.path / 'codex_attempts/pending.json', {'call_id': 'pending', 'purpose': 'root'})
    write_json(ctx.path / 'codex_attempts/judge.json', {'call_id': 'judge', 'purpose': 'grade'})
    def no_remaining_budget(run_ctx, *, budget):
        assert budget.count == 1
        budget.reserve()
        raise AssertionError('A resumed task exceeded its call limit')
    monkeypatch.setattr(agent, 'CodexBackend', no_remaining_budget)
    if entry == 'worker':
        request = ctx.path / 'request.json'
        write_json(request, {'root': str(ctx.root), 'run_id': ctx.run_id, 'task_id': ctx.task_id,
                            'config': ctx.config.model_dump(), 'prompt': 'fixture',
                            'result_path': str(ctx.path / 'worker_result.json')})
        with pytest.raises(BudgetExceeded, match='call limit'):
            agent.worker(request)
    else:
        class Worker:
            def __init__(self, command, **kwargs):
                request = read_json(Path(command[-1]))
                write_json(Path(request['result_path']), {'text': 'invalid output'})
            def wait(self, **kwargs):
                return 0
        monkeypatch.setattr(agent.subprocess, 'Popen', Worker)
        with pytest.raises(BudgetExceeded, match='call limit'):
            agent.run_task(task, benchmark, None, ctx)
    assert not (ctx.path / 'output.json').exists()


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


def test_repl_string_format_cannot_introspect_tool_globals():
    def fixture_tool():
        return "unused"
    with ResearchREPL(custom_tools={"search": fixture_tool}) as repl:
        result = repl.execute_code('print("{0.__globals__}".format(search))')
    assert result.stderr
    assert "__builtins__" not in result.stdout


def test_task_deadline_is_shared_by_worker_and_repair(ctx, task, benchmark, output, monkeypatch):
    from pathlib import Path
    from loop_research import agent
    from loop_research.archive import read_json, write_json
    from loop_research.codex_backend import CallBudget, BudgetExceeded
    budgets = []
    def make_budget(*args):
        budget = CallBudget(*args)
        budgets.append(budget)
        return budget
    class Worker:
        def __init__(self, command, **kwargs):
            self.request = read_json(Path(command[-1]))
            write_json(Path(self.request['result_path']), {'text': json.dumps(output)})
        def wait(self, **kwargs):
            assert self.request['deadline'] == budgets[0].deadline
            budgets[0].deadline = 0
            return 0
    monkeypatch.setattr(agent, 'CallBudget', make_budget)
    monkeypatch.setattr(agent.subprocess, 'Popen', Worker)
    with pytest.raises(BudgetExceeded, match='deadline'):
        agent.run_task(task, benchmark, None, ctx)
    assert len(budgets) == 1
    assert not (ctx.path / 'output.json').exists()


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


def test_interrupted_task_terminates_worker_group(ctx, task, benchmark, monkeypatch):
    import signal
    from loop_research import agent
    waits, signals = [], []
    class Worker:
        pid = 123456
        def __init__(self, *args, **kwargs):
            assert kwargs['start_new_session'] is True
        def wait(self, **kwargs):
            waits.append(kwargs)
            if len(waits) == 1:
                raise KeyboardInterrupt()
            return -9
    monkeypatch.setattr(agent.subprocess, 'Popen', Worker)
    monkeypatch.setattr(agent.os, 'killpg', lambda pid, sig: signals.append((pid, sig)))
    with pytest.raises(KeyboardInterrupt):
        agent.run_task(task, benchmark, None, ctx)
    assert signals == [(123456, signal.SIGKILL)]
    assert len(waits) == 2 and waits[-1] == {}
    assert not (ctx.path / 'output.json').exists()
