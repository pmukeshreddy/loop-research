from loop_research.harness import Harness
from loop_research.session import Session
from test_agent_tools import Replies
from test_refine import Planner, proposal


def test_failed_background_plan_stops_task_and_finish_until_explicit_resume(ctx, task):
    import pytest
    h = Harness(ctx.root / 'harness')
    session = Session(task, ctx, h, backend=Replies('next turn'))
    session.refiner.backend = Replies('not json')
    session.refiner.run()
    try:
        session.refiner.pending.result(5)
    except ValueError:
        pass
    with pytest.raises(RuntimeError, match='Refinement failed'):
        session.dispatch('complete', ['continue'], {'purpose': 'root'})
    with pytest.raises(RuntimeError, match='Refinement failed'):
        session.finish()
    assert session.backend.calls == [] and h.list() == []
    session.refiner.close()
    resumed = Session(task, ctx, h, backend=Replies(), resume=True)
    resumed.refiner.backend = Planner({'summary': 'No edit', 'edits': []})
    resumed.finish()
    assert len(resumed.refiner.backend.prompts) == 2


def test_consistently_bad_outcomes_are_available_to_refine_for_deletion(ctx, task):
    h = Harness(ctx.root / 'harness')
    e = h.create('memory', 'Failure', 'bad tactic')
    for i in range(3):
        h.record_usage([e], f'prior-{i}')
        h.record_outcome(f'prior-{i}', {'ok': False, 'issues': ['fabricated_quote']})
    session = Session(task, ctx, h, backend=Replies())
    planner = Planner(proposal('delete', id=e['id'], title=None, content=None))
    session.refiner.backend = planner
    session.finish()
    assert h.list() == []
    assert planner.prompts[0].count('fabricated_quote') >= 3


def test_completed_fetch_event_required_and_reports_prose_only_failure(ctx):
    from loop_research.repl_tools import ResearchTools
    # A custom transport with no tool evidence cannot make prose count as a fetch.
    class NoFetch:
        last_web_actions = []
        def complete(self, *args, **kwargs):
            return 'claimed page'
    tools = ResearchTools(NoFetch(), ctx)
    assert tools.fetch('https://example.org/') == 'FETCH_FAILED'
    assert tools.snapshot()['fetched'] == {}
    assert tools.snapshot()['failures'] == [{'operation': 'fetch', 'url': 'https://example.org/',
                                            'request_id': 1, 'source': 'backend', 'reason': 'fetch_failed'}]


def test_rollback_requested_in_final_cell_applies_at_task_end(ctx, task):
    h = Harness(ctx.root / 'harness'); h.create('memory', 'Failure', 'bad lesson')
    commit = h.head
    session = Session(task, ctx, h, backend=Replies())
    session.refiner.backend = Planner({'summary': 'No changes', 'edits': []})
    assert session.dispatch('refine.rollback', [commit], {}) == {'scheduled': True}
    session.finish()
    assert h.list() == []


def test_shutdown_prevents_delayed_tools_and_new_dispatch_from_mutating_state(ctx, task):
    from concurrent.futures import CancelledError, ThreadPoolExecutor
    import threading
    import pytest
    entered, release = threading.Event(), threading.Event()
    class Delayed:
        last_web_actions = [{'type': 'open_page', 'url': 'https://example.org/'}]
        def complete(self, *args, **kwargs):
            entered.set()
            assert release.wait(5)
            return 'late evidence'
    h = Harness(ctx.root / 'harness')
    session = Session(task, ctx, h, backend=Delayed())
    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(session.dispatch, 'tools.fetch', ['https://example.org/'], {})
        assert entered.wait(5)
        try:
            session.close_worker()
        finally:
            release.set()
        with pytest.raises(CancelledError):
            request.result(5)
    evidence = session.tools.snapshot()
    assert {k: evidence[k] for k in ('fetched', 'checks', 'searches', 'discoveries', 'dropped_search_hits')} == {
        'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'dropped_search_hits': []}
    assert len(evidence['fetches']) == len(evidence['failures']) == 1
    assert evidence['fetches'][0]['status'] == 'cancelled'
    assert evidence['failures'][0]['reason'] == 'cancelled'
    assert ctx.load('evidence.json') == evidence
    assert session.tools.cache == {} and session.tools.ledger == set()
    with pytest.raises(CancelledError):
        session.dispatch('harness.create', ['memory', 'Late', 'must not persist'], {})
    assert h.list() == []
    session.refiner.close()


def test_invalid_rollback_cannot_poison_next_turn(ctx, task):
    import pytest
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=Replies('next turn'))
    for value in (None, 1, [], {}, ''):
        with pytest.raises(ValueError):
            session.dispatch('refine.rollback', [value], {})
    assert session.dispatch('complete', ['continue'], {'purpose': 'root'})['text'] == 'next turn'
    session.refiner.close()


def test_rollback_failure_is_fatal_and_remains_pending(ctx, task):
    import pytest
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=Replies())
    session.refiner.backend = Planner({'summary': 'No edits', 'edits': []})
    session.dispatch('refine.rollback', ['unknown'], {})
    with pytest.raises(RuntimeError, match='Rollback failed'):
        session.finish()
    assert session.rollbacks[0]['id'] == 'unknown'
    assert ctx.load('session_state.json')['rollbacks'][0]['id'] == 'unknown'
    session.refiner.close()


def test_direct_delete_of_missing_entry_is_audited(ctx, task):
    from loop_research.archive import read_jsonl
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=Replies())
    assert session.dispatch('harness.delete', ['memory', 'absent'], {}) is False
    assert read_jsonl(ctx.path / 'refinements.jsonl')[-1]['reason'] == 'entry_missing'
    session.refiner.close()


def test_worker_model_override_must_match_role_and_trajectory_records_model(ctx, task):
    import pytest
    from loop_research.archive import read_jsonl
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=Replies('response'))
    with pytest.raises(ValueError, match='configured model'):
        session.dispatch('complete', ['prompt'], {'purpose': 'sub', 'model': 'different-model'})
    session.dispatch('complete', ['prompt'], {'purpose': 'sub', 'model': ctx.config.models.sub})
    assert read_jsonl(ctx.path / 'trajectory.jsonl')[-1]['model'] == ctx.config.models.sub
    session.refiner.close()
