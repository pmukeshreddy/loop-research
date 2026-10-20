"""Research can inspect its call and time allowances without consuming or extending them."""
from concurrent.futures import CancelledError, ThreadPoolExecutor
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from loop_research.agent import run_task
from loop_research.archive import read_jsonl
from loop_research.codex_backend import BudgetExceeded, CallBudget, CodexBackend
from loop_research.harness import Harness
from loop_research.session import Session
from test_agent_tools import Replies
from test_worker import code_reply, final_code, session_factory


def assert_allowance(snapshot, limit, reserved, seconds_upper_bound):
    assert set(snapshot) == {'limit', 'reserved', 'remaining', 'seconds_remaining'}
    assert {key: snapshot[key] for key in ('limit', 'reserved', 'remaining')} == {
        'limit': limit, 'reserved': reserved, 'remaining': max(0, limit - reserved)}
    assert isinstance(snapshot['seconds_remaining'], float)
    assert 0 <= snapshot['seconds_remaining'] <= seconds_upper_bound


def test_snapshot_reports_reservations_without_spending_or_raising_at_exhaustion(monkeypatch):
    monkeypatch.setattr('loop_research.codex_backend.time.monotonic', lambda: 100.0)
    budget = CallBudget(2, 30)
    initial = budget.snapshot()
    assert initial == {'limit': 2, 'reserved': 0, 'remaining': 2, 'seconds_remaining': 30.0}
    budget.reserve()
    budget.reserve()
    budget.deadline = 0
    assert budget.snapshot() == {'limit': 2, 'reserved': 2, 'remaining': 0, 'seconds_remaining': 0.0}
    assert budget.snapshot() == {'limit': 2, 'reserved': 2, 'remaining': 0, 'seconds_remaining': 0.0}
    initial['reserved'] = 99
    initial['seconds_remaining'] = 999
    assert budget.count == 2
    assert budget.deadline == 0
    with pytest.raises(BudgetExceeded):
        budget.reserve()


def test_snapshot_uses_live_monotonic_deadline_without_extending_or_reserving(monkeypatch):
    now = [100.0]
    monkeypatch.setattr('loop_research.codex_backend.time.monotonic', lambda: now[0])
    budget = CallBudget(4, 30)
    budget.reserve()
    for current, expected in [(100.0, 30.0), (112.25, 17.75), (130.0, 0.0), (141.0, 0.0)]:
        now[0] = current
        assert budget.snapshot() == {
            'limit': 4, 'reserved': 1, 'remaining': 3, 'seconds_remaining': expected}
        assert budget.deadline == 130.0
        assert budget.count == 1
    with pytest.raises(BudgetExceeded, match='Task deadline exceeded'):
        budget.remaining()


def test_snapshot_is_consistent_with_concurrent_reservations():
    budget = CallBudget(32, 30)
    start = threading.Barrier(9)

    def reserve_four():
        start.wait(timeout=5)
        observed = []
        for _ in range(4):
            budget.reserve()
            observed.append(budget.snapshot())
        return observed

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(reserve_four) for _ in range(8)]
        start.wait(timeout=5)
        snapshots = [value for future in futures for value in future.result(timeout=5)]
    assert_allowance(budget.snapshot(), 32, 32, 30)
    assert all(value['reserved'] + value['remaining'] == value['limit'] == 32 for value in snapshots)
    assert all(0 < value['seconds_remaining'] <= 30 for value in snapshots)


def test_snapshot_counts_retried_and_inflight_backend_attempts(ctx):
    budget = CallBudget(4, 30)
    entered, release = threading.Event(), threading.Event()
    attempts = 0

    def runner(command, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return SimpleNamespace(returncode=1, stdout='', stderr='retryable fixture failure')
        entered.set()
        assert release.wait(5)
        Path(command[command.index('--output-last-message') + 1]).write_text('fixture success')
        return SimpleNamespace(returncode=0, stdout='', stderr='')

    backend = CodexBackend(ctx, budget=budget, runner=runner, sleep=lambda _: None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(backend.complete, 'fixture', purpose='sub')
        try:
            assert entered.wait(5)
            assert_allowance(budget.snapshot(), 4, 2, 30)
        finally:
            release.set()
        assert future.result(timeout=5) == 'fixture success'
    assert_allowance(budget.snapshot(), 4, 2, 30)


def test_budget_rpc_preserves_resumed_counts_without_calling_model(ctx, task):
    ctx.config.agent.max_codex_calls = 9
    for name, purpose in [('root', 'root'), ('sub', 'sub'), ('refine', 'refine'), ('grade', 'grade')]:
        ctx.save(f'codex_attempts/{name}.json', {'call_id': name, 'purpose': purpose})
    backend = Replies()
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=backend, resume=True)
    try:
        first = session.dispatch('budget', [], {})
        second = session.dispatch('budget', [], {})
        assert_allowance(first, 9, 2, ctx.config.agent.task_timeout_s)
        assert_allowance(second, 9, 2, first['seconds_remaining'])
    finally:
        session.refiner.close()
    assert backend.calls == []
    records = read_jsonl(ctx.path / 'trajectory.jsonl')
    assert [record['result'] for record in records] == [first, second]
    assert all(record['type'] == 'tool' and record['tool'] == 'budget' for record in records)


def test_cancelled_session_cannot_read_or_archive_a_budget_snapshot(ctx, task):
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=Replies())
    session.close_worker()
    try:
        with pytest.raises(CancelledError):
            session.dispatch('budget', [], {})
    finally:
        session.refiner.close()
    assert session.budget.count == 0
    assert not [row for row in read_jsonl(ctx.path / 'trajectory.jsonl') if row.get('tool') == 'budget']


@pytest.mark.parametrize('args,kwargs', [([1], {}), ([], {'limit': 999}), ([], {'reserve': 1})])
def test_budget_rpc_rejects_arguments_without_mutating_allowance(ctx, task, args, kwargs):
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=Replies())
    try:
        with pytest.raises(ValueError, match='budget.*arguments'):
            session.dispatch('budget', args, kwargs)
    finally:
        session.refiner.close()
    assert session.budget.count == 0
    assert session.budget.limit == ctx.config.agent.max_codex_calls


def test_real_worker_can_inspect_budget_and_both_inputs_expose_configured_limits(
        ctx, task, benchmark, output, session_factory):
    ctx.config.agent.max_codex_calls = 19
    ctx.config.agent.task_timeout_s = 45
    ctx.config.rlm.max_iterations = 5
    ctx.config.rlm.max_depth = 2
    ctx.config.codex.max_concurrent = 3
    limits = {'max_codex_calls': 19, 'task_timeout_s': 45.0,
              'max_iterations_per_rlm': 5, 'max_depth': 2, 'max_concurrent_codex_calls': 3}
    code = '''
import json
limits = json.loads(context.split("RESOURCE LIMITS\\n", 1)[1].splitlines()[0])
assert limits == ''' + repr(limits) + '''
before = budget()
assert {key: before[key] for key in ("limit", "reserved", "remaining")} == {"limit": 19, "reserved": 1, "remaining": 18}
assert 0 < before["seconds_remaining"] <= 45
assert llm_query("fixture extraction") == "fixture extracted value"
after = budget()
assert {key: after[key] for key in ("limit", "reserved", "remaining")} == {"limit": 19, "reserved": 2, "remaining": 17}
assert 0 < after["seconds_remaining"] <= before["seconds_remaining"]
again = budget()
assert {key: again[key] for key in ("limit", "reserved", "remaining")} == {"limit": 19, "reserved": 2, "remaining": 17}
assert 0 < again["seconds_remaining"] <= after["seconds_remaining"]
''' + final_code(output)

    def reply(prompt, options):
        if options['purpose'] == 'sub':
            return 'fixture extracted value'
        root_limits = json.loads(prompt.split('RESOURCE LIMITS\n', 1)[1].splitlines()[0])
        assert root_limits == limits
        return code_reply(code)

    session = session_factory(reply)
    result = run_task(task, benchmark, session)
    assert result.output == output
    assert_allowance(session.budget.snapshot(), 19, 2, 45)
    records = read_jsonl(ctx.path / 'trajectory.jsonl')
    snapshots = [record['result'] for record in records if record.get('tool') == 'budget']
    assert len(snapshots) == 3
    for snapshot, reserved in zip(snapshots, (1, 2, 2)):
        assert_allowance(snapshot, 19, reserved, 45)
    assert snapshots[0]['seconds_remaining'] >= snapshots[1]['seconds_remaining'] >= snapshots[2]['seconds_remaining'] > 0
