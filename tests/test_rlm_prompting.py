"""Research orchestration keeps evidence in Python without censoring stdout."""
import json

from loop_research.agent import run_task
from loop_research.archive import read_jsonl
from loop_research.rlm_codex_client import CodexRLM
from test_worker import code_reply, final_code, session_factory
from test_agent_tools import install_fetch


def test_root_preserves_full_contract_procedure_and_outcome_history(
        ctx, task, benchmark, output, session_factory):
    session = session_factory(lambda prompt, options: code_reply(final_code(output)))
    entry = session.harness.create('memory', 'Hand-written fixture procedure',
                                   'Inspect fixture evidence before choosing a value.')
    session.harness.record_usage([entry], 'earlier-run')
    session.harness.record_outcome('earlier-run', {'ok': False, 'issues': ['OUTCOME_ONLY_MARKER']})
    result = run_task(task, benchmark, session)
    root_prompt = session.backend.calls[0][0]
    assert task.question in root_prompt
    assert 'Inspect fixture evidence before choosing a value.' in root_prompt
    assert 'OUTCOME_ONLY_MARKER' in root_prompt
    assert 'earlier-run' in root_prompt
    assert 'OUTPUT CONTRACT\n' in root_prompt
    assert 'CONSTRAINT IDS\n' in root_prompt
    assert (ctx.path / 'prompt.txt').read_text() in root_prompt
    assert (ctx.path / 'root_prompt.txt').read_text() == (ctx.path / 'prompt.txt').read_text()
    assert 'OUTCOME_ONLY_MARKER' in json.dumps(session.harness.snapshot())
    assert result.output == output


def test_retrieval_preserves_every_field_for_the_researcher(session_factory):
    session = session_factory(lambda *args: None)
    entry = session.harness.create('memory', 'Hand-written fixture procedure',
                                   'Inspect fixture evidence before choosing a value.')
    session.harness.record_usage([entry], 'earlier-run')
    session.harness.record_outcome('earlier-run', {'ok': False, 'issues': ['OUTCOME_ONLY_MARKER']})
    query = session.task.question + ' ' + json.dumps(session.task.spec, ensure_ascii=False)
    expected = session.harness.search(query, limit=session.ctx.config.harness.retrieval_limit)
    assert session.retrieve() == expected


def test_research_orchestrator_does_not_require_printing_candidate_answer():
    rlm = CodexRLM(None, root_model='fixture-root', sub_model='fixture-sub')
    system = rlm._setup_prompt('fixture context', root_prompt='fixture question')[0]['content']
    assert 'only flip' not in system
    assert 'printed the candidate answer' not in system
    assert 'Keep fetched text' in system
    assert 'programmatic' in system


def test_full_pages_reach_submodel_and_persist_without_being_printed_to_root(
        ctx, task, benchmark, output, session_factory, monkeypatch):
    page = ('fixture-a fixture-value\n' + ''.join(f'Evidence record {i}: unique payload.\n' for i in range(2000))).rstrip()
    downloads = install_fetch(monkeypatch, page)
    root_calls = 0
    def reply(prompt, options):
        nonlocal root_calls
        if options['purpose'] == 'sub':
            assert page in prompt
            return 'fixture-value'
        root_calls += 1
        if root_calls == 1:
            return code_reply('page = fetch("https://example.org/")\n'
                              'extracted = llm_query("Extract the value from this evidence:\\n" + page)\n'
                              'print({"page_chars": len(page), "value": extracted})')
        assert page[:100] not in prompt
        assert len(prompt) < len(page)
        return code_reply('assert "fixture-a" in page\n' + final_code(output))
    session = session_factory(reply)
    assert run_task(task, benchmark, session).output == output
    assert root_calls == 2 and downloads == ['https://example.org/']
    assert session.tools.snapshot()['fetched']['https://example.org/'] == [page]
    records = read_jsonl(ctx.path / 'trajectory.jsonl')
    assert any(x['type'] == 'model' and x['purpose'] == 'sub' and page in x['prompt'] for x in records)


def test_printed_page_is_visible_and_only_upstream_per_block_truncation_applies(
        ctx, task, benchmark, output, session_factory, monkeypatch):
    page = 'VISIBLE_PAGE_START\n' + 'evidence content\n' * 2000 + 'VISIBLE_PAGE_END'
    downloads = install_fetch(monkeypatch, page)
    roots = 0
    def reply(prompt, options):
        nonlocal roots
        roots += 1
        if roots == 1:
            return code_reply('page = fetch("https://example.org/")\nprint(page)')
        assert page[:1000] in prompt
        assert 'VISIBLE_PAGE_END' not in prompt
        assert 'chars...]' in prompt
        return code_reply(final_code(output))
    session = session_factory(reply)
    assert run_task(task, benchmark, session).output == output
    assert downloads == ['https://example.org/']
    iteration = next(x['event'] for x in read_jsonl(ctx.path / 'trajectory.jsonl') if x['type']=='worker_iteration')
    assert iteration['code_blocks'][0]['result']['stdout'] == page + '\n'
