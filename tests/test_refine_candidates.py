"""Planner accounting is validated before any durable harness mutation."""
import copy
import json

import pytest

from loop_research.archive import read_jsonl
from loop_research.harness import Harness
from loop_research.refine import INSTRUCTIONS, Refiner, candidate_inventory
from loop_research.trace import Trace
from test_refine import Planner, proposal


class RawPlanner:
    def __init__(self, response):
        self.response = response
        self.prompts = []
        self.schemas = []

    def complete(self, prompt, **kwargs):
        self.prompts.append(json.loads(prompt.removeprefix(INSTRUCTIONS)))
        self.schemas.append(kwargs['schema'])
        return json.dumps(self.response)


def observed():
    return {'trajectory': [], 'self_check': {'ok': True, 'issues': [], 'signals': [
        {'type': 'stalled_search', 'query': 'already verified entity'},
        {'type': 'failed_fetch', 'url': 'https://example.org/page', 'reason': 'fetch_failed'},
        {'type': 'failed_fetch', 'url': 'https://example.net/other', 'reason': 'fetch_failed'},
    ]}}


def decision(candidate_id, ref, *, accepted=False, reason='The recorded attempt recovered without a reusable procedure.'):
    return {'candidate_id': candidate_id, 'decision': 'accepted' if accepted else 'declined',
            'reason': reason, 'evidence_refs': [ref], 'edit_indexes': [0] if accepted else []}


def accounted_response():
    return {'summary': 'No reusable change established', 'edits': [], 'additional_candidates': [], 'decisions': [
        decision('self_check:signals:stalled_search', '/self_check/signals/0'),
        decision('self_check:signals:failed_fetch', '/self_check/signals/1'),
    ]}


def test_repeated_signal_families_are_presented_with_every_evidence_reference(ctx):
    h = Harness(ctx.root / 'harness')
    observation = observed()
    backend = RawPlanner(accounted_response())
    refiner = Refiner(h, ctx, backend, lambda: observation)
    try:
        refiner.run()
        refiner.boundary(wait=True)
    finally:
        refiner.close()
    payload = backend.prompts[0]
    assert payload['candidate_inventory'] == [
        {'id': 'self_check:signals:stalled_search', 'source': 'self_check.signals',
         'type': 'stalled_search', 'count': 1, 'evidence_refs': ['/self_check/signals/0']},
        {'id': 'self_check:signals:failed_fetch', 'source': 'self_check.signals',
         'type': 'failed_fetch', 'count': 2,
         'evidence_refs': ['/self_check/signals/1', '/self_check/signals/2']},
    ]
    assert payload['self_check'] == observation['self_check']
    state = ctx.load('refine_state.json')
    assert state['candidate_inventory'] == payload['candidate_inventory']
    assert state['proposal']['decisions'] == accounted_response()['decisions']
    assert state['observed'] == observation and state['status'] == 'applied'
    assert h.list() == []


def test_missing_accounting_is_rejected_even_with_no_edits(ctx):
    h = Harness(ctx.root / 'harness')
    refiner = Refiner(h, ctx, RawPlanner({'summary': 'Ignored signals', 'edits': []}), observed)
    try:
        refiner.run()
        with pytest.raises(ValueError, match='decisions'):
            refiner.boundary(wait=True)
    finally:
        refiner.close()
    assert ctx.load('refine_state.json')['status'] == 'failed'
    assert h.list() == []


@pytest.mark.parametrize('mutation, error', [
    ('omit_candidate', 'exactly once'),
    ('duplicate_decision', 'exactly once'),
    ('unknown_candidate', 'exactly once'),
    ('blank_reason', 'reason'),
    ('missing_evidence', 'evidence_refs'),
    ('unknown_evidence', 'evidence reference'),
    ('other_candidate_evidence', 'candidate evidence'),
    ('declined_edit', 'Declined'),
    ('accepted_without_edit', 'Accepted'),
    ('unaccounted_edit', 'Every edit'),
    ('invalid_edit_index', 'edit index'),
    ('additional_without_decision', 'exactly once'),
    ('additional_duplicate_id', 'unique'),
    ('additional_unknown_evidence', 'evidence reference'),
    ('boolean_edit_index', 'edit_indexes'),
])
def test_invalid_accounting_cannot_apply_any_edits(ctx, mutation, error):
    response = accounted_response()
    if mutation == 'omit_candidate':
        response['decisions'].pop()
    elif mutation == 'duplicate_decision':
        response['decisions'].append(copy.deepcopy(response['decisions'][0]))
    elif mutation == 'unknown_candidate':
        response['decisions'][0]['candidate_id'] = 'imaginary'
    elif mutation == 'blank_reason':
        response['decisions'][0]['reason'] = ' \n '
    elif mutation == 'missing_evidence':
        response['decisions'][0]['evidence_refs'] = []
    elif mutation == 'unknown_evidence':
        response['decisions'][0]['evidence_refs'] = ['/self_check/signals/99']
    elif mutation == 'other_candidate_evidence':
        response['decisions'][0]['evidence_refs'] = ['/self_check/signals/1']
    elif mutation == 'declined_edit':
        response['edits'] = proposal()['edits']
        response['decisions'][0]['edit_indexes'] = [0]
    elif mutation == 'accepted_without_edit':
        response['decisions'][0]['decision'] = 'accepted'
    elif mutation == 'unaccounted_edit':
        response['edits'] = proposal()['edits']
    elif mutation == 'invalid_edit_index':
        response['edits'] = proposal()['edits']
        response['decisions'][0].update(decision='accepted', edit_indexes=[1])
    elif mutation == 'additional_without_decision':
        response['additional_candidates'] = [{'id': 'new', 'description': 'A further candidate',
                                             'evidence_refs': ['/self_check/signals/1']}]
    elif mutation == 'additional_duplicate_id':
        response['additional_candidates'] = [{'id': 'self_check:signals:failed_fetch',
            'description': 'Cannot replace a presented candidate', 'evidence_refs': ['/self_check/signals/1']}]
    elif mutation == 'additional_unknown_evidence':
        response['additional_candidates'] = [{'id': 'new', 'description': 'Unsupported candidate',
                                             'evidence_refs': ['/trajectory/99']}]
    elif mutation == 'boolean_edit_index':
        response['decisions'][0].update(decision='accepted', edit_indexes=[False])
    h = Harness(ctx.root / 'harness')
    head = h.head
    refiner = Refiner(h, ctx, RawPlanner(response), observed)
    try:
        refiner.run()
        with pytest.raises(ValueError, match=error):
            refiner.boundary(wait=True)
    finally:
        refiner.close()
    assert h.head == head and h.list() == []
    assert ctx.load('refine_state.json')['status'] == 'failed'


def test_model_additional_candidate_is_accounted_and_linked_to_edit(ctx):
    observation = {'trajectory': [{'type': 'tool', 'result': 'Reusable observed recovery'}],
                   'self_check': {'ok': True, 'issues': [], 'signals': []}}
    response = {**proposal(), 'additional_candidates': [
        {'id': 'recovery', 'description': 'Tool recovery procedure', 'evidence_refs': ['/trajectory/0/result']}],
        'decisions': [decision('recovery', '/trajectory/0/result', accepted=True)]}
    h = Harness(ctx.root / 'harness')
    backend = RawPlanner(response)
    refiner = Refiner(h, ctx, backend, lambda: observation)
    try:
        refiner.run()
        assert len(refiner.boundary(wait=True)) == 1
    finally:
        refiner.close()
    assert len(h.list()) == 1
    assert backend.prompts[0]['candidate_inventory'] == []
    assert ctx.load('refine_state.json')['proposal']['additional_candidates'] == response['additional_candidates']


def test_one_accepted_candidate_and_one_declined_does_not_force_edit_cap(ctx):
    response = accounted_response()
    response['edits'] = proposal()['edits']
    response['decisions'][1].update(decision='accepted', edit_indexes=[0],
        reason='The two recorded fetch failures support a reusable recovery procedure.')
    h = Harness(ctx.root / 'harness')
    ctx.config.refine.max_edits = 2
    refiner = Refiner(h, ctx, RawPlanner(response), observed)
    try:
        refiner.run()
        assert len(refiner.boundary(wait=True)) == 1
    finally:
        refiner.close()
    assert len(h.list()) == 1
    assert ctx.load('refine_state.json')['proposal']['decisions'] == response['decisions']


def test_issue_and_signal_groups_preserve_untyped_and_unfamiliar_evidence():
    observation = {'trajectory': [], 'self_check': {'issues': [
        {'type': 'novel_check', 'detail': 'first'}, {'type': 'novel_check', 'detail': 'second'}, 'legacy issue'],
        'signals': [{'type': 'novel_check', 'detail': 'third'}]}}
    assert candidate_inventory(observation) == [
        {'id': 'self_check:issues:novel_check', 'source': 'self_check.issues', 'type': 'novel_check',
         'count': 2, 'evidence_refs': ['/self_check/issues/0', '/self_check/issues/1']},
        {'id': 'self_check:issues:untyped', 'source': 'self_check.issues', 'type': 'untyped',
         'count': 1, 'evidence_refs': ['/self_check/issues/2']},
        {'id': 'self_check:signals:novel_check', 'source': 'self_check.signals', 'type': 'novel_check',
         'count': 1, 'evidence_refs': ['/self_check/signals/0']},
    ]


def test_worker_stderr_candidates_group_exact_errors_without_losing_code_or_stdout(ctx):
    blocks = [
        {'code': 'operation()', 'result': {'stdout': 'before failure', 'stderr': 'TypeError: invalid argument'}},
        {'code': 'retry()', 'result': {'stdout': 'attempt two', 'stderr': 'TypeError: invalid argument'}},
        {'code': 'other()', 'result': {'stdout': '', 'stderr': 'RuntimeError: unavailable'}},
        {'code': 'success()', 'result': {'stdout': 'done', 'stderr': ''}},
    ]
    observation = {'trajectory': [{'type': 'worker_iteration', 'event': {'code_blocks': blocks}}],
                   'self_check': {'ok': True, 'issues': [], 'signals': []}}
    response = {'summary': 'Recovered execution evidence does not support a change', 'edits': [],
                'additional_candidates': [], 'decisions': [
        decision('trajectory:stderr:0:0', '/trajectory/0/event/code_blocks/0/result/stderr'),
        decision('trajectory:stderr:0:2', '/trajectory/0/event/code_blocks/2/result/stderr'),
    ]}
    h = Harness(ctx.root / 'harness')
    backend = RawPlanner(response)
    refiner = Refiner(h, ctx, backend, lambda: observation)
    try:
        refiner.run()
        refiner.boundary(wait=True)
    finally:
        refiner.close()
    inventory = backend.prompts[0]['candidate_inventory']
    assert len(inventory) == 2
    assert inventory[0]['count'] == 2
    assert inventory[0]['evidence_refs'] == ['/trajectory/0/event/code_blocks/0/result/stderr',
                                          '/trajectory/0/event/code_blocks/1/result/stderr']
    assert inventory[1]['count'] == 1
    assert backend.prompts[0]['trajectory'] == observation['trajectory']


def test_zero_candidates_allows_no_edits_and_schema_retains_configured_cap(ctx):
    response = {'summary': 'No candidates', 'edits': [], 'additional_candidates': [], 'decisions': []}
    observation = {'trajectory': [], 'self_check': {'ok': True, 'issues': [], 'signals': []}}
    backend = RawPlanner(response)
    h = Harness(ctx.root / 'harness')
    refiner = Refiner(h, ctx, backend, lambda: observation)
    try:
        refiner.run()
        assert refiner.boundary(wait=True) == []
    finally:
        refiner.close()
    assert backend.prompts[0]['candidate_inventory'] == []
    assert backend.schemas[0]['properties']['edits']['maxItems'] == ctx.config.refine.max_edits
    assert {'decisions', 'additional_candidates'} <= set(backend.schemas[0]['required'])


def test_legacy_planned_job_resumes_without_inventing_accounting(ctx):
    h = Harness(ctx.root / 'harness')
    job = {'status': 'planned', 'focus': None, 'snapshot': h.snapshot(), 'observed': observed(),
           'branch': h.branch, 'proposal': proposal(), 'operations': ['refine_abcdef'], 'request_id': 'archived'}
    ctx.save('refine_state.json', job)
    backend = RawPlanner(None)
    refiner = Refiner(h, ctx, backend, observed)
    try:
        assert refiner.resume()
        assert len(refiner.boundary(wait=True)) == 1
    finally:
        refiner.close()
    assert backend.prompts == []
    assert ctx.load('refine_state.json')['proposal'] == job['proposal']
    assert 'candidate_inventory' not in ctx.load('refine_state.json')


def test_new_planned_job_cannot_resume_with_missing_decisions(ctx):
    h = Harness(ctx.root / 'harness')
    backend = RawPlanner(accounted_response())
    refiner = Refiner(h, ctx, backend, observed)
    try:
        refiner.run()
        refiner.pending.result(5)
    finally:
        refiner.close()
    job = ctx.load('refine_state.json')
    del job['proposal']['decisions']
    ctx.save('refine_state.json', job)
    resumed = Refiner(h, ctx, backend, observed)
    try:
        assert resumed.resume()
        with pytest.raises(ValueError, match='decisions'):
            resumed.boundary(wait=True)
    finally:
        resumed.close()
    assert h.list() == [] and len(backend.prompts) == 1


def test_unplanned_legacy_job_must_receive_and_return_complete_accounting(ctx):
    h = Harness(ctx.root / 'harness')
    job = {'status': 'planning', 'focus': None, 'snapshot': h.snapshot(), 'observed': observed(),
           'branch': h.branch, 'proposal': None, 'request_id': 'archived'}
    ctx.save('refine_state.json', job)
    backend = RawPlanner(accounted_response())
    refiner = Refiner(h, ctx, backend, observed)
    try:
        assert refiner.resume()
        assert refiner.boundary(wait=True) == []
    finally:
        refiner.close()
    state = ctx.load('refine_state.json')
    assert state['accounting_version'] == 1
    assert state['candidate_inventory'] == backend.prompts[0]['candidate_inventory']
    assert state['proposal']['decisions'] == accounted_response()['decisions']


def test_each_refinement_request_keeps_its_input_inventory_and_declines(ctx):
    ctx.trace = Trace(ctx.run_dir)
    h = Harness(ctx.root / 'harness')
    observation = observed()
    backend = RawPlanner(accounted_response())
    refiner = Refiner(h, ctx, backend, lambda: copy.deepcopy(observation))
    try:
        refiner.run('during task', request_id='mid-task')
        refiner.boundary(wait=True)
        first = ctx.load('refine_state.json')
        observation['trajectory'].append({'type': 'tool', 'result': 'later evidence'})
        refiner.run('after task', request_id='after-task')
        refiner.boundary(wait=True)
        latest = ctx.load('refine_state.json')
    finally:
        refiner.close()
    archives = [json.loads(path.read_text()) for path in (ctx.path / 'refine_requests').glob('*/*.json')]
    assert len(archives) == 2
    by_request = {job['request_id']: job for job in archives}
    assert by_request['mid-task'] == first
    assert by_request['after-task'] == latest
    assert first['observed']['trajectory'] == []
    assert latest['observed']['trajectory'] == [{'type': 'tool', 'result': 'later evidence'}]
    for index, request_id in enumerate(('mid-task', 'after-task')):
        job = by_request[request_id]
        assert job['candidate_inventory'] == backend.prompts[index]['candidate_inventory']
        assert json.loads(job['planner_prompt'].removeprefix(INSTRUCTIONS)) == backend.prompts[index]
        assert job['planner_schema'] == backend.schemas[index]
        assert job['proposal']['decisions'] == accounted_response()['decisions']
        trace = [row for row in read_jsonl(ctx.run_dir / 'trace.jsonl') if row['event'] == 'proposal']
        assert trace[index]['details']['request_id'] == request_id
        assert trace[index]['details']['job_id'] == job['job_id']
    audits = [row for row in read_jsonl(ctx.path / 'refinements.jsonl') if row['status'] == 'applied']
    assert [row['request_id'] for row in audits] == ['mid-task', 'after-task']


def test_replanning_same_request_preserves_discarded_input_and_proposal(ctx):
    h = Harness(ctx.root / 'harness')
    entry = h.create('memory', 'Procedure', 'original')
    backend = Planner(proposal('update', id=entry['id']))
    refiner = Refiner(h, ctx, backend, lambda: {'trajectory': [], 'self_check': {}})
    try:
        refiner.run(request_id='same-request')
        refiner.pending.result(5)
        h.update('memory', entry['id'], 'Procedure', 'concurrent change')
        assert refiner.boundary(wait=True) == []
        refiner.boundary(wait=True)
    finally:
        refiner.close()
    archives = [json.loads(path.read_text()) for path in (ctx.path / 'refine_requests').glob('*/*.json')]
    assert len(archives) == 2
    assert {job['request_id'] for job in archives} == {'same-request'}
    assert len({job['job_id'] for job in archives}) == 2
    discarded = next(job for job in archives if job['status'] == 'discarded')
    applied = next(job for job in archives if job['status'] == 'applied')
    assert discarded['snapshot']['entries']['memory:' + entry['id']]['body'] == 'original'
    assert applied['snapshot']['entries']['memory:' + entry['id']]['body'] == 'concurrent change'
    assert discarded['proposal']['decisions'] and applied['proposal']['decisions']
    assert ctx.load('refine_state.json') == applied


def test_job_archive_is_durable_before_latest_checkpoint_and_resume_reuses_it(ctx, monkeypatch):
    h = Harness(ctx.root / 'harness')
    backend = Planner(proposal())
    observation = lambda: {'trajectory': [], 'self_check': {}}
    refiner = Refiner(h, ctx, backend, observation)
    save = ctx.save

    def interrupted(name, value):
        if name == 'refine_state.json' and value['status'] == 'applied':
            archives = [json.loads(path.read_text()) for path in (ctx.path / 'refine_requests').glob('*/*.json')]
            assert len(archives) == 1 and archives[0] == value
            raise OSError('latest checkpoint interrupted')
        return save(name, value)

    monkeypatch.setattr(ctx, 'save', interrupted)
    try:
        refiner.run(request_id='durable')
        with pytest.raises(OSError, match='checkpoint interrupted'):
            refiner.boundary(wait=True)
    finally:
        refiner.close()
    head = h.head
    job_id = ctx.load('refine_state.json')['job_id']
    monkeypatch.setattr(ctx, 'save', save)
    resumed = Refiner(h, ctx, backend, observation)
    try:
        assert resumed.resume()
        resumed.boundary(wait=True)
    finally:
        resumed.close()
    archives = [json.loads(path.read_text()) for path in (ctx.path / 'refine_requests').glob('*/*.json')]
    assert len(archives) == 1 and archives[0]['job_id'] == job_id
    assert archives[0] == ctx.load('refine_state.json')
    assert h.head == head and len(backend.prompts) == 1


def test_retry_keeps_failed_planner_input_and_raw_proposal(ctx):
    h = Harness(ctx.root / 'harness')
    invalid = {'summary': 'Missing accounting', 'edits': []}
    backend = RawPlanner(invalid)
    refiner = Refiner(h, ctx, backend, observed)
    try:
        refiner.run(request_id='retry-request')
        with pytest.raises(ValueError, match='decisions'):
            refiner.boundary(wait=True)
    finally:
        refiner.close()
    failed = ctx.load('refine_state.json')
    backend.response = accounted_response()
    resumed = Refiner(h, ctx, backend, observed)
    try:
        assert resumed.resume()
        resumed.boundary(wait=True)
    finally:
        resumed.close()
    archives = [json.loads(path.read_text()) for path in (ctx.path / 'refine_requests').glob('*/*.json')]
    assert len(archives) == 2
    assert next(job for job in archives if job['status'] == 'failed') == failed
    assert json.loads(failed['response_text']) == invalid
    applied = next(job for job in archives if job['status'] == 'applied')
    assert json.loads(applied['response_text']) == accounted_response()
    assert applied['request_id'] == failed['request_id']
    assert applied['job_id'] != failed['job_id']
    assert ctx.load('refine_state.json') == applied
