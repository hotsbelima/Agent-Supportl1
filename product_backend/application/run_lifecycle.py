"""Persistent Scenario 1 run bootstrap service for the product API."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from product_backend.contracts.events import ApplicationEventType
from product_backend.contracts.run_state import (
    Scenario1Bootstrap,
    Scenario1RunStarted,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import IncidentStatus, RunStatus
from product_backend.domain.models import Incident, Run
from product_backend.domain.transitions import RUN_TRANSITIONS, can_transition
from product_backend.ports.events import ApplicationEventRepository
from product_backend.ports.repositories import IncidentRepository, RunRepository


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix.upper()}-{uuid4().hex}"


class RunStartUnitOfWork(Protocol):
    runs: RunRepository
    incidents: IncidentRepository
    events: ApplicationEventRepository

    async def __aenter__(self) -> "RunStartUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


RunStartUowFactory = Callable[[], RunStartUnitOfWork]


class Scenario1RunStartService:
    """Create persistent Scenario 1 state without invoking Gemini/ADK."""

    def __init__(
        self,
        uow_factory: RunStartUowFactory,
        *,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_factory = id_factory

    async def start(
        self,
        *,
        tenant_id: str,
        bootstrap: Scenario1Bootstrap,
    ) -> Scenario1RunStarted:
        tenant = tenant_id.strip()
        if not tenant:
            raise ValueError("tenant_id is required")
        if not bootstrap.scenario_id.strip():
            raise ValueError("scenario_id is required")
        if not bootstrap.incident_id.strip():
            raise ValueError("incident_id is required")
        if not bootstrap.site_id.strip():
            raise ValueError("site_id is required")
        if not bootstrap.reported_device_id.strip():
            raise ValueError("reported_device_id is required")
        if not bootstrap.symptom.strip():
            raise ValueError("symptom is required")

        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("run clock must return timezone-aware datetime")
        now = now.astimezone(UTC)

        run_id = self._id_factory("run")
        created_run = Run(
            run_id=run_id,
            tenant_id=tenant,
            scenario_id=bootstrap.scenario_id,
            status=RunStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        incident = Incident(
            incident_id=bootstrap.incident_id,
            tenant_id=tenant,
            run_id=run_id,
            site_id=bootstrap.site_id,
            reported_device_id=bootstrap.reported_device_id,
            symptom=bootstrap.symptom,
            status=IncidentStatus.OPEN,
            created_at=now,
            updated_at=now,
        )

        if not can_transition(
            RUN_TRANSITIONS,
            created_run.status,
            RunStatus.ACTIVE,
        ):
            raise RuntimeError("Scenario 1 run cannot transition to ACTIVE")

        active_run = replace(
            created_run,
            status=RunStatus.ACTIVE,
            updated_at=now,
        )
        context = ToolCallContext(tenant_id=tenant, run_id=run_id)

        async with self._uow_factory() as uow:
            await uow.runs.add(created_run)
            await uow.incidents.save(incident)

            await uow.events.append(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                event_type=ApplicationEventType.SIMULATION_STARTED,
                payload={
                    "scenario_id": bootstrap.scenario_id,
                    "status": created_run.status.value,
                },
            )
            await uow.events.append(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                event_type=ApplicationEventType.EXTERNAL_SIGNAL,
                payload={
                    "signal_type": "itsm.incident.created",
                    "details": {
                        "incident_id": incident.incident_id,
                        "site_id": incident.site_id,
                        "reported_device_id": incident.reported_device_id,
                        "symptom": incident.symptom,
                    },
                },
            )
            await uow.runs.save(active_run)
            await uow.events.append(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                event_type=ApplicationEventType.RUN_STATUS_CHANGED,
                payload={
                    "previous_status": created_run.status.value,
                    "status": active_run.status.value,
                    "cause": "simulation_started",
                },
            )
            await uow.commit()

        return Scenario1RunStarted(run=active_run, incident=incident)


__all__ = [
    "RunStartUnitOfWork",
    "Scenario1RunStartService",
]
