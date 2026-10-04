"""Pure Scenario 1 domain entities.

No FastAPI, Google ADK, database or provider types are imported here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

from .enums import (
    ActionType,
    AdminState,
    ApprovalApplicationResult,
    ApprovalDecision,
    ConfigurationState,
    DiagnosisCode,
    EvidenceSourceType,
    HealthState,
    IncidentSearchScope,
    IncidentStatus,
    OperationalState,
    PortSecurityState,
    ProposalStatus,
    RunStatus,
    WorkOrderStatus,
)


@dataclass(frozen=True, slots=True)
class Run:
    run_id: str
    tenant_id: str
    scenario_id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Incident:
    incident_id: str
    tenant_id: str
    run_id: str
    site_id: str
    reported_device_id: str
    symptom: str
    status: IncidentStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class DeviceTopology:
    device_id: str
    site_id: str
    attachment_id: str
    device_type: str
    expected_switch_id: str
    expected_port_id: str


@dataclass(frozen=True, slots=True)
class SiteHealthSnapshot:
    site_id: str
    site_network: HealthState
    payment_service: HealthState
    peer_device_id: str
    peer_reachable: bool
    affected_device_id: str
    affected_device_reachable: bool


@dataclass(frozen=True, slots=True)
class AccessLinkDiagnosticSnapshot:
    target_id: str
    attachment_id: str
    switch_id: str
    port_id: str
    switch_reachable: bool
    admin_state: AdminState
    operational_state: OperationalState
    port_security: PortSecurityState
    configuration: ConfigurationState


@dataclass(frozen=True, slots=True)
class IncidentSearchSnapshot:
    scope: IncidentSearchScope
    entity_id: str
    open_incident_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KbArticle:
    article_id: str
    title: str
    approved: bool
    diagnosis_codes: tuple[DiagnosisCode, ...]
    allowed_actions: tuple[ActionType, ...]
    guidance_code: str


EvidencePayload: TypeAlias = (
    DeviceTopology
    | SiteHealthSnapshot
    | AccessLinkDiagnosticSnapshot
    | IncidentSearchSnapshot
    | KbArticle
)


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: str
    tenant_id: str
    run_id: str
    source_type: EvidenceSourceType
    captured_at: datetime
    entity_ids: tuple[str, ...]
    payload: EvidencePayload
    facts: tuple[str, ...] = ()
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ActionProposal:
    proposal_id: str
    tenant_id: str
    run_id: str
    incident_id: str
    device_id: str
    diagnosis: DiagnosisCode
    action_type: ActionType
    evidence_ids: tuple[str, ...]
    rationale: str
    status: ProposalStatus
    created_at: datetime
    updated_at: datetime
    # Server-derived fields are stored after validation, never chosen by the model.
    derived_parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Approval:
    approval_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    decision: ApprovalDecision
    application_result: ApprovalApplicationResult
    decided_at: datetime
    decided_by: str
    reason_code: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutedAction:
    action_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    incident_id: str
    device_id: str
    action_type: ActionType
    executed_at: datetime


@dataclass(frozen=True, slots=True)
class FieldServiceWorkOrder:
    work_order_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    incident_id: str
    device_id: str
    status: WorkOrderStatus
    created_at: datetime
