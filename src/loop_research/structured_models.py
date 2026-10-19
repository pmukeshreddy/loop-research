"""Validated JSON submodel calls over the host's existing model transport."""
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from contextvars import copy_context
from copy import deepcopy
import json
import math
import threading

from jsonschema import Draft202012Validator, SchemaError
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.jsonschema import specification_with


def _check_schema_json(value):
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise SchemaError("JSON schema object keys must be strings")
        for item in value.values():
            _check_schema_json(item)
    elif isinstance(value, list):
        for item in value:
            _check_schema_json(item)
    elif value is None or isinstance(value, (str, bool, int)):
        return
    elif not isinstance(value, float) or not math.isfinite(value):
        raise SchemaError("JSON schema must contain only finite JSON values")


def _validator_class(schema, default):
    validator = default
    if isinstance(schema, dict) and "$schema" in schema:
        if not isinstance(schema["$schema"], str):
            raise SchemaError("JSON schema $schema must name a supported draft")
        validator = validator_for(schema, default=None)
        if validator is None:
            raise SchemaError(f"Unsupported JSON schema draft: {schema['$schema']!r}")
    return validator


def _check_subschema_drafts(schema, validator):
    meta = validator.META_SCHEMA
    specification = specification_with(meta.get("$id", meta.get("id")))
    # Traverse only schema locations for this draft, never const/default data.
    for subschema in specification.subresources_of(schema):
        nested_validator = _validator_class(subschema, validator)
        nested_validator.check_schema(subschema)
        _check_subschema_drafts(subschema, nested_validator)


def _schema_validator(schema):
    schema = deepcopy(schema)
    _check_schema_json(schema)
    if not isinstance(schema, (dict, bool)):
        raise SchemaError("JSON schema must be an object or boolean")
    validator = _validator_class(schema, Draft202012Validator)
    validator.check_schema(schema)
    _check_subschema_drafts(schema, validator)
    return schema, validator


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError(f"Nonfinite JSON number: {value}")


class StructuredModels:
    """Return validated Python values without retries, repair, or type coercion.

    ``complete(prompt, schema)`` must return the raw model text. The host callback
    owns model selection, transport, budgets, and archival. Schemas without a
    ``$schema`` use Draft 2020-12; explicit drafts must be supported by jsonschema.
    Remote reference retrieval is disabled. Standard JSON/schema/transport
    exceptions propagate to the caller, including from a batched request.
    """

    def __init__(self, complete, *, max_concurrent):
        if type(max_concurrent) is not int or max_concurrent < 1:
            raise ValueError("max_concurrent must be a positive integer")
        self.complete = complete
        self.max_concurrent = max_concurrent
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def _query(self, prompt, schema, validator, abort=None):
        with self._slots:
            if abort is not None and abort.is_set():
                raise CancelledError()
            raw = self.complete(prompt, deepcopy(schema))
        if not isinstance(raw, str):
            raise TypeError("Structured model completion must return text")
        value = json.loads(raw, object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        # JSON's finite numeric values can overflow Python's float (e.g. 1e999).
        # Check without transforming or substituting the parsed value.
        json.dumps(value, allow_nan=False)
        validator(schema, registry=Registry()).validate(value)
        return value

    def llm_query_json(self, prompt, schema):
        """Validate the schema before dispatch, then parse and validate one result."""
        if not isinstance(prompt, str):
            raise TypeError("prompt must be a string")
        prepared, validator = _schema_validator(schema)
        return self._query(prompt, prepared, validator)

    def llm_query_json_batched(self, prompts, schema):
        """Run with configured concurrency and return validated values in input order.

        Validate every input before dispatch. A failure raises instead of returning
        partial results; already running calls finish and queued calls are cancelled.
        Each call inherits the submitting thread's context variables.
        """
        if not isinstance(prompts, (list, tuple)) or not all(isinstance(p, str) for p in prompts):
            raise TypeError("prompts must be a sequence of strings")
        prompts = list(prompts)
        prepared, validator = _schema_validator(schema)
        if not prompts:
            return []
        abort = threading.Event()
        failure_lock = threading.Lock()
        first_failure = []

        def query(prompt):
            try:
                return self._query(prompt, prepared, validator, abort)
            except BaseException as error:
                # Close dispatch before this worker can take another queued job.
                # Retain the cause even if a cancelled future is observed first.
                with failure_lock:
                    if not first_failure:
                        first_failure.append(error)
                    abort.set()
                raise

        with ThreadPoolExecutor(max_workers=self.max_concurrent) as executor:
            futures = {executor.submit(copy_context().run, query, prompt): index
                       for index, prompt in enumerate(prompts)}
            results = [None] * len(prompts)
            try:
                for future in as_completed(futures):
                    results[futures[future]] = future.result()
                return results
            except BaseException:
                abort.set()
                for future in futures:
                    future.cancel()
                with failure_lock:
                    failure = first_failure[0] if first_failure else None
                if failure is not None:
                    raise failure
                raise
