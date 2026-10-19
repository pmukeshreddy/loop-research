"""Exact embedded text must remain readable once, with lossless concatenation."""
import copy
import json

import pytest

from loop_research.shared_text import decode_shared_text, encode_shared_text


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def test_different_prompts_share_embedded_quoted_text_without_losing_wrappers():
    passage = 'Exact evidence with 雪, "quotes", slash \\, and newline\n' * 30
    payload = {'prompts': [f'Request {i}: ' + compact({'text': passage, 'record': i})
                           + f'\nEnd {i}.' for i in range(8)], 'number': 1.0}
    original = copy.deepcopy(payload)
    encoded = encode_shared_text(payload)
    assert encoded['format'] == 'shared-text-v2'
    assert compact(passage) in encoded['shared_texts']
    assert compact(encoded).count('$shared_text_parts') == len(payload['prompts'])
    assert len(compact(encoded)) < len(compact(payload)) - 6 * len(compact(passage))
    assert compact(decode_shared_text(json.loads(compact(encoded)))) == compact(original)
    assert payload == original


@pytest.mark.parametrize('ending', ['\n', '\r\n', '\r', '\v', '\f', '\u2028', '\u2029'])
def test_fragment_round_trip_preserves_all_line_endings_and_quote_escapes(ending):
    value = ('  exact \\ "quoted" 雪 e\u0301' + ending) * 20
    payload = [f'prefix-{i} ' + compact(value) + ending + f'suffix-{i}' for i in range(5)]
    encoded = encode_shared_text(payload)
    assert encoded['format'] == 'shared-text-v2'
    assert compact(value) in encoded['shared_texts']
    assert compact(decode_shared_text(json.loads(compact(encoded)))) == compact(payload)


def test_fragment_marker_collision_is_escaped_while_legacy_literal_is_unchanged():
    payload = {'$shared_text_parts': ['literal', {'$shared_text': 1}], 'other': False}
    encoded = encode_shared_text(payload)
    assert '$literal_object' in encoded['payload']
    assert decode_shared_text(encoded) == payload
    legacy = {'format': 'shared-text-v1', 'shared_texts': [],
              'payload': {'$shared_text_parts': ['literal']}}
    assert decode_shared_text(legacy) == legacy['payload']


def test_decoder_concatenates_only_literals_and_valid_table_references():
    wrapper = {'format': 'shared-text-v2', 'shared_texts': [' exact\n', '雪'],
               'payload': {'$shared_text_parts': ['prefix', {'$shared_text': 0},
                                                  {'$shared_text': 1}, 'suffix']}}
    assert decode_shared_text(wrapper) == 'prefix exact\n雪suffix'


@pytest.mark.parametrize('parts', [None, 'text', 1, [False], [None], [1],
    [{}], [{'$shared_text': True}], [{'$shared_text': -1}], [{'$shared_text': 1}],
    [{'$shared_text': 0, 'extra': True}], [{'$shared_text_parts': ['nested']}],
    [{'$literal_object': {'key': 'value'}}]])
def test_decoder_rejects_malformed_fragment_parts_without_coercion(parts):
    wrapper = {'format': 'shared-text-v2', 'shared_texts': ['only index zero'],
               'payload': {'$shared_text_parts': parts}}
    with pytest.raises(ValueError):
        decode_shared_text(wrapper)


def test_v2_decoder_rejects_extra_keys_on_a_fragment_marker():
    with pytest.raises(ValueError):
        decode_shared_text({'format': 'shared-text-v2', 'shared_texts': [],
                            'payload': {'$shared_text_parts': ['a'], 'extra': 'b'}})


@pytest.mark.parametrize('version', [None, True, 2, [], {}])
def test_non_string_version_is_rejected_as_invalid_json_wrapper(version):
    with pytest.raises(ValueError):
        decode_shared_text({'format': version, 'shared_texts': [], 'payload': None})
