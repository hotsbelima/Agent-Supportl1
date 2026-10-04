"""Stable HTTP schemas for the Phase 4C product API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from product_backend.contracts.events import ApplicationEvent
from product_backend.contracts.run_state import RunStateSnapshot
from product_backend.contracts.serialization import to_tool_payload
from product_backend.application.results import ApprovalProcessed
from product_backend.domain.errors import DomainError


class ApiErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, str] = Field(default_factory=dict)


class ApiErrorResponse(BaseModel):
    error: ApiErrorBody


class HumanDecisionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    decided_by: str = Field(min_length=1, max_length=256)


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


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalView
    proposal: ProposalView
    incident: IncidentView
    executed_action: ExecutedActionView | None
    work_order: FieldServiceWorkOrderView | None
    replayed: bool


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


def approval_response(result: ApprovalProcessed) -> ApprovalDecisionResponse:
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
    "ApiErrorResponse",
    "ApprovalDecisionResponse",
    "HumanDecisionRequest",
    "RunStateResponse",
    "TimelineResponse",
    "approval_response",
    "error_response",
    "run_state_response",
    "timeline_response",
]
