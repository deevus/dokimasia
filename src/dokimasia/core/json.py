from __future__ import annotations

import json
from typing import Any


def decode_nested_json_strings(value: Any) -> Any:
    """Recursively decode JSON object/array strings inside JSON-like values."""
    if isinstance(value, dict):
        return {key: decode_nested_json_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_nested_json_strings(item) for item in value]
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    return decode_nested_json_strings(decoded)
