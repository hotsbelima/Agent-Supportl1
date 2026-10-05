"""Product-owned Scenario 2 event ingestion and deterministic simulator.

This module deliberately does not invoke ADK. Each persisted operational signal is
queued on the dedicated Scenario 2 dispatch topic for the later ADK consumer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import TypeAlias
from uuid import uuid4

from product_backend.application.results import OperationFailure
from product_backend.contracts.events import (
    ApplicationEventType,
    SCENARIO2_AGENT_DISPATCH_TOPIC,
    validate_safe_event_payload,
)
from product_backend.contracts.scenario2_ingestion import (
    Scenario2RunStarted,
    Scenario2SignalIngested,
    Scenario2SignalInput,
)
from product_backend.domain.enums import HealthState, IncidentStatus, RunStatus
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.domain.models import Run
from product_backend.domain.scenario2 import (
    OperationalSignal,
    Scenario2FixtureState,
    ServiceIncident,
)
from product_backend.ports.scenario2 import (
    Scenario2FixtureStateUnitOfWork,
    Scenario2RunStartUnitOfWork,
    Scenario2SignalIngestionUnitOfWork,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
RunStartUowFactory = Callable[[], Scenario2RunStartUnitOfWork]
SignalUowFactory = Callable[[], Scenario2SignalIngestionUnitOfWork]
FixtureUowFactory = Callable[[], Scenario2FixtureStateUnitOfWork]

RunStartResult: TypeAlias = Scenario2RunStarted | OperationFailure
SignalIngestionResult: TypeAlias = Scenario2SignalIngested | OperationFailure
FixtureTransitionResult: TypeAlias = Scenario2FixtureState | OperationFailure
_UNCHANGED = object()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix.upper()}-{uuid4().hex}"


def _failure(
    code: ErrorCode,
    message: str,
    reason: str,
) -> OperationFailure:
    return OperationFailure(
        ok=False,
        error=DomainError(
            code=code,
            message=message,
            details=(("reason", reason),),
        ),
    )


def _clean(value: str) -> str:
    return value.strip()


class Scenario2RunStartService:
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

    async def start(self, *, tenant_id: str) -> RunStartResult:
        tenant = _clean(tenant_id)
        if not tenant:
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Tenant context is required.",
                "empty_tenant",
            )

        now = self._clock()
        run = Run(
            run_id=self._id_factory("run"),
            tenant_id=tenant,
            scenario_id="scenario-2",
            status=RunStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        fixture_state = Scenario2FixtureState(
            tenant_id=tenant,
            run_id=run.run_id,
            dependency_status=HealthState.DEGRADED,
            matching_major_incident_id=None,
            updated_at=now,
        )

        async with self._uow_factory() as uow:
            await uow.runs.add(run)
            await uow.fixture_states.add(fixture_state)
            start_event = await uow.events.append(
                tenant_id=tenant,
                run_id=run.run_id,
                event_type=ApplicationEventType.SIMULATION_STARTED,
                payload={
                    "scenario_id": "scenario-2",
                    "mode": "event-driven",
                },
            )
            await uow.commit()

        return Scenario2RunStarted(
            run=run,
            fixture_state=fixture_state,
            start_event=start_event,
        )


class Scenario2SignalIngestionService:
    def __init__(
        self,
        uow_factory: SignalUowFactory,
        *,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_factory = id_factory

    async def ingest(
        self,
        *,
        tenant_id: str,
        run_id: str,
        signal_input: Scenario2SignalInput,
    ) -> SignalIngestionResult:
        tenant = _clean(tenant_id)
        run_key = _clean(run_id)
        site_id = _clean(signal_input.site_id)
        service_key = _clean(signal_input.service_key)
        symptom_key = _clean(signal_input.symptom_key)
        source_ref = _clean(signal_input.source_ref)

        if not all((tenant, run_key, site_id, service_key, symptom_key, source_ref)):
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Scenario 2 operational signal is incomplete.",
                "missing_signal_identity",
            )
        try:
            validate_safe_event_payload(signal_input.safe_payload)
        except ValueError:
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Scenario 2 signal payload contains unsafe or unsupported data.",
                "unsafe_signal_payload",
            )

        async with self._uow_factory() as uow:
            run = await uow.runs.get(tenant_id=tenant, run_id=run_key)
            if run is None or run.scenario_id != "scenario-2":
                return _failure(
                    ErrorCode.CONTEXT_MISMATCH,
                    "Scenario 2 run was not found.",
                    "run_not_found_or_wrong_scenario",
                )
            if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                return _failure(
                    ErrorCode.INVALID_STATE_TRANSITION,
                    "Closed Scenario 2 run cannot accept new operational facts.",
                    "run_closed",
                )

            existing = await uow.signals.get_by_source_identity(
                tenant_id=tenant,
                run_id=run_key,
                source=signal_input.source,
                source_ref=source_ref,
            )
            if existing is not None:
                if (
                    existing.site_id != site_id
                    or existing.service_key != service_key
                    or existing.symptom_key != symptom_key
                    or existing.safe_payload != signal_input.safe_payload
                ):
                    return _failure(
                        ErrorCode.INVALID_ARGUMENT,
                        "Signal source identity was replayed with different facts.",
                        "conflicting_signal_replay",
                    )
                incident = await uow.service_incidents.get(
                    tenant_id=tenant,
                    run_id=run_key,
                    incident_id=existing.incident_id or "",
                )
                if incident is None:
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Persisted signal lost its ServiceIncident association.",
                        "signal_incident_missing",
                    )
                return Scenario2SignalIngested(
                    signal=existing,
                    service_incident=incident,
                    event=None,
                    dispatch=None,
                    replayed=True,
                )

            now = self._clock()

            incident = await uow.service_incidents.get_for_site_service(
                tenant_id=tenant,
                run_id=run_key,
                site_id=site_id,
                service_key=service_key,
            )
            if incident is None:
                incident_hint = (
                    _clean(signal_input.incident_id_hint)
                    if signal_input.incident_id_hint is not None
                    else ""
                )
                incident = ServiceIncident(
                    incident_id=(
                        incident_hint
                        if incident_hint
                        else self._id_factory("incident")
                    ),
                    tenant_id=tenant,
                    run_id=run_key,
                    site_id=site_id,
                    service_key=service_key,
                    symptom_key=symptom_key,
                    status=IncidentStatus.OPEN,
                    created_at=now,
                    updated_at=now,
                )
                await uow.service_incidents.add(incident)
            elif incident.symptom_key != symptom_key:
                return _failure(
                    ErrorCode.INVALID_ARGUMENT,
                    "Site/service already has a different active Scenario 2 symptom.",
                    "service_incident_symptom_conflict",
                )

            signal_hint = (
                _clean(signal_input.signal_id_hint)
                if signal_input.signal_id_hint is not None
                else ""
            )
            signal = OperationalSignal(
                signal_id=(
                    signal_hint
                    if signal_hint
                    else self._id_factory("signal")
                ),
                tenant_id=tenant,
                run_id=run_key,
                source=signal_input.source,
                site_id=site_id,
                service_key=service_key,
                symptom_key=symptom_key,
                source_ref=source_ref,
                received_at=now,
                safe_payload=dict(signal_input.safe_payload),
                incident_id=incident.incident_id,
            )
            await uow.signals.add(signal)

            event_payload = {
                "scenario_id": "scenario-2",
                "signal_id": signal.signal_id,
                "source": signal.source.value,
                "source_ref": signal.source_ref,
                "site_id": signal.site_id,
                "service_key": signal.service_key,
                "symptom_key": signal.symptom_key,
                "incident_id": incident.incident_id,
                "received_at": signal.received_at.isoformat(),
                "safe_payload": signal.safe_payload,
            }
            event = await uow.events.append(
                tenant_id=tenant,
                run_id=run_key,
                event_type=ApplicationEventType.EXTERNAL_SIGNAL,
                payload=event_payload,
            )
            dispatch = await uow.outbox.enqueue(
                tenant_id=tenant,
                run_id=run_key,
                event_seq=event.seq,
                topic=SCENARIO2_AGENT_DISPATCH_TOPIC,
                payload={
                    "event_id": event.event_id,
                    "event_seq": event.seq,
                    "scenario_id": "scenario-2",
                    "signal_id": signal.signal_id,
                },
            )
            await uow.runs.save(replace(run, updated_at=now))
            await uow.commit()

        return Scenario2SignalIngested(
            signal=signal,
            service_incident=incident,
            event=event,
            dispatch=dispatch,
            replayed=False,
        )


class Scenario2FixtureTransitionService:
    def __init__(
        self,
        uow_factory: FixtureUowFactory,
        *,
        clock: Clock = _utc_now,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def set_dependency_status(
        self,
        *,
        tenant_id: str,
        run_id: str,
        status: HealthState,
    ) -> FixtureTransitionResult:
        if status not in {HealthState.DEGRADED, HealthState.HEALTHY}:
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Scenario 2 fixture dependency supports DEGRADED or HEALTHY.",
                "unsupported_fixture_dependency_status",
            )

        return await self._update(
            tenant_id=tenant_id,
            run_id=run_id,
            dependency_status=status,
            matching_major_incident_id_marker=_UNCHANGED,
        )

    async def set_matching_major_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        major_incident_id: str | None,
    ) -> FixtureTransitionResult:
        normalized = (
            (major_incident_id or "").strip() or None
        )
        return await self._update(
            tenant_id=tenant_id,
            run_id=run_id,
            dependency_status=None,
            matching_major_incident_id_marker=normalized,
        )

    async def _update(
        self,
        *,
        tenant_id: str,
        run_id: str,
        dependency_status: HealthState | None,
        matching_major_incident_id_marker: object,
    ) -> FixtureTransitionResult:
        tenant = _clean(tenant_id)
        run_key = _clean(run_id)

        async with self._uow_factory() as uow:
            run = await uow.runs.get(tenant_id=tenant, run_id=run_key)
            if run is None or run.scenario_id != "scenario-2":
                return _failure(
                    ErrorCode.CONTEXT_MISMATCH,
                    "Scenario 2 run was not found.",
                    "run_not_found_or_wrong_scenario",
                )
            if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
                return _failure(
                    ErrorCode.INVALID_STATE_TRANSITION,
                    "Closed Scenario 2 run cannot mutate fixture state.",
                    "run_closed",
                )
            state = await uow.fixture_states.get(
                tenant_id=tenant,
                run_id=run_key,
            )
            if state is None:
                return _failure(
                    ErrorCode.CONTEXT_MISMATCH,
                    "Scenario 2 fixture state was not found.",
                    "fixture_state_missing",
                )

            now = self._clock()

            matching = state.matching_major_incident_id
            if matching_major_incident_id_marker is not _UNCHANGED:
                if (
                    matching_major_incident_id_marker is not None
                    and not isinstance(matching_major_incident_id_marker, str)
                ):
                    return _failure(
                        ErrorCode.INVALID_ARGUMENT,
                        "Matching Major Incident fixture value is invalid.",
                        "invalid_matching_major_incident_marker",
                    )
                matching = matching_major_incident_id_marker

            updated = replace(
                state,
                dependency_status=dependency_status or state.dependency_status,
                matching_major_incident_id=matching,
                updated_at=now,
            )
            await uow.fixture_states.save(updated)
            await uow.commit()
            return updated


__all__ = [
    "Scenario2FixtureTransitionService",
    "Scenario2RunStartService",
    "Scenario2SignalIngestionService",
]
