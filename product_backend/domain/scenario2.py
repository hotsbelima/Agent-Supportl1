"""Typed Scenario 2 domain contracts.

Scenario 2 is deliberately separate from Scenario 1 field-visit entities.
No dummy device/diagnosis/work-order fields are used for Major Incident flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from .enums import ApprovalDecision, HealthState, IncidentStatus, ProposalStatus


class Scenario2SignalSource(StrEnum):
    MONITORING = "MONITORING"
    ITSM = "ITSM"


class Scenario2ActionType(StrEnum):
    CREATE_MAJOR_INCIDENT = "CREATE_MAJOR_INCIDENT"


class DependencyKind(StrEnum):
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"


class MajorIncidentStatus(StrEnum):
    OPEN = "OPEN"


@dataclass(frozen=True, slots=True)
class ServiceIncident:
    """Scenario 2 site/service incident without a fabricated device identity."""

    incident_id: str
    tenant_id: str
    run_id: str
    site_id: str
    service_key: str
    symptom_key: str
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class OperationalSignal:
    """Product-owned incoming operational fact.

    received_at is assigned by Product ingestion in server UTC. safe_payload
    may contain source metadata/facts but never raw model/provider internals.
    incident_id links to a real site-level Product Incident when one exists;
    repeated signals may intentionally point to the same Incident.
    """

    signal_id: str
    tenant_id: str
    run_id: str
    source: Scenario2SignalSource
    site_id: str
    symptom_key: str
    source_ref: str
    received_at: datetime
    safe_payload: dict[str, Any]
    incident_id: str | None = None


@dataclass(frozen=True, slots=True)
class OperationalSignalEvidenceSnapshot:
    signal_id: str
    source: Scenario2SignalSource
    site_id: str
    symptom_key: str
    source_ref: str


@dataclass(frozen=True, slots=True)
class LocalServiceHealthSnapshot:
    site_id: str
    service_key: str
    network_health: HealthState
    local_service_health: HealthState


@dataclass(frozen=True, slots=True)
class ServiceDependencyMappingSnapshot:
    service_key: str
    dependency_id: str
    dependency_name: str
    dependency_kind: DependencyKind


@dataclass(frozen=True, slots=True)
class ExternalDependencyStatusSnapshot:
    dependency_id: str
    dependency_name: str
    status: HealthState
    status_detail: str


@dataclass(frozen=True, slots=True)
class MajorIncidentSearchSnapshot:
    correlation_key: str
    dependency_id: str
    open_major_incident_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MajorIncidentProposal:
    proposal_id: str
    tenant_id: str
    run_id: str
    correlation_key: str
    service_key: str
    affected_site_ids: tuple[str, ...]
    dependency_id: str
    dependency_name: str
    action_type: Scenario2ActionType
    evidence_ids: tuple[str, ...]
    summary: str
    rationale: str
    status: ProposalStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MajorIncidentApproval:
    approval_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    decision: ApprovalDecision
    decided_at: datetime
    decided_by: str


@dataclass(frozen=True, slots=True)
class MajorIncidentRecord:
    major_incident_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    correlation_key: str
    affected_site_ids: tuple[str, ...]
    dependency_id: str
    dependency_name: str
    summary: str
    status: MajorIncidentStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MajorIncidentExecution:
    execution_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    action_type: Scenario2ActionType
    major_incident_id: str
    executed_at: datetime


@dataclass(frozen=True, slots=True)
class SimulatedNotificationRecord:
    """Optional Product-owned record; never an external notification side effect."""

    notification_id: str
    tenant_id: str
    run_id: str
    major_incident_id: str
    message_key: str
    created_at: datetime


def major_incident_equivalence_key(
    *,
    tenant_id: str,
    correlation_key: str,
    dependency_id: str,
) -> tuple[str, str, str]:
    """Canonical duplicate-prevention key for an equivalent Major Incident."""
    return (tenant_id, correlation_key, dependency_id)


__all__ = [
    "DependencyKind",
    "ExternalDependencyStatusSnapshot",
    "LocalServiceHealthSnapshot",
    "MajorIncidentApproval",
    "MajorIncidentExecution",
    "MajorIncidentRecord",
    "MajorIncidentSearchSnapshot",
    "MajorIncidentStatus",
    "MajorIncidentProposal",
    "OperationalSignal",
    "OperationalSignalEvidenceSnapshot",
    "Scenario2ActionType",
    "ServiceIncident",
    "Scenario2SignalSource",
    "ServiceDependencyMappingSnapshot",
    "SimulatedNotificationRecord",
    "major_incident_equivalence_key",
]
