"""Safe persisted application-event contracts for Phase 4B."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
import re
from typing import Any


class ApplicationEventType(StrEnum):
    SIMULATION_STARTED = "simulation.started"
    EXTERNAL_SIGNAL = "external.signal"
    TOOL_STARTED = "tool.started"
    TOOL_FINISHED = "tool.finished"
    FINDING_RECORDED = "finding.recorded"
    PROPOSAL_CREATED = "proposal.created"
    APPROVAL_DECIDED = "approval.decided"
    ACTION_EXECUTED = "action.executed"
    RUN_STATUS_CHANGED = "run.status_changed"


@dataclass(frozen=True, slots=True)
class ApplicationEvent:
    event_id: str
    tenant_id: str
    run_id: str
    seq: int
    event_type: ApplicationEventType
    occurred_at: datetime
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ApplicationOutboxRecord:
    outbox_id: str
    tenant_id: str
    run_id: str
    event_seq: int
    topic: str
    payload: dict[str, Any]
    created_at: datetime
    available_at: datetime
    delivered_at: datetime | None
    attempt_count: int


_FORBIDDEN_KEYS = frozenset(
    {
        "thought",
        "thoughts",
        "reasoning",
        "chain_of_thought",
        "model_reasoning",
        "internal_reasoning",
        "hidden_reasoning",
        "scratchpad",
        "api_key",
        "apikey",
        "google_api_key",
        "authorization",
        "password",
        "secret",
        "client_secret",
        "access_token",
        "refresh_token",
        "bearer_token",
    }
)

_FORBIDDEN_KEY_STEMS = (
    "thought",
    "thoughts",
    "reasoning",
    "chain_of_thought",
    "model_reasoning",
    "internal_reasoning",
    "hidden_reasoning",
    "scratchpad",
    "api_key",
    "google_api_key",
    "authorization",
    "password",
    "secret",
    "client_secret",
    "access_token",
    "refresh_token",
    "bearer_token",
)


def _forbidden_key(normalized: str) -> bool:
    if normalized in _FORBIDDEN_KEYS:
        return True

    if any(
        normalized.startswith(f"{stem}_")
        or normalized.endswith(f"_{stem}")
        or f"_{stem}_" in normalized
        for stem in _FORBIDDEN_KEY_STEMS
    ):
        return True

    # JSON producers frequently use camelCase/PascalCase. After lower-casing,
    # names such as chainOfThought become "chainofthought" and would otherwise
    # bypass underscore-oriented checks.
    collapsed = normalized.replace("_", "")
    return any(
        stem.replace("_", "") in collapsed
        for stem in _FORBIDDEN_KEY_STEMS
    )


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _validate_json_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string key")
            normalized = _normalize_key(key)
            if _forbidden_key(normalized):
                raise ValueError(f"{path}.{key} is not allowed in persisted events")
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(
        f"{path} contains unsupported event payload type "
        f"{type(value).__name__}"
    )


def validate_safe_event_payload(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("event payload must be an object")
    _validate_json_value(payload, path="payload")


__all__ = [
    "ApplicationEvent",
    "ApplicationEventType",
    "ApplicationOutboxRecord",
    "validate_safe_event_payload",
]
