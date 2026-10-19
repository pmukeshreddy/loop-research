"""Research can inspect its real call allowance without consuming or extending it."""
from concurrent.futures import ThreadPoolExecutor
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


def test_snapshot_reports_reservations_without_spending_or_raising_at_exhaustion():
    budget = CallBudget(2, 30)
    initial = budget.snapshot()
    assert initial == {'limit': 2, 'reserved': 0, 'remaining': 2}
    budget.reserve()
    budget.reserve()
    budget.deadline = 0
    assert budget.snapshot() == {'limit': 2, 'reserved': 2, 'remaining': 0}
    assert budget.snapshot() == {'limit': 2, 'reserved': 2, 'remaining': 0}
    initial['reserved'] = 99
    assert budget.count == 2
    with pytest.raises(BudgetExceeded):
        budget.reserve()


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
    assert budget.snapshot() == {'limit': 32, 'reserved': 32, 'remaining': 0}
    assert all(value['reserved'] + value['remaining'] == value['limit'] == 32 for value in snapshots)


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
            assert budget.snapshot() == {'limit': 4, 'reserved': 2, 'remaining': 2}
        finally:
            release.set()
        assert future.result(timeout=5) == 'fixture success'
    assert budget.snapshot() == {'limit': 4, 'reserved': 2, 'remaining': 2}


def test_budget_rpc_preserves_resumed_counts_without_calling_model(ctx, task):
    ctx.config.agent.max_codex_calls = 9
    for name, purpose in [('root', 'root'), ('sub', 'sub'), ('refine', 'refine'), ('grade', 'grade')]:
        ctx.save(f'codex_attempts/{name}.json', {'call_id': name, 'purpose': purpose})
    backend = Replies()
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=backend, resume=True)
    try:
        assert session.dispatch('budget', [], {}) == {'limit': 9, 'reserved': 2, 'remaining': 7}
        assert session.dispatch('budget', [], {}) == {'limit': 9, 'reserved': 2, 'remaining': 7}
    finally:
        session.refiner.close()
    assert backend.calls == []
    records = read_jsonl(ctx.path / 'trajectory.jsonl')
    assert [record['result'] for record in records] == [
        {'limit': 9, 'reserved': 2, 'remaining': 7}, {'limit': 9, 'reserved': 2, 'remaining': 7}]
    assert all(record['type'] == 'tool' and record['tool'] == 'budget' for record in records)


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
assert before == {"limit": 19, "reserved": 1, "remaining": 18}
assert llm_query("fixture extraction") == "fixture extracted value"
after = budget()
assert after == {"limit": 19, "reserved": 2, "remaining": 17}
assert budget() == after
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
    assert session.budget.snapshot() == {'limit': 19, 'reserved': 2, 'remaining': 17}
    records = read_jsonl(ctx.path / 'trajectory.jsonl')
    snapshots = [record['result'] for record in records if record.get('tool') == 'budget']
    assert snapshots == [{'limit': 19, 'reserved': 1, 'remaining': 18},
                         {'limit': 19, 'reserved': 2, 'remaining': 17},
                         {'limit': 19, 'reserved': 2, 'remaining': 17}]
