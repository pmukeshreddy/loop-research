"""Read-only lifecycle visibility; application remains an explicit boundary operation."""
import json
import threading

import pytest

from loop_research.harness import Harness
from loop_research.refine import Refiner
from loop_research.session import Session
from test_agent_tools import Replies
from test_refine import Planner, proposal


def make_refiner(ctx, response, *, enabled=True):
    return Refiner(Harness(ctx.root / 'harness'), ctx, Planner(response),
                   lambda: {'trajectory': [], 'self_check': {'issues': [{'type': 'empty_output'}]}},
                   enabled=enabled)


def test_status_observes_decline_without_applying_or_resuming(ctx):
    refiner = make_refiner(ctx, {'summary': 'Insufficient evidence for a reusable procedure', 'edits': []})
    try:
        assert refiner.status()['state'] == 'idle'
        receipt = refiner.run('Review observed work')
        refiner.pending.result(5)
        before = {p: p.read_bytes() for p in ctx.path.rglob('*.json')}
        head, future = refiner.harness.head, refiner.pending
        status = refiner.status()
        assert status['state'] == 'planned' and status['commits'] == []
        assert status['request_id'] == receipt['request_id'] and status['job_id'] == receipt['job_id']
        assert status['proposal']['decisions'][0]['decision'] == 'declined'
        assert status['proposal']['decisions'][0]['reason']
        assert refiner.status() == status
        assert refiner.pending is future and refiner.harness.head == head
        assert {p: p.read_bytes() for p in ctx.path.rglob('*.json')} == before
        assert len(refiner.backend.prompts) == 1
        assert refiner.boundary() == []
        assert refiner.status()['state'] == 'applied'
        assert refiner.status()['proposal'] == status['proposal']
        assert refiner.status()['commits'] == []
    finally:
        refiner.close()


def test_status_reports_only_committed_operations_and_survives_host_restart(ctx):
    refiner = make_refiner(ctx, proposal())
    try:
        refiner.run()
        job = refiner.pending.result(5)
        # A file staged/written before Git commit is not application evidence.
        path = refiner.harness.path / 'edits' / (job['operations'][0] + '.json')
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({'id': job['operations'][0], 'key': 'memory:uncommitted'}))
        assert refiner.status()['commits'] == []
        path.unlink()
        commits = refiner.boundary()
        status = refiner.status()
        assert status['state'] == 'applied'
        assert status['commits'] == [{'operation_id': job['operations'][0], 'commit': commits[0],
                                     'key': 'memory:' + job['operations'][0].removeprefix('refine_'),
                                     'action': 'create'}]
    finally:
        refiner.close()
    restarted = make_refiner(ctx, proposal(), enabled=False)
    try:
        assert restarted.status() == {**status, 'enabled': False}
        assert restarted.pending is None and restarted.backend.prompts == []
    finally:
        restarted.close()


def test_status_returns_while_background_planner_is_blocked(ctx):
    refiner = make_refiner(ctx, {'summary': 'No lesson', 'edits': []})
    started, release = threading.Event(), threading.Event()
    complete = refiner.backend.complete
    def gated(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return complete(*args, **kwargs)
    refiner.backend.complete = gated
    try:
        refiner.run()
        assert started.wait(5)
        assert refiner.status()['state'] == 'planning'
        assert refiner.boundary() == []
        assert not release.is_set() and refiner.harness.list() == []
    finally:
        release.set()
        refiner.close()


def test_status_exposes_failed_plan_without_consuming_failure(ctx, task):
    session = Session(task, ctx, Harness(ctx.root / 'harness'), backend=Replies())
    session.refiner.backend = Replies('invalid proposal')
    try:
        session.refiner.run()
        with pytest.raises(ValueError):
            session.refiner.pending.result(5)
        status = session.dispatch('refine.status', [], {})
        assert status['state'] == 'failed' and status['error'] and status['fatal'] is None
        with pytest.raises(RuntimeError, match='Refinement failed'):
            session.apply_refinement()
        assert session.dispatch('refine.status', [], {})['fatal'] == session.fatal
        assert session.backend.calls == []
    finally:
        session.refiner.close()


def test_status_argument_validation_and_no_learning_do_not_schedule(ctx, task):
    session = Session(task, ctx, Harness(ctx.root / 'harness'), learning=False, backend=Replies())
    try:
        status = session.dispatch('refine.status', [], {})
        assert status['state'] == 'idle' and status['enabled'] is False
        for args, kwargs in [(['x'], {}), ([], {'wait': True})]:
            with pytest.raises(ValueError, match='no arguments'):
                session.dispatch('refine.status', args, kwargs)
        assert session.refiner.pending is None and ctx.load('refine_state.json') is None
        assert session.backend.calls == []
    finally:
        session.refiner.close()


def test_retrieval_includes_full_committed_current_run_entries_without_query_overlap(ctx, task):
    harness = Harness(ctx.root / 'harness')
    session = Session(task, ctx, harness, backend=Replies())
    try:
        prior = harness.create('memory', 'Hand-written fixture', 'Prior relevant procedure', id='prior')
        unrelated = harness.create('memory', 'Retain provenance', 'Require verbatim quotation membership.', id='older')
        current = harness.create('skill', 'Validate provenance', 'Check exact quotation membership.', id='current',
                                 module='def check(quote, page):\n    return quote in page\n', evidence=[session.run_id])
        harness.record_usage([current], 'previous-observation')
        harness.record_outcome('previous-observation', {'ok': True, 'issues': [], 'signals': []})
        current = harness.get('skill', 'current')
        assert [entry['id'] for entry in harness.search(task.question + ' ' + json.dumps(task.spec))] == [prior['id']]
        entries = session.retrieve()
        assert {entry['id'] for entry in entries} == {'prior', 'current'}
        assert next(entry for entry in entries if entry['id'] == 'current') == current
        assert unrelated['id'] not in [entry['id'] for entry in entries]
        session.close_worker()
        assert harness.get('skill', 'current')['usage'][-1]['run_id'] == session.run_id
        harness.delete('skill', 'current', evidence=[session.run_id])
        assert [entry['id'] for entry in session.retrieve()] == ['prior']
    finally:
        session.refiner.close()


def test_status_keeps_planned_state_after_commit_before_save_failure(ctx, monkeypatch):
    refiner = make_refiner(ctx, proposal())
    save = ctx.save
    def interrupted(name, state):
        if name == 'refine_state.json' and state.get('status') == 'applied':
            raise OSError('interrupted after commit')
        return save(name, state)
    try:
        refiner.run()
        refiner.pending.result(5)
        monkeypatch.setattr(ctx, 'save', interrupted)
        with pytest.raises(OSError, match='interrupted after commit'):
            refiner.boundary()
        status = refiner.status()
        assert status['state'] == 'planned' and len(status['commits']) == 1
        assert status['commits'][0]['commit'] == refiner.harness.head
        assert refiner.pending is None and len(refiner.backend.prompts) == 1
        monkeypatch.setattr(ctx, 'save', save)
        assert refiner.resume()
        refiner.boundary(wait=True)
        assert refiner.status()['state'] == 'applied'
        assert refiner.status()['commits'] == status['commits']
        assert len(refiner.backend.prompts) == 1
    finally:
        refiner.close()


def test_status_keeps_discard_distinct_from_completed_decline(ctx):
    refiner = make_refiner(ctx, proposal())
    try:
        refiner.run()
        refiner.pending.result(5)
        refiner.harness.fork(refiner.harness.head)
        assert refiner.boundary() == []
        status = refiner.status()
        assert status['state'] == 'discarded' and status['commits'] == []
        assert status['proposal']['edits']
    finally:
        refiner.close()


def test_status_does_not_mask_corrupt_saved_state_or_invalid_operation_identity(ctx):
    refiner = make_refiner(ctx, proposal())
    try:
        refiner.run()
        job = refiner.pending.result(5)
        ctx.save('refine_state.json', {**job, 'operations': ['../unsafe']})
        with pytest.raises(ValueError, match='Invalid refinement identity'):
            refiner.status()
        (ctx.path / 'refine_state.json').write_text('{broken')
        with pytest.raises(json.JSONDecodeError):
            refiner.status()
    finally:
        refiner.close()
