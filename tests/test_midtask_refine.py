"""Learning policy and the actual isolated mid-task refinement path."""
import pytest

from loop_research.agent import run_task
from loop_research.archive import read_jsonl
from loop_research.trace import Trace
from test_refine import Planner, proposal
from test_worker import code_reply, final_code, session_factory
from test_agent_tools import install_fetch


@pytest.mark.parametrize('learning', [True, False])
def test_root_and_context_describe_learning_policy(task, benchmark, output, ctx, session_factory, learning):
    session = session_factory(lambda prompt, options: code_reply(final_code(output)))
    session.learning = session.refiner.enabled = learning
    run_task(task, benchmark, session)
    context = (ctx.path / 'prompt.txt').read_text()
    root = session.backend.calls[0][0]
    expected = 'LEARNING ENABLED' if learning else 'LEARNING DISABLED'
    assert expected in context and expected in root
    if learning:
        assert 'repeated tool failure' in root and 'refine.run(focus=' in root
        assert 'Do not repeat a pending request' in root
    else:
        assert 'Do not request refinement or edit the harness' in root


def test_midtask_refine_commits_and_is_retrieved_on_later_root_turn(ctx, task, benchmark, output, session_factory, monkeypatch):
    install_fetch(monkeypatch, lambda url: 'fixture-a fixture-value')
    ctx.trace = Trace(ctx.run_dir)
    roots = 0
    def reply(prompt, options):
        nonlocal roots
        if options['purpose'] == 'sub':
            session.refiner.pending.result(timeout=5)
            return 'fixture extraction complete'
        roots += 1
        if roots == 1:
            return code_reply('page = fetch("https://example.org/")\n'
                              'assert refine.run(focus="Review the observed fixture extraction")["scheduled"]\n'
                              'extracted = llm_query(page)\nprint(extracted)')
        assert 'MIDTASK_FIXTURE_PROCEDURE' in prompt
        return code_reply(final_code(output))
    session = session_factory(reply)
    session.learning = session.refiner.enabled = True
    session.refiner.backend = Planner(proposal(title='Hand-written fixture extraction', content='MIDTASK_FIXTURE_PROCEDURE'))
    assert run_task(task, benchmark, session).output == output
    events = read_jsonl(ctx.run_dir / 'trace.jsonl')
    applied = next(i for i, event in enumerate(events) if event['component'] == 'Refine' and event['event'] == 'apply.end')
    commit = events[applied]['details']['commits'][0]
    assert len(commit) == 40
    retrieval = next(i for i, event in enumerate(events) if i > applied and event['component'] == 'Harness' and event['event'] == 'retrieve.end')
    assert events[retrieval]['details']['entries'][0]['title'] == 'Hand-written fixture extraction'
    ended = next(i for i, event in enumerate(events) if event['component'] == 'Worker' and event['event'] == 'run.end')
    assert applied < retrieval < ended
