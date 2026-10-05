"""Durable Product operational-event -> native ADK dispatch for Phase 7A."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Protocol

from agent_runtime.service import Scenario1AgentRuntime
from product_backend.application.run_state import RunStateService
from product_backend.contracts.events import (
    AGENT_DISPATCH_TOPIC,
    ApplicationOutboxRecord,
)
from product_backend.ports.events import ApplicationOutboxRepository


class DispatchUnitOfWork(Protocol):
    outbox: ApplicationOutboxRepository

    async def __aenter__(self) -> "DispatchUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


DispatchUowFactory = Callable[[], DispatchUnitOfWork]


def _retry_delay_seconds(attempt_count: int) -> float:
    exponent = max(0, min(attempt_count - 1, 5))
    return float(min(30, 2**exponent))


class Scenario1DispatchWorker:
    """Consume durable Product dispatch envelopes without becoming an agent loop.

    The outbox decides *when* a persisted operational event should wake ADK.
    Google ADK still owns the invocation/tool/session lifecycle. The worker never
    polls Monitoring through the model and never interprets incident evidence.
    """

    def __init__(
        self,
        *,
        uow_factory: DispatchUowFactory,
        state_service: RunStateService,
        agent_runtime: Scenario1AgentRuntime,
        poll_interval_seconds: float = 0.5,
        lease_seconds: float = 180.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self._uow_factory = uow_factory
        self._state_service = state_service
        self._agent_runtime = agent_runtime
        self._poll_interval = poll_interval_seconds
        self._lease_seconds = lease_seconds
        self._wake = asyncio.Event()
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._task = asyncio.create_task(
            self._run(),
            name="phase7a-operational-event-dispatch",
        )

    def wake(self) -> None:
        self._wake.set()

    async def close(self) -> None:
        self._stopping.set()
        self._wake.set()
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _claim(self) -> ApplicationOutboxRecord | None:
        async with self._uow_factory() as uow:
            record = await uow.outbox.claim_next(
                topic=AGENT_DISPATCH_TOPIC,
                lease_seconds=self._lease_seconds,
            )
            await uow.commit()
            return record

    async def _mark_delivered(self, record: ApplicationOutboxRecord) -> None:
        async with self._uow_factory() as uow:
            await uow.outbox.mark_delivered(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                outbox_id=record.outbox_id,
            )
            await uow.commit()

    async def _reschedule(self, record: ApplicationOutboxRecord) -> None:
        async with self._uow_factory() as uow:
            await uow.outbox.reschedule(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                outbox_id=record.outbox_id,
                delay_seconds=_retry_delay_seconds(record.attempt_count),
            )
            await uow.commit()

    async def dispatch_once(self) -> bool:
        """Process at most one due envelope; useful for deterministic tests."""
        if not self._agent_runtime.gemini_configured:
            return False

        record = await self._claim()
        if record is None:
            return False

        try:
            event_id = record.payload.get("event_id")
            signal = record.payload.get("signal")
            if not isinstance(event_id, str) or not event_id:
                raise ValueError("dispatch envelope event_id is invalid")
            if not isinstance(signal, dict):
                raise ValueError("dispatch envelope signal is invalid")

            snapshot = await self._state_service.get(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
            )
            if snapshot is None:
                raise RuntimeError("dispatch run state was not found")

            operational_signal = {
                "event_id": event_id,
                "event_seq": record.event_seq,
                "scenario_id": snapshot.run.scenario_id,
                "signal": signal,
                "incidents": [
                    {
                        "incident_id": incident.incident_id,
                        "site_id": incident.site_id,
                        "reported_device_id": incident.reported_device_id,
                        "symptom": incident.symptom,
                        "status": incident.status.value,
                    }
                    for incident in snapshot.incidents
                ],
            }

            await self._agent_runtime.invoke_operational_event(
                tenant_id=record.tenant_id,
                run_id=record.run_id,
                operational_event_id=event_id,
                operational_signal=operational_signal,
            )
        except asyncio.CancelledError:
            # Release the durable lease immediately on graceful shutdown. If ADK
            # already persisted the invocation/pause, redelivery reconciles from
            # native Session history instead of starting a second invocation.
            await self._reschedule(record)
            raise
        except Exception:
            # Do not log provider payloads/secrets. The durable row remains the
            # recovery source and will be retried with the same event identity.
            await self._reschedule(record)
            return True

        await self._mark_delivered(record)
        return True

    async def _run(self) -> None:
        while not self._stopping.is_set():
            processed = await self.dispatch_once()
            if processed:
                continue

            self._wake.clear()
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=self._poll_interval,
                )
            except TimeoutError:
                pass


__all__ = ["Scenario1DispatchWorker"]
