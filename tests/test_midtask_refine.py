"""Learning policy and the actual isolated mid-task refinement path."""
import json
import threading

import pytest

from loop_research.agent import run_task
from loop_research.archive import read_jsonl
from loop_research.trace import Trace
from test_refine import Planner, proposal
from test_worker import code_reply, final_code, session_factory
from test_agent_tools import install_fetch


def current_boundary(prompt):
    before, entries = prompt.rsplit('\nCURRENT RELEVANT HARNESS ENTRIES\n', 1)
    status = json.loads(before.rsplit('\nCURRENT REFINEMENT STATUS\n', 1)[1])
    return status, json.loads(entries)


@pytest.mark.parametrize('edit', [True, False])
def test_isolated_worker_uses_boundary_feedback_without_polling(ctx, task, benchmark, output, session_factory, edit):
    """The next useful root turn sees an unrelated lesson or an honest completed decline."""
    ctx.trace = Trace(ctx.run_dir)
    roots = 0
    content = 'Require verbatim quotation membership before citation emission.'
    def reply(prompt, options):
        nonlocal roots
        if options['purpose'] == 'sub':
            # Synchronize only the offline transport, never the worker's code or production scheduler.
            session.refiner.pending.result(timeout=5)
            return 'fixture-a fixture-value'
        assert options['purpose'] == 'root'
        roots += 1
        if roots == 1:
            return code_reply('request = refine.run(focus="Review collected provenance")\n'
                              'extracted = llm_query("Extract the collected evidence: fixture-a fixture-value")\n'
                              'print(extracted)')
        status, entries = current_boundary(prompt)
        assert status['state'] == 'applied' and status['fatal'] is None
        if edit:
            assert len(status['commits']) == 1
            learned, = [entry for entry in entries if entry['body'] == content]
            # The selected entry drives a later REPL action over the retained evidence.
            action = ('lesson = harness.get("memory", ' + repr(learned['id']) + ')\n'
                      'assert lesson["body"] == ' + repr(content) + '\n'
                      'assert "fixture-value" in extracted\n'
                      'print({"applied_procedure": lesson["id"], "quotation_validated": True})\n')
        else:
            assert status['proposal']['edits'] == [] and status['commits'] == []
            assert status['proposal']['decisions'] and all(
                decision['decision'] == 'declined' and decision['reason']
                for decision in status['proposal']['decisions'])
            assert entries == []
            action = 'print({"completed_decline": True})\n'
        return code_reply(action + final_code(output))
    session = session_factory(reply)
    session.learning = session.refiner.enabled = True
    response = proposal(title='Validate provenance', content=content) if edit else {
        'summary': 'The incomplete research snapshot does not establish a reusable lesson', 'edits': []}
    session.refiner.backend = Planner(response)
    # Trusted offline source evidence is independent of fetching transport and remains citation-checked.
    session.tools.evidence['fetched']['https://example.org/'] = 'fixture-a fixture-value'
    result = run_task(task, benchmark, session)
    assert result.output == output and result.uncited == [] and not result.repaired
    assert roots == 2 and len(session.refiner.backend.prompts) == 1
    events = read_jsonl(ctx.run_dir / 'trace.jsonl')
    applied = next(i for i, event in enumerate(events)
                   if event['component'] == 'Refine' and event['event'] == 'apply.end')
    retrieved = next(i for i, event in enumerate(events) if i > applied
                     and event['component'] == 'Harness' and event['event'] == 'retrieve.end')
    ended = next(i for i, event in enumerate(events)
                 if event['component'] == 'Worker' and event['event'] == 'run.end')
    assert applied < retrieved < ended
    if edit:
        assert events[retrieved]['details']['entries'][0]['title'] == 'Validate provenance'
    trajectory = read_jsonl(ctx.path / 'trajectory.jsonl')
    blocks = [block for row in trajectory if row['type'] == 'worker_iteration'
              for block in row['event']['code_blocks']]
    assert len(blocks) == 2
    assert ('quotation_validated' if edit else 'completed_decline') in blocks[-1]['result']['stdout']
    assert all('sleep' not in block['code'] and 'refine.status(' not in block['code'] for block in blocks)


def test_isolated_worker_does_not_schedule_without_agent_request(ctx, task, benchmark, output, session_factory):
    session = session_factory(lambda prompt, options: code_reply(final_code(output)))
    session.learning = session.refiner.enabled = True
    session.refiner.backend = Planner(proposal())
    run_task(task, benchmark, session)
    assert session.refiner.backend.prompts == [] and session.refiner.pending is None
    assert ctx.load('refine_state.json') is None


def test_isolated_worker_can_finish_while_refinement_is_still_planning(ctx, task, benchmark, output, session_factory):
    release = threading.Event()
    roots = 0
    def reply(prompt, options):
        nonlocal roots
        roots += 1
        if roots == 1:
            return code_reply('refine.run(focus="Review observed work")\nprint("research continues")')
        status, entries = current_boundary(prompt)
        assert status['state'] == 'planning' and status['proposal'] is None and entries == []
        return code_reply('assert refine.status()["state"] == "planning"\n' + final_code(output))
    session = session_factory(reply)
    session.learning = session.refiner.enabled = True
    planner = Planner({'summary': 'Insufficient evidence', 'edits': []})
    complete = planner.complete
    def gated(*args, **kwargs):
        assert release.wait(10)
        return complete(*args, **kwargs)
    planner.complete = gated
    session.refiner.backend = planner
    try:
        assert run_task(task, benchmark, session).output == output
        assert roots == 2 and not release.is_set()
        assert session.refiner.pending is not None and not session.refiner.pending.done()
        assert session.harness.list() == []
    finally:
        release.set()


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
