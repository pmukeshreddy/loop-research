"""Lossless, inspectable sharing of exact repeated JSON string values.

The versioned wrapper is always returned, including when its string table is
empty. Savings are measured in compact JSON characters (ensure_ascii=False),
including escaping, reference indices, table entries and the complete wrapper.
No content is shortened, normalized, compressed or inferred.
"""
from collections import Counter
import json
import math


_FORMAT = "shared-text-v1"
_MARKERS = {"$shared_text", "$literal_object"}


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _string_counts(value):
    """Validate JSON without coercion, counting values rather than object keys."""
    counts = Counter()
    ancestors = set()

    def visit(node):
        kind = type(node)
        if kind is str:
            counts[node] += 1
        elif node is None or kind in (bool, int):
            return
        elif kind is float:
            if not math.isfinite(node):
                raise ValueError("JSON numbers must be finite")
        elif kind in (dict, list):
            identity = id(node)
            if identity in ancestors:
                raise ValueError("Cyclic containers are not JSON")
            ancestors.add(identity)
            try:
                if kind is dict:
                    for key, item in node.items():
                        if type(key) is not str:
                            raise ValueError("JSON object keys must be strings")
                        visit(item)
                else:
                    for item in node:
                        visit(item)
            finally:
                ancestors.remove(identity)
        else:
            raise ValueError(f"Unsupported JSON value type: {kind.__name__}")

    visit(value)
    return counts


def _encode_node(value, indices):
    if isinstance(value, str):
        return {"$shared_text": indices[value]} if value in indices else value
    if isinstance(value, list):
        return [_encode_node(item, indices) for item in value]
    if isinstance(value, dict):
        mapping = {key: _encode_node(item, indices) for key, item in value.items()}
        # Escape the mapping itself once. Its values have already been encoded,
        # including any nested literal objects that contain reserved keys.
        return {"$literal_object": mapping} if _MARKERS.intersection(value) else mapping
    return value


def encode_shared_text(payload):
    """Return a shared-text-v1 wrapper, without modifying the JSON payload.

    Repeated strings are considered in first-occurrence order. Each selected
    entry must reduce compact JSON cost at its actual table index; interning is
    retained only when the complete result is smaller than the original JSON.
    An empty table preserves the same API when there is no net saving. Invalid
    JSON values, including non-string keys, cycles and nonfinite numbers, raise
    ValueError rather than being coerced.
    """
    counts = _string_counts(payload)
    strings = []
    indices = {}
    for value, count in counts.items():
        if count < 2:
            continue
        literal_chars = len(_compact(value))
        reference_chars = len(_compact({"$shared_text": len(strings)}))
        table_chars = literal_chars + (1 if strings else 0)
        if count * (literal_chars - reference_chars) > table_chars:
            indices[value] = len(strings)
            strings.append(value)
    wrapper = {"format": _FORMAT, "shared_texts": strings,
               "payload": _encode_node(payload, indices)}
    if strings and len(_compact(wrapper)) >= len(_compact(payload)):
        wrapper = {"format": _FORMAT, "shared_texts": [],
                   "payload": _encode_node(payload, {})}
    return wrapper


def decode_shared_text(wrapper):
    """Restore the exact JSON value; reject malformed wrappers with ValueError.

    A reference must be exactly {"$shared_text": integer_index}; booleans are
    not indices. A literal-object escape decodes the values of its mapping,
    while preserving that mapping's own keys without interpreting them again.
    """
    _string_counts(wrapper)
    if (type(wrapper) is not dict
            or set(wrapper) != {"format", "shared_texts", "payload"}
            or wrapper["format"] != _FORMAT):
        raise ValueError("Expected a shared-text-v1 wrapper")
    strings = wrapper["shared_texts"]
    if type(strings) is not list or any(type(value) is not str for value in strings):
        raise ValueError("shared_texts must be a list of literal strings")

    def decode(value):
        if isinstance(value, list):
            return [decode(item) for item in value]
        if isinstance(value, dict):
            if "$shared_text" in value:
                index = value["$shared_text"]
                if (set(value) != {"$shared_text"} or type(index) is not int
                        or not 0 <= index < len(strings)):
                    raise ValueError("Invalid shared-text reference")
                return strings[index]
            if "$literal_object" in value:
                mapping = value["$literal_object"]
                if set(value) != {"$literal_object"} or type(mapping) is not dict:
                    raise ValueError("Invalid literal-object escape")
                return {key: decode(item) for key, item in mapping.items()}
            return {key: decode(item) for key, item in value.items()}
        return value

    return decode(wrapper["payload"])
