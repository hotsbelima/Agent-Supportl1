"""Ports for persisted application lifecycle/audit records."""

from __future__ import annotations

from typing import Any, Protocol

from product_backend.contracts.events import ApplicationEvent, ApplicationEventType


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


__all__ = ["ApplicationEventRepository"]
