"""Phase 7C Product-owned Scenario 2 ingestion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from product_backend.contracts.events import ApplicationEvent, ApplicationOutboxRecord
from product_backend.domain.models import Evidence, Run
from product_backend.domain.scenario2 import (
    MajorIncidentApproval,
    MajorIncidentExecution,
    MajorIncidentProposal,
    MajorIncidentRecord,
    OperationalSignal,
    Scenario2FixtureState,
    Scenario2SignalSource,
    ServiceIncident,
)


@dataclass(frozen=True, slots=True)
class Scenario2SignalInput:
    source: Scenario2SignalSource
    site_id: str
    service_key: str
    symptom_key: str
    source_ref: str
    safe_payload: dict[str, Any]
    signal_id_hint: str | None = None
    incident_id_hint: str | None = None


@dataclass(frozen=True, slots=True)
class Scenario2RunStarted:
    run: Run
    fixture_state: Scenario2FixtureState
    start_event: ApplicationEvent


@dataclass(frozen=True, slots=True)
class Scenario2SignalIngested:
    signal: OperationalSignal
    service_incident: ServiceIncident
    evidence: Evidence
    event: ApplicationEvent | None
    dispatch: ApplicationOutboxRecord | None
    replayed: bool


@dataclass(frozen=True, slots=True)
class Scenario2IngestionStateSnapshot:
    run: Run
    service_incidents: tuple[ServiceIncident, ...]
    operational_signals: tuple[OperationalSignal, ...]
    evidence: tuple[Evidence, ...]
    major_incident_proposals: tuple[MajorIncidentProposal, ...]
    major_incident_approvals: tuple[MajorIncidentApproval, ...]
    major_incident_executions: tuple[MajorIncidentExecution, ...]
    major_incidents: tuple[MajorIncidentRecord, ...]
    fixture_state: Scenario2FixtureState
    latest_event_seq: int


@dataclass(frozen=True, slots=True)
class Scenario2SimulatorStep:
    state: Scenario2IngestionStateSnapshot
    ingested: Scenario2SignalIngested | None
    complete: bool
    next_index: int


__all__ = [
    "Scenario2IngestionStateSnapshot",
    "Scenario2RunStarted",
    "Scenario2SignalIngested",
    "Scenario2SignalInput",
    "Scenario2SimulatorStep",
]
