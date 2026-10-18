import json
import threading

from loop_research.harness import Harness
from loop_research.refine import Refiner
from test_harness import commits


class Planner:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return json.dumps(self.response)


def proposal(action='create', kind='memory', id=None, title='Fetch failure', content='Retry unavailable official pages.'):
    return {'summary': 'Reuse evidence', 'edits': [{'action': action, 'kind': kind, 'id': id,
        'title': title, 'content': content, 'module': None}]}


def test_refine_one_commit_per_edit_and_rollback(ctx):
    h = Harness(ctx.root / 'harness')
    backend = Planner(proposal())
    refiner = Refiner(h, ctx, backend, lambda: {'trajectory': [], 'self_check': {'ok': False, 'issues': ['fetch']}})
    n = commits(h)
    refiner.run('repeated fetch failure')
    refiner.boundary(wait=True)
    assert commits(h) == n + 1
    entry = h.list()[0]
    assert entry['kind'] == 'memory' and entry['evidence'] == [ctx.run_id + '/' + ctx.task_id]
    refiner.rollback(h.head)
    assert h.list() == []
    refiner.close()


def test_planning_does_not_block_task_and_apply_waits_for_boundary(ctx):
    h = Harness(ctx.root / 'harness')
    started, release = threading.Event(), threading.Event()
    class Background(Planner):
        def complete(self, *args, **kwargs):
            started.set()
            assert release.wait(5)
            return super().complete(*args, **kwargs)
    refiner = Refiner(h, ctx, Background(proposal()), lambda: {'trajectory': [], 'self_check': {}})
    refiner.run()
    assert started.wait(5)
    assert refiner.boundary() == [] and h.list() == []
    release.set()
    refiner.pending.result(5)
    assert h.list() == []
    assert refiner.boundary() and len(h.list()) == 1
    refiner.close()


def test_refiner_receives_only_research_and_selfcheck_not_grade(ctx):
    h = Harness(ctx.root / 'harness')
    ctx.save('grade.json', {'SECRET_GRADE': 0.99})
    backend = Planner({'summary': 'No reusable lesson', 'edits': []})
    refiner = Refiner(h, ctx, backend, lambda: {'trajectory': ['actual research'], 'self_check': {'ok': True}})
    refiner.run(); refiner.boundary(wait=True); refiner.close()
    assert 'SECRET_GRADE' not in backend.prompts[0]
    assert 'actual research' in backend.prompts[0]
    assert h.list() == []


def test_stale_plan_replans_instead_of_overwriting_newer_edit(ctx):
    h = Harness(ctx.root / 'harness')
    entry = h.create('memory', 'Fetch failure', 'old')
    backend = Planner(proposal('update', id=entry['id']))
    refiner = Refiner(h, ctx, backend, lambda: {'trajectory': [], 'self_check': {}})
    refiner.run(); refiner.pending.result(5)
    h.update('memory', entry['id'], 'Fetch failure', 'concurrent')
    assert refiner.boundary() == []
    assert h.get('memory', entry['id'])['body'] == 'concurrent'
    refiner.boundary(wait=True)
    assert len(backend.prompts) == 2
    refiner.close()


def test_pending_plan_cannot_cross_a_lineage_fork(ctx):
    h = Harness(ctx.root / 'harness'); base = h.head
    refiner = Refiner(h, ctx, Planner(proposal()), lambda: {'trajectory': ['task research'], 'self_check': {}})
    refiner.run(); refiner.pending.result(5)
    h.fork(base)
    assert refiner.boundary() == []
    assert h.list() == [] and refiner.pending is None
    refiner.close()


def test_no_learning_never_calls_planner_or_allows_rollback(ctx):
    import pytest
    h = Harness(ctx.root / 'harness'); backend = Planner(proposal())
    refiner = Refiner(h, ctx, backend, lambda: {'trajectory': [], 'self_check': {}}, enabled=False)
    assert refiner.run()['scheduled'] is False
    assert refiner.boundary(wait=True) == [] and backend.prompts == []
    with pytest.raises(ValueError, match='disabled'):
        refiner.rollback('anything')
    refiner.close()


def test_invalid_second_edit_is_rejected_before_any_commit(ctx):
    import pytest
    from pydantic import ValidationError
    h = Harness(ctx.root / 'harness'); response = proposal()
    response['edits'].append({**response['edits'][0], 'title': None})
    refiner = Refiner(h, ctx, Planner(response), lambda: {'trajectory': [], 'self_check': {}})
    n = commits(h); refiner.run()
    with pytest.raises(ValidationError):
        refiner.boundary(wait=True)
    assert h.list() == [] and commits(h) == n
    refiner.close()
