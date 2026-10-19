"""Planner output references must name evidence in the immutable input snapshot."""
import json

import pytest
from jsonschema import Draft202012Validator, ValidationError

from loop_research.harness import Harness
from loop_research.refine import INSTRUCTIONS, Refiner
from loop_research.shared_text import decode_shared_text
from test_refine_candidates import RawPlanner, accounted_response, observed


def test_planner_schema_rejects_nonexistent_records_and_shows_all_evidence_anchors(ctx):
    observation = observed()
    observation['trajectory'] = [{'type': 'tool', 'result': 'first complete record'},
                                 {'type': 'model', 'response': 'second complete record'}]
    observation['self_check']['a/b~c'] = 'unfamiliar evidence remains visible'
    harness = Harness(ctx.root / 'harness')
    harness.create('memory', 'Observed procedure', 'Full original content', trigger='fixture', evidence=[])
    backend = RawPlanner(accounted_response())
    refiner = Refiner(harness, ctx, backend, lambda: observation)
    try:
        refiner.run()
        refiner.boundary(wait=True)
    finally:
        refiner.close()
    schema = backend.schemas[0]
    validator = Draft202012Validator(schema)
    proposed = accounted_response()
    proposed['decisions'][0]['evidence_refs'].append('/trajectory/2')
    with pytest.raises(ValidationError):
        validator.validate(proposed)
    proposed['decisions'][0]['evidence_refs'][-1] = '/trajectory/1'
    validator.validate(proposed)
    anchors = backend.prompts[0]['evidence_index']
    assert set(anchors) == {
        '/trajectory', '/trajectory/0', '/trajectory/1', '/entries', '/entries/0',
        '/self_check', '/self_check/ok', '/self_check/issues', '/self_check/signals',
        '/self_check/signals/0', '/self_check/signals/1', '/self_check/signals/2',
        '/self_check/a~1b~0c',
    }
    assert len(anchors) == len(set(anchors))
    assert schema['$defs']['EvidenceRef']['enum'] == anchors
    for definition in ('Candidate', 'Decision'):
        assert schema['$defs'][definition]['properties']['evidence_refs']['items'] == {
            '$ref': '#/$defs/EvidenceRef'}
    assert backend.prompts[0]['trajectory'] == observation['trajectory']
    assert backend.prompts[0]['self_check'] == observation['self_check']
    job = ctx.load('refine_state.json')
    assert job['evidence_index'] == anchors
    assert decode_shared_text(json.loads(job['planner_prompt'].removeprefix(INSTRUCTIONS))) == backend.prompts[0]


def test_every_deep_candidate_occurrence_remains_an_allowed_anchor(ctx):
    observation = {'trajectory': [{'type': 'worker_iteration', 'event': {'code_blocks': [
        {'code': 'operation()', 'result': {'stdout': 'unchanged output', 'stderr': 'observed error'}}]}}],
        'self_check': {'ok': True, 'issues': [], 'signals': []}}
    reference = '/trajectory/0/event/code_blocks/0/result/stderr'
    response = {'summary': 'No supported edit', 'edits': [], 'additional_candidates': [], 'decisions': [{
        'candidate_id': 'trajectory:stderr:0:0', 'decision': 'declined', 'reason': 'Insufficient evidence.',
        'evidence_refs': [reference], 'edit_indexes': []}]}
    backend = RawPlanner(response)
    refiner = Refiner(Harness(ctx.root / 'harness'), ctx, backend, lambda: observation)
    try:
        refiner.run()
        refiner.boundary(wait=True)
    finally:
        refiner.close()
    assert reference in backend.prompts[0]['evidence_index']
    Draft202012Validator(backend.schemas[0]).validate(response)
