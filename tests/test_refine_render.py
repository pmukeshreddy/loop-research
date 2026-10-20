"""Context transport must not be reported as a dispatched monolithic prompt."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from loop_research.archive import append_json, write_json


def renderer():
    path = Path(__file__).resolve().parents[1] / 'runs/round2/render.py'
    spec = importlib.util.spec_from_file_location('refine_renderer_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(tmp_path):
    job = {'job_id': 'fixture-job', 'request_id': 'fixture-request', 'status': 'applied',
           'focus': None, 'planner_prompt': 'prospective legacy representation',
           'planner_transport': {'kind': 'repl-context-v1'},
           'candidate_inventory': [], 'proposal': None}
    write_json(tmp_path / 'refine_requests/request/job.json', job)
    directory = tmp_path / 'refine_planners/fixture-job'
    write_json(directory / 'manifest.json', {'transport': 'repl-context-v1', 'status': 'complete',
                                            'logical_payload_chars': 2_000_000})
    call = {'call_id': 'actual-call', 'purpose': 'refine', 'attempt': 0, 'prompt': 'actual planner input.',
            'response': 'actual reply', 'error': None, 'prompt_chars': 21,
            'prompt_sha256': hashlib.sha256(b'actual planner input.').hexdigest()}
    append_json(tmp_path / 'codex_calls.jsonl', call)
    append_json(directory / 'actions.jsonl', {'event': 'model.start', 'action_id': 'fixture-action',
                                            'backend_prompt': call['prompt'], 'schema': None, 'role': 'planner'})
    append_json(directory / 'actions.jsonl', {'event': 'model.attempt', 'action_id': 'fixture-action',
                                            'call_id': 'actual-call', 'status': 'dispatched', 'role': 'planner'})
    return {'task_path': str(tmp_path), 'refine': []}


def test_overflow_render_reports_actual_calls_separately_from_legacy_input(tmp_path):
    audit = fixture(tmp_path)
    rendered = '\n'.join(renderer().refinement_details('fixture', audit))
    assert 'actual-call' in rendered and 'actual planner input' not in rendered
    assert '| 21 |' in rendered
    assert 'not dispatched' in rendered
    assert 'exact transmitted representation' not in rendered
    assert 'actions.jsonl' in rendered and 'context.json' in rendered


def test_overflow_render_rejects_missing_linked_attempt(tmp_path):
    audit = fixture(tmp_path)
    (tmp_path / 'codex_calls.jsonl').write_text('')
    with pytest.raises(ValueError, match='attempt'):
        renderer().refinement_details('fixture', audit)


def test_overflow_render_retains_dispatched_attempt_without_completion(tmp_path):
    audit = fixture(tmp_path)
    call = json.loads((tmp_path / 'codex_calls.jsonl').read_text())
    (tmp_path / 'codex_calls.jsonl').write_text('')
    receipt = {key: call[key] for key in ('call_id', 'purpose', 'attempt', 'prompt_chars', 'prompt_sha256')}
    write_json(tmp_path / 'codex_attempts/actual-call.json', receipt)
    rendered = '\n'.join(renderer().refinement_details('fixture', audit))
    assert 'actual-call' in rendered and '| 21 |' in rendered
    assert 'completion unavailable' in rendered
