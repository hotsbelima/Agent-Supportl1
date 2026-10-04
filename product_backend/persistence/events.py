"""PostgreSQL repository for safe application events and transactional outbox."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_backend.contracts.events import (
    ApplicationEvent,
    ApplicationEventType,
    validate_safe_event_payload,
)

from .tables import ApplicationEventRow, ApplicationOutboxRow, RunRow


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
    return ApplicationEvent(
        event_id=row.event_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        seq=row.seq,
        event_type=ApplicationEventType(row.event_type),
        occurred_at=row.occurred_at,
        payload=deepcopy(row.payload),
    )


class SqlAlchemyApplicationEventRepository:
    """Allocate per-run sequence under a run-row lock.

    Locking the owning run serializes writers for that run. Different runs may
    append concurrently. Each event also creates an outbox record in the same
    database transaction so later delivery cannot observe a state/event split.
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

        outbox_payload = {
            "event_id": event_id,
            "event_type": event_type.value,
            "seq": seq,
            "occurred_at": occurred_at.isoformat(),
            "payload": deepcopy(safe_payload),
        }
        validate_safe_event_payload(outbox_payload)
        self._session.add(
            ApplicationOutboxRow(
                tenant_id=tenant_id,
                run_id=run_id,
                outbox_id=self._id_factory("outbox"),
                event_seq=seq,
                topic="application.event",
                payload=outbox_payload,
                created_at=occurred_at,
                available_at=occurred_at,
                delivered_at=None,
                attempt_count=0,
            )
        )

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


__all__ = ["SqlAlchemyApplicationEventRepository"]
