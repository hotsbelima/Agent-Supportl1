"""Ports for persisted application lifecycle/audit records."""

from __future__ import annotations

from typing import Any, Protocol

from product_backend.contracts.events import (
    ApplicationEvent,
    ApplicationEventType,
    ApplicationOutboxRecord,
)


class ApplicationEventRepository(Protocol):
    async def append(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_type: ApplicationEventType,
        payload: dict[str, Any],
    ) -> ApplicationEvent: ...

    async def list_after(
        self,
        *,
        tenant_id: str,
        run_id: str,
        after_seq: int = 0,
        limit: int = 100,
    ) -> tuple[ApplicationEvent, ...]: ...


class ApplicationOutboxRepository(Protocol):
    async def enqueue(
        self,
        *,
        tenant_id: str,
        run_id: str,
        event_seq: int,
        topic: str,
        payload: dict[str, Any],
    ) -> ApplicationOutboxRecord: ...

    async def claim_next(
        self,
        *,
        topic: str,
        lease_seconds: float,
    ) -> ApplicationOutboxRecord | None: ...

    async def mark_delivered(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
    ) -> ApplicationOutboxRecord: ...

    async def reschedule(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
        delay_seconds: float,
    ) -> ApplicationOutboxRecord: ...


__all__ = ["ApplicationEventRepository", "ApplicationOutboxRepository"]
