from loop_research.harness import Harness
from loop_research.session import Session
from test_agent_tools import Replies
from test_refine import Planner, proposal


def test_failed_background_plan_does_not_abort_task_or_suppress_automatic_refine(ctx, task):
    h = Harness(ctx.root / 'harness')
    session = Session(task, ctx, h, backend=Replies('next turn'))
    session.refiner.backend = Replies('not json')
    session.refiner.run()
    try:
        session.refiner.pending.result(5)
    except ValueError:
        pass
    response = session.dispatch('complete', ['continue'], {'purpose': 'root'})
    assert response['text'] == 'next turn'
    planner = Planner(proposal())
    session.refiner.backend = planner
    session.finish()
    assert len(planner.prompts) == 1 and len(h.list()) == 1


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
    assert tools.snapshot()['failures'] == [{'operation': 'fetch', 'url': 'https://example.org/'}]


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
    assert session.tools.snapshot() == {'fetched': {}, 'checks': [], 'searches': [], 'discoveries': [], 'failures': []}
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
