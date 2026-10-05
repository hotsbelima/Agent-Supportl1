"""Application-facing Product state contracts for Scenario 2."""

from __future__ import annotations

from dataclasses import dataclass

from product_backend.domain.models import Evidence, Run
from product_backend.domain.scenario2 import (
    MajorIncidentApproval,
    MajorIncidentExecution,
    MajorIncidentProposal,
    MajorIncidentRecord,
    OperationalSignal,
    ServiceIncident,
)


@dataclass(frozen=True, slots=True)
class Scenario2RunStateSnapshot:
    run: Run
    service_incidents: tuple[ServiceIncident, ...]
    operational_signals: tuple[OperationalSignal, ...]
    evidence: tuple[Evidence, ...]
    proposals: tuple[MajorIncidentProposal, ...]
    approvals: tuple[MajorIncidentApproval, ...]
    executions: tuple[MajorIncidentExecution, ...]
    major_incidents: tuple[MajorIncidentRecord, ...]
    latest_event_seq: int


__all__ = ["Scenario2RunStateSnapshot"]
