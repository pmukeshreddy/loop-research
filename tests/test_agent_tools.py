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
