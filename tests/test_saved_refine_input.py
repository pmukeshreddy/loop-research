"""Saved-input replay must verify both original and losslessly encoded jobs."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def helper():
    path = Path(__file__).resolve().parents[1] / 'runs/round2/replay_saved_refine.py'
    spec = importlib.util.spec_from_file_location('saved_refine_input_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serialized(value):
    return json.dumps(value, ensure_ascii=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def fixture(version):
    expected = {'focus': None, 'candidate_inventory': [], 'entries': [],
                'trajectory': [{'text': 'exact 雪\n'}], 'self_check': {'issues': [], 'signals': []},
                'max_edits': 2}
    logical = {**expected, 'evidence_index': ['/trajectory/0']}
    wire = {'format': version, 'shared_texts': [], 'payload': logical}
    wire_text = json.dumps(wire, ensure_ascii=False, separators=(',', ':'))
    job = {'planner_prompt': 'Original instructions\n' + wire_text,
           'evidence_index': logical['evidence_index'], 'planner_representation': {
               'format': version, 'wire_payload_chars': len(wire_text),
               'wire_payload_sha256': digest(wire_text),
               'logical_payload_chars': len(serialized(logical)),
               'logical_payload_sha256': digest(serialized(logical))}}
    return job, expected


@pytest.mark.parametrize('version', ['shared-text-v1', 'shared-text-v2'])
def test_saved_encoded_prompt_matches_original_logical_fields_and_index(version):
    job, expected = fixture(version)
    before = copy.deepcopy(job)
    result = helper().verify_saved_input(job, expected)
    assert result['representation'] == version and result['logical_input_equal'] is True
    assert result['wire_hash_verified'] is True and result['logical_hash_verified'] is True
    assert job == before


def test_legacy_unencoded_prompt_still_requires_exact_payload_suffix():
    expected = {'focus': '  exact\n', 'max_edits': 2}
    result = helper().verify_saved_input({'planner_prompt': 'Instructions\n' + serialized(expected)}, expected)
    assert result['representation'] == 'plain-json' and result['logical_input_equal'] is True
    with pytest.raises(ValueError):
        helper().verify_saved_input({'planner_prompt': serialized(expected) + 'altered'}, expected)


@pytest.mark.parametrize('change', ['wire_hash', 'wire_size', 'logical_hash', 'logical_size',
                                  'format', 'field', 'index', 'trailing'])
def test_encoded_saved_input_rejects_tampered_provenance_or_logical_values(change):
    job, expected = fixture('shared-text-v2')
    metadata = job['planner_representation']
    if change in ('wire_hash', 'logical_hash'):
        metadata[change.replace('_hash', '_payload_sha256')] = 'wrong'
    elif change in ('wire_size', 'logical_size'):
        metadata[change.replace('_size', '_payload_chars')] += 1
    elif change == 'format':
        metadata['format'] = 'unknown-version'
    elif change == 'field':
        expected['trajectory'][0]['text'] += 'changed'
    elif change == 'index':
        job['evidence_index'] = ['/trajectory/1']
    else:
        job['planner_prompt'] += '\n'
    with pytest.raises(ValueError):
        helper().verify_saved_input(job, expected)
