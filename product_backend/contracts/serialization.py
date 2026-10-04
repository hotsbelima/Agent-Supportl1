"""JSON-safe serialization for typed Scenario 1 tool results.

Google ADK wiring is intentionally deferred, but the Phase 3 contract must
already define how typed dataclasses cross the eventual model boundary.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any


def to_tool_payload(value: Any) -> Any:
    """Convert typed contract/domain values into JSON-safe primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_tool_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(to_tool_payload(key)): to_tool_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list, set, frozenset)):
        return [to_tool_payload(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported tool payload type: {type(value).__name__}")
