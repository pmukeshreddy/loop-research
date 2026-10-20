"""Offline checks of independent runs at the actual researcher boundary."""
import json
import re
from datetime import date

import pytest

from loop_research import agent, session as session_module, stream
from loop_research.agent import run_task
from loop_research.archive import RunContext, read_jsonl
from loop_research.harness import Harness
from loop_research.research import ResearchData
from loop_research.session import Session
from test_agent_tools import Replies
from test_worker import OfflineBackend, code_reply, final_code


def entry_sections(prompt):
    sections = []
    for match in reversed(list(re.finditer(r'(?m)^(?:CURRENT )?RELEVANT HARNESS(?: ENTRIES)?\n', prompt))):
        entries, length = json.JSONDecoder().raw_decode(prompt[match.end():])
        sections.insert(0, entries)
        prompt = prompt[:match.end()] + '<entries>' + prompt[match.end() + length:]
    return prompt, sections


def test_repeated_researcher_reads_keep_complete_prior_metadata_until_worker_closes(ctx, task):
    harness = Harness(ctx.root / 'harness')
    entry = harness.create('memory', 'Hand-written fixture', 'Check all fixture evidence.', id='existing')
    harness.record_usage([entry], 'earlier/task')
    harness.record_outcome('earlier/task', {'ok': False, 'issues': [{'type': 'missing_evidence'}]})
    prior = harness.get('memory', entry['id'])
    session = Session(task, ctx, harness, learning=False, backend=Replies('done'))
    try:
        assert session.retrieve() == [prior]
        for method, args, expected in (
            ('get', ['memory', 'existing'], prior),
            ('read', ['memory', 'existing'], prior),
            ('list', [], [prior]),
            ('search', ['fixture'], [prior]),
        ):
            assert session.dispatch('harness.' + method, args, {}) == expected
        assert session.retrieve() == [prior]
        assert harness.get('memory', 'existing') == prior
        pending = ctx.load('harness_usage.json')
        assert pending == [{'kind': 'memory', 'id': 'existing', 'version': 1,
                            'refinement_id': entry['refinement_id']}]
        session.close_worker()
        actual = harness.get('memory', 'existing')
        assert actual['usage'] == prior['usage'] + [{'run_id': session.run_id, 'version': 1,
                                                    'refinement_id': entry['refinement_id']}]
        assert actual['outcomes'] == prior['outcomes']
    finally:
        session.close_worker()
        session.refiner.close()


def test_pending_usage_survives_session_recreation_and_finish_is_idempotent(ctx, task):
    harness = Harness(ctx.root / 'harness')
    entry = harness.create('memory', 'Hand-written fixture', 'Inspect fixture facts.')
    session = Session(task, ctx, harness, learning=False, backend=Replies())
    session.retrieve()
    session.refiner.close()  # Simulate loss of the research session before worker shutdown.
    assert harness.get('memory', entry['id'])['usage'] == []
    resumed = Session(task, ctx, harness, learning=False, backend=Replies(), resume=True)
    try:
        resumed.finish()
        completed = harness.snapshot()
        resumed.finish()
        assert harness.snapshot() == completed
        actual = harness.get('memory', entry['id'])
        assert actual['usage'] == [{'run_id': resumed.run_id, 'version': 1,
                                    'refinement_id': entry['refinement_id']}]
        assert len(actual['outcomes']) == 1
        assert actual['outcomes'][0]['run_id'] == resumed.run_id
    finally:
        resumed.refiner.close()


def test_usage_journal_write_failure_can_be_retried_without_losing_the_read(ctx, task, monkeypatch):
    harness = Harness(ctx.root / 'harness')
    entry = harness.create('memory', 'Hand-written fixture', 'Inspect fixture facts.')
    session = Session(task, ctx, harness, learning=False, backend=Replies())
    save = ctx.save

    def unavailable(name, value):
        if name == 'harness_usage.json':
            raise OSError('archive unavailable')
        return save(name, value)

    try:
        monkeypatch.setattr(ctx, 'save', unavailable)
        with pytest.raises(OSError, match='archive unavailable'):
            session.retrieve()
        monkeypatch.setattr(ctx, 'save', save)
        assert session.retrieve() == [entry]
        assert ctx.load('harness_usage.json') == [{'kind': 'memory', 'id': entry['id'], 'version': 1,
                                                  'refinement_id': entry['refinement_id']}]
    finally:
        session.close_worker()
        session.refiner.close()


@pytest.mark.parametrize('different_entries', [False, True])
def test_explicit_base_runs_change_only_complete_entries_in_actual_worker_inputs(
        tmp_path, config, monkeypatch, different_entries):
    config.agent.as_of = '2024-02-29'
    config.models.root, config.models.sub = 'offline-root', 'offline-sub'
    config.rlm.max_iterations = 1
    harness = Harness(tmp_path / 'harness')
    existing = harness.create('memory', 'Fixture evidence', 'Inspect fixture sources.', id='existing')
    harness.record_usage([existing], 'earlier/task')
    harness.record_outcome('earlier/task', {'ok': True, 'issues': []})
    base = harness.head
    original = harness.list()
    backends = []

    def backend(ctx, *, budget=None):
        def reply(prompt, options):
            original_context = (ctx.path / 'prompt.txt').read_text()
            return code_reply('assert context == ' + repr(original_context) + '\n' + final_code({'rows': []}))
        result = OfflineBackend(reply)
        result.budget = budget
        backends.append(result)
        return result

    monkeypatch.setattr(session_module, 'CodexBackend', backend)
    first = stream.research(tmp_path, config, 'Fixture evidence', ['entity'], ['entity'], 'en',
                            base=base, no_learning=True, trace=True)
    if different_entries:
        harness.create('skill', 'Fixture evidence procedure', 'Cross-check fixture evidence. ' * 50,
                       id='learned', evidence=['earlier/task'])
    second_base = harness.head
    second_entries = harness.list()
    second = stream.research(tmp_path, config, 'Fixture evidence', ['entity'], ['entity'], 'en',
                             base=second_base, no_learning=True, trace=True)
    roots = [prompt for b in backends for prompt, options in b.calls if options['purpose'] == 'root']
    assert len(roots) == 2
    normalized = [entry_sections(prompt) for prompt in roots]
    assert normalized[0][0] == normalized[1][0]
    for result, initial, expected in zip((first, second), normalized, (original, second_entries)):
        assert len(initial[1]) == 2
        expected_by_id = {entry['id']: entry for entry in expected}
        for section in initial[1]:
            assert {entry['id']: entry for entry in section} == expected_by_id
        ctx = RunContext(tmp_path, result['run_id'], config, result['task_id'])
        prompt = (ctx.path / 'prompt.txt').read_text()
        assert entry_sections(prompt)[0] == entry_sections((ctx.path / 'root_prompt.txt').read_text())[0]
        assert ctx.load('as_of.json') == {'policy': '2024-02-29', 'task_date': None,
                                         'as_of_date': '2024-02-29', 'date_source': 'config'}
        assert ctx.load('prompt_metadata.json') == {'context_type': 'str', 'context_total_length': len(prompt)}
        assert result['run_id'] not in roots[(first, second).index(result)]
        finished = json.loads(harness.git('show', result['harness_after'] + ':harness_state.json'))
        for entry in finished['entries'].values():
            assert any(use['run_id'] == result['run_id'] + '/' + result['task_id'] for use in entry['usage'])
        events = read_jsonl(ctx.run_dir / 'trace.jsonl')
        assert any(event['component'] == 'RLM' and event['event'] == 'context_metadata'
                   and event['details']['context_total_length'] == len(prompt) for event in events)
    if not different_entries:
        assert roots[0] == roots[1]


@pytest.mark.parametrize('policy,task_date,source', [
    ('today', None, 'today'),
    ('2024-02-29', None, 'config'),
    ('today', date(2020, 1, 2), 'task'),
])
def test_independent_date_archives_keep_equal_true_provenance(tmp_path, config, task, monkeypatch,
                                                            policy, task_date, source):
    class Today(date):
        @classmethod
        def today(cls):
            return cls(2024, 2, 29)
    monkeypatch.setattr(agent, 'date', Today)
    task.as_of_date = task_date
    config.agent.as_of = policy
    config.models.root, config.models.sub = 'offline-root', 'offline-sub'
    harness = Harness(tmp_path / 'harness')
    base = harness.head
    roots, dates = [], []
    for name in ('first', 'second'):
        harness.fork(base)
        ctx = RunContext(tmp_path, name, config, task.task_id)
        backend = OfflineBackend(lambda prompt, options: code_reply(final_code({'rows': []})))
        session = Session(task, ctx, harness, learning=False, backend=backend)
        backend.budget = session.budget
        try:
            result = run_task(task, ResearchData(), session)
            assert result.date_source == source
            roots.append(next(prompt for prompt, opts in backend.calls if opts['purpose'] == 'root'))
            dates.append(ctx.load('as_of.json'))
        finally:
            session.close_worker()
            session.refiner.close()
    assert roots[0] == roots[1]
    assert dates[0] == dates[1]
    assert dates[0]['date_source'] == source
    assert dates[0]['task_date'] == (task_date.isoformat() if task_date else None)
