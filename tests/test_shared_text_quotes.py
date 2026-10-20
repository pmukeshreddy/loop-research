"""Lossless sharing across raw source text and its canonical JSON spelling."""
import copy
import json

import pytest

from loop_research.shared_text import (
    _encode_quoted, _encode_v2, decode_shared_text, encode_shared_text,
)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def wrapper(payload, strings=None, version='shared-text-v3'):
    return {'format': version, 'shared_texts': strings or [], 'payload': payload}


def test_prose_apostrophe_does_not_hide_json_evidence_shared_with_raw_source():
    source = ('Exact page: 雪, "quoted", apostrophe\'s, backslash\\, newline\n' * 100)
    payload = {'source': source, 'again': source,
               'prompts': ["Check each person's evidence.\n" + compact({'text': source, 'i': i})
                           for i in range(4)]}
    original = copy.deepcopy(payload)
    encoded = encode_shared_text(payload)
    assert encoded['format'] == 'shared-text-v3'
    assert encoded['shared_texts'].count(source) == 1
    assert compact(source) not in encoded['shared_texts']
    assert '$json_quote' in compact(encoded)
    assert len(compact(encoded)) < len(compact(payload)) / 3
    assert compact(decode_shared_text(json.loads(compact(encoded)))) == compact(original)
    assert payload == original


@pytest.mark.parametrize('source', [
    '', '雪 😀 e\u0301', '"quoted" and \\\\slashes', '\n\r\t\b\f\x00',
    '\\u2603 is literal; ☃ is actual', 'already "quoted" /', 'apostrophe\'s',
])
def test_v3_quote_reference_is_exactly_one_json_string_serialization(source):
    encoded = wrapper({'$shared_text_parts': [
        'before:', {'$shared_text': 0}, '/', {'$json_quote': 0}, ':after']}, [source])
    original = copy.deepcopy(encoded)
    assert decode_shared_text(encoded) == 'before:' + source + '/' + json.dumps(source, ensure_ascii=False) + ':after'
    assert encoded == original


@pytest.mark.parametrize('version', ['shared-text-v1', 'shared-text-v2'])
def test_older_formats_keep_new_marker_keys_literal(version):
    payload = {'$json_quote': 0, 'nested': {'$json_quote': False}}
    assert decode_shared_text(wrapper(payload, ['text'], version)) == payload


def test_v3_escapes_literal_new_marker_and_keeps_nested_references_distinct():
    source = 'Evidence with "quotes", 雪 and newlines\n' * 100
    payload = {'$json_quote': {'$shared_text': 0}, 'source': source,
               'prompts': [f'read {i} ' + json.dumps(source, ensure_ascii=False) for i in range(3)]}
    encoded = encode_shared_text(payload)
    assert encoded['format'] == 'shared-text-v3'
    assert set(encoded['payload']) == {'$literal_object'}
    assert decode_shared_text(encoded) == payload
    assert decode_shared_text(wrapper({'$literal_object': {'$json_quote': {'$json_quote': 0}}},
                                     [source])) == {'$json_quote': json.dumps(source, ensure_ascii=False)}


@pytest.mark.parametrize('index', [True, False, -1, 1, 0.0, '0', None, [], {}])
def test_v3_rejects_bad_quote_indices_without_coercion(index):
    with pytest.raises(ValueError):
        decode_shared_text(wrapper({'$json_quote': index}, ['only zero']))


@pytest.mark.parametrize('marker', [
    {'$json_quote': 0, 'extra': 1},
    {'$json_quote': 0, '$shared_text': 0},
    {'$shared_text_parts': [{'$json_quote': True}]},
    {'$shared_text_parts': [{'$json_quote': 0, 'depth': 2}]},
    {'$shared_text_parts': [{'$shared_text_parts': ['nested']}]},
])
def test_v3_rejects_malformed_quote_and_part_shapes(marker):
    with pytest.raises(ValueError):
        decode_shared_text(wrapper(marker, ['source']))


def test_noncanonical_escapes_and_invalid_json_fragments_are_not_normalized():
    source = '雪 and / "quoted" \n' * 60
    unusual = json.dumps(source, ensure_ascii=True).replace('/', '\\/')
    payload = {'raw': source, 'valid': [json.dumps(source, ensure_ascii=False)] * 3,
               'noncanonical': unusual, 'invalid': 'prose "\nnot JSON" and "\\xZ"'}
    encoded = encode_shared_text(payload)
    assert compact(decode_shared_text(encoded)) == compact(payload)
    assert decode_shared_text(encoded)['noncanonical'] == unusual


def test_unprofitable_new_representation_retains_original_v2_encoding():
    payload = {'text': 'Unique literal without repetition', 'quoted': '"different unique literal"'}
    assert encode_shared_text(payload) == wrapper(payload, version='shared-text-v2')


@pytest.mark.parametrize('payload', [
    {'$json_quote': 7, 'other': {'$json_quote': False}},
    ['single-quoted evidence: ' + "'a long unchanged literal ' " * 10] * 3,
    ['x' * 60] * 2,
])
def test_v2_fallback_retains_its_original_marker_escape_rules_and_complete_cost(payload):
    original = _encode_v2(payload)
    assert original['format'] == 'shared-text-v2'
    assert encode_shared_text(payload) == original
    assert decode_shared_text(original) == payload
    if type(payload) is dict:
        assert original['payload'] == payload


def test_selection_compares_complete_serialized_candidates_with_actual_index_widths():
    sources = [f'source {i}: 雪 "quoted" \\\n' * 40 for i in range(110)]
    payload = {'raw': sources, 'prompts': [
        f"Person's evidence {i}: " + compact({'text': value})
        for i, value in enumerate(sources)]}
    candidates = [_encode_v2(payload), _encode_quoted(payload)]
    assert len(candidates[1]['shared_texts']) >= 100
    expected = min(candidates, key=lambda value: len(compact(value)))
    assert expected['format'] == 'shared-text-v3'
    assert encode_shared_text(payload) == expected
    assert compact(decode_shared_text(expected)) == compact(payload)


def test_quoted_text_encoding_is_deterministic_and_preserves_all_scalar_types():
    text = '雪\\ and exact newline\n' * 80
    payload = {'raw': text, 'quoted': [json.dumps(text, ensure_ascii=False)] * 4,
               'types': [None, False, True, 0, -1, 1.0, -0.0, [], {}]}
    first = encode_shared_text(payload)
    assert first == encode_shared_text(copy.deepcopy(payload))
    assert compact(decode_shared_text(first)) == compact(payload)
