"""Stable Product API schemas through the Phase 6C ADK resume boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from product_backend.contracts.events import ApplicationEvent
from product_backend.contracts.run_state import RunStateSnapshot
from product_backend.contracts.scenario2_ingestion import (
    Scenario2IngestionStateSnapshot,
    Scenario2SignalIngested,
    Scenario2SimulatorStep,
)
from product_backend.contracts.serialization import to_tool_payload
from product_backend.application.results import ApprovalProcessed
from product_backend.application.scenario2_results import MajorIncidentDecisionProcessed
from product_backend.domain.errors import DomainError


class ApiErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, str] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class AcceptanceAccessLinkStateRequest(BaseModel):
    operational_state: Literal["UP", "DOWN"]


class AcceptanceAccessLinkStateResponse(BaseModel):
    tenant_id: str
    run_id: str
    operational_state: Literal["UP", "DOWN"]
    scope: Literal["phase6d_acceptance_only"] = "phase6d_acceptance_only"


class Scenario2SignalIngestRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source: Literal["MONITORING", "ITSM"]
    site_id: str = Field(min_length=1, max_length=128)
    service_key: str = Field(min_length=1, max_length=128)
    symptom_key: str = Field(min_length=1, max_length=128)
    source_ref: str = Field(min_length=1, max_length=256)
    safe_payload: dict[str, Any] = Field(default_factory=dict)


class Scenario2DependencyStatusRequest(BaseModel):
    dependency_status: Literal["DEGRADED", "HEALTHY"]


class Scenario2MatchingMajorIncidentRequest(BaseModel):
    major_incident_id: str | None = Field(default=None, max_length=128)


class HumanDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    decided_by: str = Field(
        min_length=1,
        max_length=256,
        pattern=r"^[^\r\n]+$",
    )


class RunView(BaseModel):
    run_id: str
    tenant_id: str
    scenario_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class IncidentView(BaseModel):
    incident_id: str
    tenant_id: str
    run_id: str
    site_id: str
    reported_device_id: str
    symptom: str
    status: str
    created_at: datetime
    updated_at: datetime


class EvidenceView(BaseModel):
    evidence_id: str
    tenant_id: str
    run_id: str
    source_type: str
    captured_at: datetime
    entity_ids: list[str]
    payload: dict[str, Any]
    facts: list[str]
    expires_at: datetime | None = None


class ProposalView(BaseModel):
    proposal_id: str
    tenant_id: str
    run_id: str
    incident_id: str
    device_id: str
    diagnosis: str
    action_type: str
    evidence_ids: list[str]
    rationale: str
    status: str
    created_at: datetime
    updated_at: datetime


class ApprovalView(BaseModel):
    approval_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    decision: str
    decided_at: datetime
    decided_by: str


class ExecutedActionView(BaseModel):
    action_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    incident_id: str
    device_id: str
    action_type: str
    executed_at: datetime


class FieldServiceWorkOrderView(BaseModel):
    work_order_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    incident_id: str
    device_id: str
    site_id: str
    attachment_id: str
    switch_id: str
    port_id: str
    created_at: datetime


class RunStateResponse(BaseModel):
    run: RunView
    incidents: list[IncidentView]
    evidence: list[EvidenceView]
    proposals: list[ProposalView]
    approvals: list[ApprovalView]
    executed_actions: list[ExecutedActionView]
    work_orders: list[FieldServiceWorkOrderView]
    latest_event_seq: int


class ServiceIncidentView(BaseModel):
    incident_id: str
    tenant_id: str
    run_id: str
    site_id: str
    service_key: str
    symptom_key: str
    status: str
    created_at: datetime
    updated_at: datetime


class OperationalSignalView(BaseModel):
    signal_id: str
    tenant_id: str
    run_id: str
    source: str
    site_id: str
    service_key: str
    symptom_key: str
    source_ref: str
    received_at: datetime
    safe_payload: dict[str, Any]
    incident_id: str | None = None


class MajorIncidentProposalView(BaseModel):
    proposal_id: str
    tenant_id: str
    run_id: str
    correlation_key: str
    service_key: str
    affected_site_ids: list[str]
    dependency_id: str
    dependency_name: str
    action_type: str
    evidence_ids: list[str]
    summary: str
    rationale: str
    status: str
    created_at: datetime
    updated_at: datetime


class MajorIncidentApprovalView(BaseModel):
    approval_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    decision: str
    decided_at: datetime
    decided_by: str


class MajorIncidentExecutionView(BaseModel):
    execution_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    action_type: str
    major_incident_id: str
    executed_at: datetime


class MajorIncidentView(BaseModel):
    major_incident_id: str
    tenant_id: str
    run_id: str
    proposal_id: str
    correlation_key: str
    service_key: str
    affected_site_ids: list[str]
    dependency_id: str
    dependency_name: str
    summary: str
    status: str
    created_at: datetime


class Scenario2IngestionStateResponse(BaseModel):
    run: RunView
    service_incidents: list[ServiceIncidentView]
    operational_signals: list[OperationalSignalView]
    evidence: list[EvidenceView]
    major_incident_proposals: list[MajorIncidentProposalView]
    major_incident_approvals: list[MajorIncidentApprovalView]
    major_incident_executions: list[MajorIncidentExecutionView]
    major_incidents: list[MajorIncidentView]
    latest_event_seq: int


class Scenario2SignalIngestResponse(BaseModel):
    signal: OperationalSignalView
    service_incident: ServiceIncidentView
    evidence_id: str
    replayed: bool
    event_seq: int | None
    dispatch_queued: bool


class Scenario2SimulatorStepResponse(BaseModel):
    state: Scenario2IngestionStateResponse
    ingested: Scenario2SignalIngestResponse | None
    complete: bool
    next_index: int


class ApplicationEventView(BaseModel):
    event_id: str
    tenant_id: str
    run_id: str
    seq: int
    event_type: str
    occurred_at: datetime
    payload: dict[str, Any]


class TimelineResponse(BaseModel):
    run_id: str
    events: list[ApplicationEventView]
    next_cursor: int


class AgentInvocationResponse(BaseModel):
    run_id: str
    session_id: str
    invocation_id: str | None
    model: str
    run_status: str
    final_answer: str | None
    awaiting_human_decision: bool = False
    pending_proposal_id: str | None = None


class AgentResumeView(BaseModel):
    status: Literal["resumed", "already_resumed", "deferred"]
    invocation_id: str | None = None
    function_call_id: str | None = None
    final_answer: str | None = None
    retryable: bool = False


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalView
    proposal: ProposalView
    incident: IncidentView
    executed_action: ExecutedActionView | None
    work_order: FieldServiceWorkOrderView | None
    replayed: bool
    agent_resume: AgentResumeView | None = None


class Scenario2ApprovalDecisionResponse(BaseModel):
    approval: MajorIncidentApprovalView
    proposal: MajorIncidentProposalView
    execution: MajorIncidentExecutionView | None
    major_incident: MajorIncidentView | None
    replayed: bool
    agent_resume: AgentResumeView | None = None


def _payload(value: object) -> dict[str, Any]:
    data = to_tool_payload(value)
    if not isinstance(data, dict):
        raise TypeError("API payload must serialize to an object")
    return data


def run_state_response(snapshot: RunStateSnapshot) -> RunStateResponse:
    return RunStateResponse(
        run=RunView(**_payload(snapshot.run)),
        incidents=[IncidentView(**_payload(item)) for item in snapshot.incidents],
        evidence=[EvidenceView(**_payload(item)) for item in snapshot.evidence],
        proposals=[ProposalView(**_payload(item)) for item in snapshot.proposals],
        approvals=[ApprovalView(**_payload(item)) for item in snapshot.approvals],
        executed_actions=[
            ExecutedActionView(**_payload(item))
            for item in snapshot.executed_actions
        ],
        work_orders=[
            FieldServiceWorkOrderView(**_payload(item))
            for item in snapshot.work_orders
        ],
        latest_event_seq=snapshot.latest_event_seq,
    )


def scenario2_state_response(
    snapshot: Scenario2IngestionStateSnapshot,
) -> Scenario2IngestionStateResponse:
    return Scenario2IngestionStateResponse(
        run=RunView(**_payload(snapshot.run)),
        service_incidents=[
            ServiceIncidentView(**_payload(item))
            for item in snapshot.service_incidents
        ],
        operational_signals=[
            OperationalSignalView(**_payload(item))
            for item in snapshot.operational_signals
        ],
        evidence=[EvidenceView(**_payload(item)) for item in snapshot.evidence],
        major_incident_proposals=[
            MajorIncidentProposalView(**_payload(item))
            for item in snapshot.major_incident_proposals
        ],
        major_incident_approvals=[
            MajorIncidentApprovalView(**_payload(item))
            for item in snapshot.major_incident_approvals
        ],
        major_incident_executions=[
            MajorIncidentExecutionView(**_payload(item))
            for item in snapshot.major_incident_executions
        ],
        major_incidents=[
            MajorIncidentView(**_payload(item))
            for item in snapshot.major_incidents
        ],
        latest_event_seq=snapshot.latest_event_seq,
    )


def scenario2_signal_response(
    result: Scenario2SignalIngested,
) -> Scenario2SignalIngestResponse:
    return Scenario2SignalIngestResponse(
        signal=OperationalSignalView(**_payload(result.signal)),
        service_incident=ServiceIncidentView(
            **_payload(result.service_incident)
        ),
        evidence_id=result.evidence.evidence_id,
        replayed=result.replayed,
        event_seq=result.event.seq if result.event is not None else None,
        dispatch_queued=result.dispatch is not None,
    )


def scenario2_simulator_response(
    result: Scenario2SimulatorStep,
) -> Scenario2SimulatorStepResponse:
    return Scenario2SimulatorStepResponse(
        state=scenario2_state_response(result.state),
        ingested=(
            scenario2_signal_response(result.ingested)
            if result.ingested is not None
            else None
        ),
        complete=result.complete,
        next_index=result.next_index,
    )


def timeline_response(
    *,
    run_id: str,
    events: tuple[ApplicationEvent, ...],
    after_seq: int,
) -> TimelineResponse:
    views = [
        ApplicationEventView(
            event_id=item.event_id,
            tenant_id=item.tenant_id,
            run_id=item.run_id,
            seq=item.seq,
            event_type=item.event_type.value,
            occurred_at=item.occurred_at,
            payload=item.payload,
        )
        for item in events
    ]
    next_cursor = views[-1].seq if views else after_seq
    return TimelineResponse(
        run_id=run_id,
        events=views,
        next_cursor=next_cursor,
    )


def approval_response(
    result: ApprovalProcessed,
    *,
    agent_resume: AgentResumeView | None = None,
) -> ApprovalDecisionResponse:
    return ApprovalDecisionResponse(
        approval=ApprovalView(**_payload(result.approval)),
        proposal=ProposalView(**_payload(result.proposal)),
        incident=IncidentView(**_payload(result.incident)),
        executed_action=(
            ExecutedActionView(**_payload(result.executed_action))
            if result.executed_action is not None
            else None
        ),
        work_order=(
            FieldServiceWorkOrderView(**_payload(result.work_order))
            if result.work_order is not None
            else None
        ),
        replayed=result.replayed,
        agent_resume=agent_resume,
    )


def scenario2_approval_response(
    result: MajorIncidentDecisionProcessed,
    *,
    agent_resume: AgentResumeView | None = None,
) -> Scenario2ApprovalDecisionResponse:
    return Scenario2ApprovalDecisionResponse(
        approval=MajorIncidentApprovalView(**_payload(result.approval)),
        proposal=MajorIncidentProposalView(**_payload(result.proposal)),
        execution=(
            MajorIncidentExecutionView(**_payload(result.execution))
            if result.execution is not None
            else None
        ),
        major_incident=(
            MajorIncidentView(**_payload(result.major_incident))
            if result.major_incident is not None
            else None
        ),
        replayed=result.replayed,
        agent_resume=agent_resume,
    )


def error_response(error: DomainError) -> ApiErrorResponse:
    return ApiErrorResponse(
        error=ApiErrorBody(
            code=error.code.value,
            message=error.message,
            retryable=error.retryable,
            details=dict(error.details),
        )
    )


__all__ = [
    "AgentInvocationResponse",
    "AgentResumeView",
    "AcceptanceAccessLinkStateRequest",
    "AcceptanceAccessLinkStateResponse",
    "ApiErrorResponse",
    "ApprovalDecisionResponse",
    "HumanDecisionRequest",
    "RunStateResponse",
    "Scenario2ApprovalDecisionResponse",
    "Scenario2DependencyStatusRequest",
    "Scenario2IngestionStateResponse",
    "Scenario2MatchingMajorIncidentRequest",
    "Scenario2SignalIngestRequest",
    "Scenario2SignalIngestResponse",
    "Scenario2SimulatorStepResponse",
    "scenario2_approval_response",
    "scenario2_signal_response",
    "scenario2_simulator_response",
    "scenario2_state_response",
    "TimelineResponse",
    "approval_response",
    "error_response",
    "run_state_response",
    "timeline_response",
]
