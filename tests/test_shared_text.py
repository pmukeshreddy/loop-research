import copy
import json
import random

import pytest


def encode(payload):
    from loop_research.shared_text import encode_shared_text
    return encode_shared_text(payload)


def decode(wrapper):
    from loop_research.shared_text import decode_shared_text
    return decode_shared_text(wrapper)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def wire(payload, strings=None):
    return {"format": "shared-text-v2", "shared_texts": strings or [], "payload": payload}


@pytest.mark.parametrize("payload", [
    None, False, True, 0, 1, -7, 1.0, -0.0, 1.25, "", "  exact\n\ttext  ",
    [], {}, [None, False, 0, 0.0, "0"],
    {"": [], "雪": {"escaped": '\\u2603 / "quoted"\n', "actual": "☃ 😀 e\u0301"}},
])
def test_round_trip_preserves_json_scalar_types_and_exact_strings(payload):
    encoded = encode(payload)
    assert set(encoded) == {"format", "shared_texts", "payload"}
    assert encoded["format"] == "shared-text-v2"
    assert compact(decode(json.loads(compact(encoded)))) == compact(payload)


def test_nested_duplicate_text_is_stored_once_with_full_wrapper_savings():
    repeated = '  Exact "quotation" with \\slashes, 雪 and\nnewlines.  ' * 40
    payload = {"text": repeated, "nested": [repeated, {"evidence": repeated}],
               "small": "visible", "number": 3}
    encoded = encode(payload)
    assert encoded["shared_texts"] == [repeated]
    assert encoded["payload"] == {"text": {"$shared_text": 0},
        "nested": [{"$shared_text": 0}, {"evidence": {"$shared_text": 0}}],
        "small": "visible", "number": 3}
    assert len(compact(encoded)) < len(compact(payload))
    assert decode(encoded) == payload


def test_unique_text_and_unprofitable_repetition_remain_literal():
    payload = {"long_unique": "u" * 10000, "small": ["x"] * 20, "visible": "read me"}
    assert encode(payload) == wire(payload)


def test_savings_must_cover_complete_wrapper_not_just_references_and_table():
    payload = ["x" * 60, "x" * 60]
    candidate = wire([{"$shared_text": 0}, {"$shared_text": 0}], ["x" * 60])
    assert len(compact(candidate)) >= len(compact(payload))
    assert encode(payload) == wire(payload)


def test_escaped_json_character_cost_can_justify_interning_shorter_text():
    repeated = "\n" * 50
    payload = [repeated, repeated, repeated]
    encoded = encode(payload)
    assert encoded["shared_texts"] == [repeated]
    assert len(compact(encoded)) < len(compact(payload))
    assert decode(encoded) == payload


def test_reference_index_width_is_included_in_entry_cost():
    texts = [str(i) + ":" + "large repeated passage " * 25 for i in range(10)]
    borderline = "b" * 36
    payload = [[s, s] for s in texts] + [[borderline, borderline]]
    encoded = encode(payload)
    assert encoded["shared_texts"] == texts
    assert encoded["payload"][-1] == [borderline, borderline]
    assert len(compact(encoded)) < len(compact(payload))
    assert decode(encoded) == payload


def test_object_key_names_are_never_interned():
    key = "long literal object key " * 50
    payload = [{key: 1}, {key: 2}, {key: 3}]
    assert encode(payload) == wire(payload)


@pytest.mark.parametrize("payload", [
    {"$shared_text": 0}, {"$shared_text": True}, {"$shared_text": -1},
    {"$shared_text": 0, "other": "literal"},
    {"$literal_object": None},
    {"$literal_object": {"$shared_text": 0}},
    {"$literal_object": {"$literal_object": {"$shared_text": "literal"}}},
    {"$shared_text": {"$literal_object": [1, {"$shared_text": False}]}},
])
def test_marker_collisions_round_trip_through_one_literal_object_layer(payload):
    encoded = encode(payload)
    assert list(encoded["payload"]) == ["$literal_object"]
    assert compact(decode(json.loads(compact(encoded)))) == compact(payload)


def test_decoder_distinguishes_literal_marker_keys_from_references_in_their_values():
    encoded = wire({
        "reference": {"$shared_text": 0},
        "literal": {"$literal_object": {"$shared_text": 0}},
        "value_reference": {"$literal_object": {"$shared_text": {"$shared_text": 0}}},
        "nested": {"$literal_object": {"$literal_object": {
            "$literal_object": {"$shared_text": 0}}}},
    }, ["exact table text"])
    assert decode(encoded) == {
        "reference": "exact table text",
        "literal": {"$shared_text": 0},
        "value_reference": {"$shared_text": "exact table text"},
        "nested": {"$literal_object": {"$shared_text": 0}},
    }


def test_interned_text_inside_nested_marker_objects_remains_lossless():
    repeated = "preserved text " * 200
    payload = {"$literal_object": {"$shared_text": repeated},
               "ordinary": [{"$shared_text": repeated}, repeated]}
    encoded = encode(payload)
    assert encoded["shared_texts"] == [repeated]
    assert decode(encoded) == payload
    assert len(compact(encoded)) < len(compact(payload))


def test_encoding_is_deterministic_and_both_operations_leave_inputs_unmodified():
    payload = {"items": ["abc " * 300] * 4, "nested": {"$shared_text": [False, 1, 1.0]}}
    original = copy.deepcopy(payload)
    first = encode(payload)
    assert first == encode(copy.deepcopy(payload))
    assert compact(payload) == compact(original)
    saved = copy.deepcopy(first)
    decoded = decode(first)
    decoded["nested"]["$shared_text"].append("changed")
    assert first == saved
    first["payload"]["items"].append("changed")
    assert payload == original


def test_seeded_nested_json_round_trips_without_value_coercion():
    rng = random.Random(17)
    scalars = [None, True, False, 0, 1, -1, 1.0, -0.0, "", "  雪\n", "repeated " * 100]

    def value(depth):
        if depth == 0 or rng.randrange(3) == 0:
            return rng.choice(scalars)
        if rng.randrange(2):
            return [value(depth - 1) for _ in range(rng.randrange(5))]
        return {key: value(depth - 1) for key in
                rng.sample(["a", "雪", "$shared_text", "$literal_object"], rng.randrange(5))}

    for _ in range(80):
        payload = value(5)
        assert compact(decode(json.loads(compact(encode(payload))))) == compact(payload)


@pytest.mark.parametrize("wrapper", [
    None, [], {}, {"format": "unknown-version", "shared_texts": [], "payload": None},
    {"format": "shared-text-v1", "payload": None},
    {"format": "shared-text-v1", "shared_texts": [], "payload": None, "extra": 1},
    {"format": "shared-text-v1", "shared_texts": "text", "payload": None},
    {"format": "shared-text-v1", "shared_texts": [1], "payload": None},
])
def test_decoder_rejects_malformed_wrapper_and_unknown_versions(wrapper):
    with pytest.raises(ValueError):
        decode(wrapper)


@pytest.mark.parametrize("reference", [True, False, -1, 1, 1.0, "0", None, [], {}])
def test_decoder_rejects_invalid_reference_indices(reference):
    with pytest.raises(ValueError):
        decode(wire({"nested": [{"$shared_text": reference}]}, ["only index zero"]))


@pytest.mark.parametrize("payload", [
    {"$shared_text": 0, "other": 1},
    {"$literal_object": None}, {"$literal_object": []},
    {"$literal_object": 0}, {"$literal_object": {}, "other": 1},
])
def test_decoder_rejects_malformed_unescaped_marker_objects(payload):
    with pytest.raises(ValueError):
        decode(wire(payload, ["text"]))


@pytest.mark.parametrize("payload", [
    ("tuple",), {1: "non-string key"}, float("nan"), float("inf"),
    {"nested": [float("-inf")]}, b"bytes", {"set"},
])
def test_non_json_inputs_are_rejected_instead_of_coerced(payload):
    with pytest.raises(ValueError):
        encode(payload)
    with pytest.raises(ValueError):
        decode(wire(payload))


def test_cyclic_inputs_are_rejected_but_repeated_container_values_are_allowed():
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError):
        encode(cyclic)
    with pytest.raises(ValueError):
        decode(wire(cyclic))
    shared = {"text": "unchanged " * 100}
    assert decode(encode([shared, shared])) == [shared, shared]
