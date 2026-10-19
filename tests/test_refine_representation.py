"""Refinement sees an exactly reconstructable, fully archived input."""
import copy
import hashlib
import json

from loop_research.harness import Harness
from loop_research.refine import INSTRUCTIONS, Refiner, planning_input


class CapturingPlanner:
    def __init__(self):
        self.calls = []

    def complete(self, prompt, **kwargs):
        self.calls.append((prompt, kwargs))
        return json.dumps({'summary': 'No supported change.', 'edits': [],
                           'additional_candidates': [], 'decisions': []})


def test_planner_wire_input_reconstructs_every_observed_field_and_archives_sizes(ctx):
    text = 'Exact evidence: 雪, "quoted", slash\\, newline\n' * 80
    observation = {'trajectory': [
        {'type': 'tool', 'result': text, 'extra': {'$shared_text': 1}},
        {'type': 'model', 'prompt': text, 'response': text},
        {'type': 'worker_iteration', 'event': {'code_blocks': [], 'unknown': [None, False, 0, -0.0]}},
    ], 'self_check': {'ok': True, 'issues': [], 'signals': [], 'unknown_field': text}}
    original = copy.deepcopy(observation)
    planner = CapturingPlanner()
    refiner = Refiner(Harness(ctx.root / 'harness'), ctx, planner, lambda: observation)
    try:
        refiner.run()
        assert refiner.boundary(wait=True) == []
    finally:
        refiner.close()
    prompt, kwargs = planner.calls[0]
    wire_text = prompt.removeprefix(INSTRUCTIONS)
    wire = json.loads(wire_text)
    assert wire.get('format') == 'shared-text-v2'
    from loop_research.shared_text import decode_shared_text
    state = ctx.load('refine_state.json')
    expected = planning_input(state) | {'max_edits': ctx.config.refine.max_edits}
    expected['evidence_index'] = ['/trajectory', '/self_check', '/entries', '/trajectory/0',
        '/trajectory/1', '/trajectory/2', '/self_check/ok', '/self_check/issues',
        '/self_check/signals', '/self_check/unknown_field']
    decoded = decode_shared_text(wire)
    assert json.dumps(decoded, ensure_ascii=False) == json.dumps(expected, ensure_ascii=False)
    assert observation == original == state['observed']
    assert state['planner_prompt'] == prompt
    assert state['planner_schema'] == kwargs['schema']
    logical_text = json.dumps(expected, ensure_ascii=False)
    metadata = state['planner_representation']
    assert metadata == {
        'format': 'shared-text-v2',
        'logical_payload_chars': len(logical_text),
        'logical_payload_sha256': hashlib.sha256(logical_text.encode()).hexdigest(),
        'wire_payload_chars': len(wire_text),
        'wire_payload_sha256': hashlib.sha256(wire_text.encode()).hexdigest(),
    }
    assert len(wire_text) < len(logical_text)
    assert 'decoded logical payload' in INSTRUCTIONS
    assert 'ordinary strings' in INSTRUCTIONS
