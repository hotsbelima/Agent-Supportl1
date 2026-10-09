"""PostgreSQL repository for safe Product application events."""

from __future__ import annotations

from collections.abc import Callable
import math
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from product_backend.contracts.events import (
    AGENT_DISPATCH_TOPIC,
    ApplicationEvent,
    ApplicationEventType,
    ApplicationOutboxRecord,
    SCENARIO2_AGENT_DISPATCH_TOPIC,
    validate_safe_event_payload,
)

from .tables import ApplicationEventRow, ApplicationOutboxRow, RunRow


RUN_CLIENT_IDLE_TIMEOUT = timedelta(seconds=90)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix.upper()}-{uuid4().hex}"


def _require_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("application event clock must return timezone-aware datetime")
    return value.astimezone(UTC)


def _from_row(row: ApplicationEventRow) -> ApplicationEvent:
    payload = deepcopy(row.payload)
    validate_safe_event_payload(payload)
    return ApplicationEvent(
        event_id=row.event_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        seq=row.seq,
        event_type=ApplicationEventType(row.event_type),
        occurred_at=row.occurred_at,
        payload=payload,
    )


class SqlAlchemyApplicationEventRepository:
    """Allocate per-run sequence under a run-row lock.

    Locking the owning run serializes writers for that run. Different runs may
    append concurrently. Generic application events still do not create outbox
    rows. Concrete Product workflows enqueue only explicit dispatch records:
    Scenario 1 uses its Phase 7A operational-event topic and Scenario 2 uses a
    distinct Scenario 2 topic consumed by the Phase 7C/7D native ADK bridge.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._session = session
        self._clock = clock
        self._id_factory = id_factory

    async def append(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_type: ApplicationEventType,
        payload: dict[str, Any],
    ) -> ApplicationEvent:
        if not isinstance(event_type, ApplicationEventType):
            raise ValueError("event_type must be ApplicationEventType")
        validate_safe_event_payload(payload)

        owner = await self._session.execute(
            select(RunRow.run_id)
            .where(
                RunRow.tenant_id == tenant_id,
                RunRow.run_id == run_id,
            )
            .with_for_update()
        )
        if owner.scalar_one_or_none() is None:
            raise ValueError("run context does not exist")

        maximum = await self._session.scalar(
            select(func.max(ApplicationEventRow.seq)).where(
                ApplicationEventRow.tenant_id == tenant_id,
                ApplicationEventRow.run_id == run_id,
            )
        )
        seq = int(maximum or 0) + 1
        occurred_at = _require_aware_utc(self._clock())
        event_id = self._id_factory("event")
        safe_payload = deepcopy(payload)

        row = ApplicationEventRow(
            tenant_id=tenant_id,
            run_id=run_id,
            seq=seq,
            event_id=event_id,
            event_type=event_type.value,
            occurred_at=occurred_at,
            payload=safe_payload,
        )
        self._session.add(row)

        # Flush here so uniqueness/FK failures are raised inside the owning UoW,
        # not deferred beyond the application service boundary.
        await self._session.flush()

        return ApplicationEvent(
            event_id=event_id,
            tenant_id=tenant_id,
            run_id=run_id,
            seq=seq,
            event_type=event_type,
            occurred_at=occurred_at,
            payload=deepcopy(safe_payload),
        )

    async def list_after(
        self,
        *,
        tenant_id: str,
        run_id: str,
        after_seq: int = 0,
        limit: int = 100,
    ) -> tuple[ApplicationEvent, ...]:
        if after_seq < 0:
            raise ValueError("after_seq must be non-negative")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        result = await self._session.execute(
            select(ApplicationEventRow)
            .where(
                ApplicationEventRow.tenant_id == tenant_id,
                ApplicationEventRow.run_id == run_id,
                ApplicationEventRow.seq > after_seq,
            )
            .order_by(ApplicationEventRow.seq)
            .limit(limit)
        )
        return tuple(_from_row(row) for row in result.scalars().all())


def _outbox_from_row(row: ApplicationOutboxRow) -> ApplicationOutboxRecord:
    payload = deepcopy(row.payload)
    validate_safe_event_payload(payload)
    return ApplicationOutboxRecord(
        outbox_id=row.outbox_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        event_seq=row.event_seq,
        topic=row.topic,
        payload=payload,
        created_at=row.created_at,
        available_at=row.available_at,
        delivered_at=row.delivered_at,
        attempt_count=row.attempt_count,
    )


class SqlAlchemyApplicationOutboxRepository:
    """Durable Product-owned delivery bridge for operational event dispatch.

    Claiming uses available_at as a short lease and preserves head-of-line
    ordering per (tenant, run, topic): a later event cannot overtake any earlier
    undelivered event in the same stream, even while that earlier row is leased
    or rescheduled. The database transaction ends before Gemini/ADK work begins,
    so no row/run lock is held across an LLM invocation. A crashed worker makes
    the same row eligible again after the lease; ADK-side operational-event
    correlation prevents a second independent invocation for an event already
    persisted into the native Session history.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._session = session
        self._clock = clock
        self._id_factory = id_factory

    async def enqueue(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_seq: int,
        topic: str,
        payload: dict[str, Any],
    ) -> ApplicationOutboxRecord:
        if event_seq < 1:
            raise ValueError("outbox event_seq must be positive")
        if not topic.strip():
            raise ValueError("outbox topic is required")
        validate_safe_event_payload(payload)
        now = _require_aware_utc(self._clock())
        row = ApplicationOutboxRow(
            tenant_id=tenant_id,
            run_id=run_id,
            outbox_id=self._id_factory("outbox"),
            event_seq=event_seq,
            topic=topic,
            payload=deepcopy(payload),
            created_at=now,
            available_at=now,
            delivered_at=None,
            attempt_count=0,
        )
        self._session.add(row)
        await self._session.flush()
        return _outbox_from_row(row)

    async def claim_next(
        self,
        *,
        topic: str,
        lease_seconds: float,
    ) -> ApplicationOutboxRecord | None:
        if not topic.strip():
            raise ValueError("outbox topic is required")
        if not math.isfinite(lease_seconds) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive finite number")
        now = _require_aware_utc(self._clock())
        if topic in {AGENT_DISPATCH_TOPIC, SCENARIO2_AGENT_DISPATCH_TOPIC}:
            inactive_before = now - RUN_CLIENT_IDLE_TIMEOUT
            await self._session.execute(
                update(RunRow)
                .where(
                    RunRow.scenario_id.in_(("scenario-1", "scenario-2", "scenario-3")),
                    RunRow.dispatch_abandoned_at.is_(None),
                    or_(
                        RunRow.client_last_seen_at.is_(None),
                        RunRow.client_last_seen_at < inactive_before,
                    ),
                )
                .values(dispatch_abandoned_at=now)
            )
        earlier = aliased(ApplicationOutboxRow)
        earlier_undelivered_same_run = exists(
            select(1).where(
                earlier.tenant_id == ApplicationOutboxRow.tenant_id,
                earlier.run_id == ApplicationOutboxRow.run_id,
                earlier.topic == ApplicationOutboxRow.topic,
                earlier.delivered_at.is_(None),
                earlier.event_seq < ApplicationOutboxRow.event_seq,
            )
        )
        statement = (
            select(ApplicationOutboxRow)
            .where(
                ApplicationOutboxRow.topic == topic,
                ApplicationOutboxRow.delivered_at.is_(None),
                ApplicationOutboxRow.available_at <= now,
                ~earlier_undelivered_same_run,
            )
            .order_by(
                ApplicationOutboxRow.available_at,
                ApplicationOutboxRow.created_at,
                ApplicationOutboxRow.outbox_id,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if topic in {AGENT_DISPATCH_TOPIC, SCENARIO2_AGENT_DISPATCH_TOPIC}:
            statement = (
                statement.join(
                    RunRow,
                    (RunRow.tenant_id == ApplicationOutboxRow.tenant_id)
                    & (RunRow.run_id == ApplicationOutboxRow.run_id),
                )
                .where(
                    RunRow.dispatch_abandoned_at.is_(None),
                    RunRow.client_last_seen_at >= now - RUN_CLIENT_IDLE_TIMEOUT,
                )
            )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.attempt_count += 1
        row.available_at = now + timedelta(seconds=lease_seconds)
        await self._session.flush()
        return _outbox_from_row(row)

    async def _locked_row(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
    ) -> ApplicationOutboxRow:
        result = await self._session.execute(
            select(ApplicationOutboxRow)
            .where(
                ApplicationOutboxRow.tenant_id == tenant_id,
                ApplicationOutboxRow.run_id == run_id,
                ApplicationOutboxRow.outbox_id == outbox_id,
            )
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("outbox record does not exist")
        return row

    async def mark_delivered(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
    ) -> ApplicationOutboxRecord:
        row = await self._locked_row(
            tenant_id=tenant_id,
            run_id=run_id,
            outbox_id=outbox_id,
        )
        if row.delivered_at is None:
            row.delivered_at = _require_aware_utc(self._clock())
        await self._session.flush()
        return _outbox_from_row(row)

    async def reschedule(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
        delay_seconds: float,
    ) -> ApplicationOutboxRecord:
        if not math.isfinite(delay_seconds) or delay_seconds < 0:
            raise ValueError("delay_seconds must be a finite non-negative number")
        row = await self._locked_row(
            tenant_id=tenant_id,
            run_id=run_id,
            outbox_id=outbox_id,
        )
        if row.delivered_at is None:
            row.available_at = (
                _require_aware_utc(self._clock())
                + timedelta(seconds=delay_seconds)
            )
        await self._session.flush()
        return _outbox_from_row(row)


__all__ = [
    "SqlAlchemyApplicationEventRepository",
    "SqlAlchemyApplicationOutboxRepository",
]
