"""Persisted SSE transport helpers for Phase 5A.

PostgreSQL application_events remain the source of truth.  This module only
contains transport/configuration helpers; it does not introduce domain state.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlsplit

from product_backend.contracts.events import ApplicationEvent

from .schemas import ApplicationEventView


@dataclass(frozen=True, slots=True)
class SseSettings:
    """Application-level polling/heartbeat settings for persisted SSE."""

    poll_interval_seconds: float = 0.75
    heartbeat_interval_seconds: float = 15.0
    batch_size: int = 100

    def __post_init__(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("SSE poll interval must be positive")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("SSE heartbeat interval must be positive")
        if not 1 <= self.batch_size <= 1000:
            raise ValueError("SSE batch size must be between 1 and 1000")

    @classmethod
    def from_env(cls) -> "SseSettings":
        return cls(
            poll_interval_seconds=_positive_float_env(
                "SSE_POLL_INTERVAL_SECONDS",
                0.75,
            ),
            heartbeat_interval_seconds=_positive_float_env(
                "SSE_HEARTBEAT_INTERVAL_SECONDS",
                15.0,
            ),
            batch_size=_bounded_int_env(
                "SSE_BATCH_SIZE",
                default=100,
                minimum=1,
                maximum=1000,
            ),
        )


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive number")
    return value


def _bounded_int_env(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


def frontend_origins_from_env() -> tuple[str, ...]:
    """Return exact browser origins allowed by the Phase 5 CORS boundary.

    Local Next.js development is allowed by default.  Production/preview Vercel
    origins must be supplied explicitly through FRONTEND_ORIGINS.
    """

    raw = os.environ.get("FRONTEND_ORIGINS")
    values = (
        ["http://localhost:3000"]
        if raw is None
        else [item.strip() for item in raw.split(",") if item.strip()]
    )

    normalized: list[str] = []
    for value in values:
        if value == "*":
            raise RuntimeError("FRONTEND_ORIGINS must use exact origins, not '*'")
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.netloc
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
        ):
            raise RuntimeError(
                "FRONTEND_ORIGINS entries must be exact http(s) origins"
            )
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in normalized:
            normalized.append(origin)
    return tuple(normalized)


def resolve_sse_cursor(
    *,
    last_event_id: str | None,
    after_seq: str | None,
) -> int:
    """Resolve reconnect cursor using Last-Event-ID precedence."""

    if last_event_id is not None:
        return _parse_cursor(last_event_id)
    if after_seq is not None:
        return _parse_cursor(after_seq)
    return 0


def _parse_cursor(value: str) -> int:
    candidate = value.strip()
    if not candidate or not candidate.isdecimal():
        raise ValueError("cursor must be a non-negative integer")
    cursor = int(candidate)
    if cursor < 0:
        raise ValueError("cursor must be a non-negative integer")
    return cursor


def application_event_sse_frame(event: ApplicationEvent) -> str:
    """Serialize one already-persisted safe application event as one SSE frame."""

    view = ApplicationEventView(
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        run_id=event.run_id,
        seq=event.seq,
        event_type=event.event_type.value,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )
    return (
        f"id: {view.seq}\n"
        "event: application.event\n"
        f"data: {view.model_dump_json()}\n\n"
    )


HEARTBEAT_FRAME = ": keepalive\n\n"


__all__ = [
    "HEARTBEAT_FRAME",
    "SseSettings",
    "application_event_sse_frame",
    "frontend_origins_from_env",
    "resolve_sse_cursor",
]
