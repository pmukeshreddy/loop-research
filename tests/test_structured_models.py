import copy
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
import json
import threading
import urllib.request

from jsonschema import SchemaError, ValidationError
import pytest
from referencing.exceptions import Unresolvable


ENTITY_SCHEMA = {
    "type": "object",
    "properties": {"entities": {"type": "array", "items": {"type": "string"}}},
    "required": ["entities"],
    "additionalProperties": False,
}


def adapter(complete, max_concurrent=2):
    from loop_research.structured_models import StructuredModels
    return StructuredModels(complete, max_concurrent=max_concurrent)


def test_valid_json_with_wrong_nested_entity_type_is_rejected_without_repair():
    calls = []

    def complete(prompt, schema):
        calls.append((prompt, schema))
        return '{"entities": [{"name": "Fixture person"}]}'

    with pytest.raises(ValidationError) as error:
        adapter(complete).llm_query_json("Extract entity names", ENTITY_SCHEMA)
    assert list(error.value.path) == ["entities", 0]
    assert calls == [("Extract entity names", ENTITY_SCHEMA)]


def test_valid_result_and_schema_reach_callback_without_prompt_or_value_coercion():
    schema = copy.deepcopy(ENTITY_SCHEMA)
    calls = []

    def complete(prompt, supplied_schema):
        calls.append((prompt, copy.deepcopy(supplied_schema)))
        return '{"entities": ["Fixture person", "  Other name  "]}'

    value = adapter(complete).llm_query_json("Exact supplied prompt\n", schema)
    assert value == {"entities": ["Fixture person", "  Other name  "]}
    assert calls == [("Exact supplied prompt\n", ENTITY_SCHEMA)]
    assert schema == ENTITY_SCHEMA


@pytest.mark.parametrize("schema", [
    {"type": "not-a-json-type"},
    {"type": "array", "items": {"type": "bogus"}},
    {"$schema": "https://example.invalid/unknown-draft"},
    {"$schema": []},
    [],
])
def test_invalid_schema_is_rejected_before_any_single_or_batch_dispatch(schema):
    calls = []
    model = adapter(lambda *args: calls.append(args))
    for operation in (lambda: model.llm_query_json("one", schema),
                      lambda: model.llm_query_json_batched(["one", "two"], schema)):
        with pytest.raises(SchemaError):
            operation()
    assert calls == []


def test_default_draft_is_2020_12_and_explicit_supported_draft_is_honored():
    schema = {"type": "array", "prefixItems": [{"type": "integer"}], "items": False}
    assert adapter(lambda *_: "[3]").llm_query_json("one", schema) == [3]
    with pytest.raises(ValidationError):
        adapter(lambda *_: '["3"]').llm_query_json("one", schema)
    draft7 = {"$schema": "http://json-schema.org/draft-07/schema#", "type": "array",
              "items": [{"type": "integer"}], "additionalItems": False}
    assert adapter(lambda *_: "[3]").llm_query_json("one", draft7) == [3]
    with pytest.raises(ValidationError):
        adapter(lambda *_: "[3, 4]").llm_query_json("one", draft7)


def test_unknown_draft_in_nested_subschema_is_rejected_before_dispatch():
    schema = {"type": "array", "items": {
        "$schema": "https://example.invalid/unknown-draft", "type": "string"}}
    calls = []
    with pytest.raises(SchemaError, match="draft"):
        adapter(lambda *args: calls.append(args) or '[]').llm_query_json("one", schema)
    assert calls == []


def test_schema_like_keys_inside_const_are_data_and_not_subschemas():
    value = {"$schema": "https://example.invalid/not-a-schema", "type": "not-a-type"}
    assert adapter(lambda *_: json.dumps(value)).llm_query_json("one", {"const": value}) == value


@pytest.mark.parametrize("schema", [
    {"default": float("inf")}, {"default": float("nan")},
    {"default": (1, 2)}, {"const": {1: "would-be-coerced-key"}},
])
def test_schema_must_itself_be_json_data_before_dispatch(schema):
    calls = []
    with pytest.raises(SchemaError):
        adapter(lambda *args: calls.append(args) or 'null').llm_query_json("one", schema)
    assert calls == []


def test_nested_explicit_draft_schema_is_checked_under_its_own_rules():
    schema = {"$schema": "http://json-schema.org/draft-07/schema#", "properties": {"value": {
        "$schema": "https://json-schema.org/draft/2020-12/schema", "items": []}}}
    calls = []
    with pytest.raises(SchemaError):
        adapter(lambda *args: calls.append(args) or '{}').llm_query_json("one", schema)
    assert calls == []


@pytest.mark.parametrize("text,value", [("null", None), ("false", False), ("3", 3),
                                        ('"text"', "text"), ("[]", [])])
def test_boolean_schema_returns_native_json_values(text, value):
    assert adapter(lambda *_: text).llm_query_json("one", True) == value
    with pytest.raises(ValidationError):
        adapter(lambda *_: text).llm_query_json("one", False)


@pytest.mark.parametrize("text", ['```json\n{}\n```', '{"entities":', '{} trailing'])
def test_malformed_json_is_not_extracted_or_repaired(text):
    calls = []

    def complete(*args):
        calls.append(args)
        return text

    with pytest.raises(json.JSONDecodeError):
        adapter(complete).llm_query_json("one", True)
    assert len(calls) == 1


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "1e999", '[{"n": NaN}]',
                                 '{"entities": [], "entities": ["silently replaced"]}'])
def test_nonfinite_numbers_and_duplicate_keys_are_rejected(text):
    with pytest.raises(ValueError):
        adapter(lambda *_: text).llm_query_json("one", True)


def test_local_references_validate_nested_values():
    schema = {"$defs": {"name": {"type": "string"}}, "type": "array",
              "items": {"$ref": "#/$defs/name"}}
    assert adapter(lambda *_: '["one"]').llm_query_json("one", schema) == ["one"]
    with pytest.raises(ValidationError):
        adapter(lambda *_: "[{}]").llm_query_json("one", schema)


def test_remote_reference_is_unresolvable_without_network_retrieval(monkeypatch):
    def forbid_network(*args, **kwargs):
        pytest.fail("Schema resolution must never retrieve remote resources")

    monkeypatch.setattr(urllib.request, "urlopen", forbid_network)
    with pytest.raises(Unresolvable):
        adapter(lambda *_: '"one"').llm_query_json(
            "one", {"$ref": "https://example.invalid/schema.json"})


def test_batch_preserves_order_and_context_while_using_configured_concurrency():
    context = ContextVar("structured-test-context", default="missing")
    token = context.set("parent-context")
    lock = threading.Lock()
    two_started = threading.Event()
    second_done = threading.Event()
    active = peak = 0
    completed = []
    contexts = []

    def complete(prompt, schema):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            contexts.append(context.get())
            if active == 2:
                two_started.set()
        assert two_started.wait(3), "Batch requests did not overlap"
        if prompt == "first":
            assert second_done.wait(3)
        with lock:
            completed.append(prompt)
            active -= 1
        if prompt == "second":
            second_done.set()
        return json.dumps(prompt)

    try:
        prompts = ["first", "second", "third", "fourth", "fifth"]
        assert adapter(complete, max_concurrent=2).llm_query_json_batched(
            prompts, {"type": "string"}) == prompts
    finally:
        context.reset(token)
    assert peak == 2
    assert completed.index("second") < completed.index("first")
    assert contexts == ["parent-context"] * 5


def test_batch_failure_propagates_and_never_returns_partial_or_retried_values():
    calls = []
    failure = RuntimeError("fixture transport failure")

    def complete(prompt, schema):
        calls.append(prompt)
        if prompt == "bad":
            raise failure
        return json.dumps(prompt)

    with pytest.raises(RuntimeError) as error:
        adapter(complete, max_concurrent=1).llm_query_json_batched(
            ["good", "bad", "pending"], {"type": "string"})
    assert error.value is failure
    assert calls.count("good") == calls.count("bad") == 1
    assert len(calls) == len(set(calls))


def test_invalid_batch_instance_raises_validation_error():
    with pytest.raises(ValidationError):
        adapter(lambda prompt, _: json.dumps(prompt)).llm_query_json_batched(
            ["one", "two"], {"type": "integer"})


@pytest.mark.parametrize("prompts", ["one", ["one", 2], ["one", None]])
def test_batch_checks_all_prompt_types_before_dispatch(prompts):
    calls = []
    with pytest.raises(TypeError):
        adapter(lambda *args: calls.append(args)).llm_query_json_batched(prompts, True)
    assert calls == []


def test_empty_batch_makes_no_calls():
    calls = []
    assert adapter(lambda *args: calls.append(args)).llm_query_json_batched([], True) == []
    assert calls == []


@pytest.mark.parametrize("max_concurrent", [0, -1, 1.5, True, None])
def test_invalid_concurrency_is_rejected(max_concurrent):
    with pytest.raises(ValueError, match="max_concurrent"):
        adapter(lambda *_: "null", max_concurrent=max_concurrent)


def test_single_call_rejects_nontext_prompt_before_dispatch():
    calls = []
    with pytest.raises(TypeError):
        adapter(lambda *args: calls.append(args)).llm_query_json(["one"], True)
    assert calls == []


def test_callback_cannot_mutate_the_schema_used_for_response_validation():
    schema = copy.deepcopy(ENTITY_SCHEMA)

    def complete(prompt, supplied_schema):
        supplied_schema.clear()
        return '{"entities": [{"name": "wrong type"}]}'

    with pytest.raises(ValidationError):
        adapter(complete).llm_query_json("one", schema)
    assert schema == ENTITY_SCHEMA


def test_concurrent_batches_share_the_instance_concurrency_limit():
    lock = threading.Lock()
    release = threading.Event()
    at_capacity = threading.Event()
    over_capacity = threading.Event()
    active = peak = 0

    def complete(prompt, schema):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 2:
                at_capacity.set()
            if active > 2:
                over_capacity.set()
        assert release.wait(3)
        with lock:
            active -= 1
        return json.dumps(prompt)

    model = adapter(complete, max_concurrent=2)
    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(model.llm_query_json_batched, ["a", "b"], True)
        assert at_capacity.wait(3)
        second = executor.submit(model.llm_query_json_batched, ["c", "d"], True)
        single = executor.submit(model.llm_query_json, "e", True)
        try:
            assert not over_capacity.wait(0.1)
            assert not second.done() and not single.done()
        finally:
            release.set()
        assert first.result() == ["a", "b"]
        assert second.result() == ["c", "d"]
        assert single.result() == "e"
    assert peak == 2
