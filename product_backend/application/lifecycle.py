"""Application lifecycle/audit helpers for Phase 4B."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from product_backend.contracts.events import ApplicationEvent, ApplicationEventType
from product_backend.contracts.tools import ToolCallContext
from product_backend.ports.events import ApplicationEventRepository
from product_backend.ports.repositories import RunRepository


class LifecycleUnitOfWork(Protocol):
    runs: RunRepository
    events: ApplicationEventRepository

    async def __aenter__(self) -> "LifecycleUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


LifecycleUowFactory = Callable[[], LifecycleUnitOfWork]


async def append_uow_event(
    uow: object,
    *,
    context: ToolCallContext,
    event_type: ApplicationEventType,
    payload: dict[str, Any],
) -> ApplicationEvent | None:
    """Append when the concrete UoW supports Phase 4B events.

    Phase 3 in-memory test UoWs intentionally remain valid and simply do not
    expose an event repository. Production PostgreSQL UoWs always do.
    """
    events = getattr(uow, "events", None)
    if events is None:
        return None
    return await events.append(
        tenant_id=context.tenant_id,
        run_id=context.run_id,
        event_type=event_type,
        payload=payload,
    )


class ApplicationLifecycleService:
    def __init__(self, uow_factory: LifecycleUowFactory) -> None:
        self._uow_factory = uow_factory

    async def _require_run(
        self,
        uow: LifecycleUnitOfWork,
        context: ToolCallContext,
    ) -> None:
        run = await uow.runs.get(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
        )
        if run is None:
            raise ValueError("run context does not exist")

    async def record_simulation_started(
        self,
        context: ToolCallContext,
        *,
        scenario_id: str,
    ) -> ApplicationEvent:
        if not scenario_id.strip():
            raise ValueError("scenario_id is required")
        async with self._uow_factory() as uow:
            await self._require_run(uow, context)
            event = await uow.events.append(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                event_type=ApplicationEventType.SIMULATION_STARTED,
                payload={"scenario_id": scenario_id},
            )
            await uow.commit()
            return event

    async def record_external_signal(
        self,
        context: ToolCallContext,
        *,
        signal_type: str,
        details: dict[str, Any],
    ) -> ApplicationEvent:
        if not signal_type.strip():
            raise ValueError("signal_type is required")
        async with self._uow_factory() as uow:
            await self._require_run(uow, context)
            event = await uow.events.append(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                event_type=ApplicationEventType.EXTERNAL_SIGNAL,
                payload={
                    "signal_type": signal_type,
                    "details": details,
                },
            )
            await uow.commit()
            return event

    async def record_finding(
        self,
        context: ToolCallContext,
        *,
        finding_code: str,
        summary: str,
        evidence_ids: tuple[str, ...],
    ) -> ApplicationEvent:
        if not finding_code.strip():
            raise ValueError("finding_code is required")
        if not summary.strip():
            raise ValueError("finding summary is required")
        if not evidence_ids:
            raise ValueError("finding must reference evidence")
        async with self._uow_factory() as uow:
            await self._require_run(uow, context)
            event = await uow.events.append(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                event_type=ApplicationEventType.FINDING_RECORDED,
                payload={
                    "finding_code": finding_code,
                    "summary": summary,
                    "evidence_ids": list(evidence_ids),
                },
            )
            await uow.commit()
            return event

    async def timeline(
        self,
        context: ToolCallContext,
        *,
        after_seq: int = 0,
        limit: int = 100,
    ) -> tuple[ApplicationEvent, ...]:
        async with self._uow_factory() as uow:
            await self._require_run(uow, context)
            return await uow.events.list_after(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                after_seq=after_seq,
                limit=limit,
            )


__all__ = [
    "ApplicationLifecycleService",
    "LifecycleUnitOfWork",
    "append_uow_event",
]
