from dataclasses import fields

from product_backend.contracts.tools import (
    MODEL_VISIBLE_TOOL_NAMES,
    GetDeviceRequest,
    GetSiteHealthRequest,
    ProposeFieldVisitRequest,
    RunDiagnosticRequest,
    SearchIncidentsRequest,
    SearchKbRequest,
    ToolCallContext,
)
from product_backend.domain.enums import IncidentStatus, ProposalStatus, RunStatus
from product_backend.domain.errors import ErrorCode
from product_backend.domain.transitions import (
    PROPOSAL_TRANSITIONS,
    RUN_TRANSITIONS,
    SCENARIO1_INCIDENT_TRANSITIONS,
    can_transition,
)


MODEL_REQUESTS = (
    GetDeviceRequest,
    GetSiteHealthRequest,
    RunDiagnosticRequest,
    SearchIncidentsRequest,
    SearchKbRequest,
    ProposeFieldVisitRequest,
)


def field_names(model: type) -> set[str]:
    return {item.name for item in fields(model)}


def test_scenario1_tool_surface_is_exactly_the_frozen_six_tools() -> None:
    assert MODEL_VISIBLE_TOOL_NAMES == (
        "get_device",
        "get_site_health",
        "run_diagnostic",
        "search_incidents",
        "search_kb",
        "propose_field_visit",
    )


def test_model_visible_requests_cannot_choose_tenant_or_run_context() -> None:
    for request in MODEL_REQUESTS:
        assert "tenant_id" not in field_names(request)
        assert "run_id" not in field_names(request)

    assert field_names(ToolCallContext) == {"tenant_id", "run_id"}


def test_field_visit_request_does_not_expose_server_derived_dispatch_fields() -> None:
    names = field_names(ProposeFieldVisitRequest)
    assert names == {
        "incident_id",
        "device_id",
        "diagnosis",
        "evidence_ids",
        "rationale",
    }
    assert not names.intersection({"queue", "address", "engineer", "work_type"})


def test_phase2_error_codes_required_by_contract_are_preserved() -> None:
    assert ErrorCode.DEVICE_NOT_FOUND.value == "DEVICE_NOT_FOUND"
    assert ErrorCode.ATTACHMENT_NOT_FOUND.value == "ATTACHMENT_NOT_FOUND"
    assert ErrorCode.DIAGNOSTIC_UNAVAILABLE.value == "DIAGNOSTIC_UNAVAILABLE"
    assert ErrorCode.UPSTREAM_UNAVAILABLE.value == "UPSTREAM_UNAVAILABLE"
    assert (
        ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE.value
        == "INSUFFICIENT_OR_INVALID_EVIDENCE"
    )


def test_proposal_transition_contract_has_no_post_terminal_transition() -> None:
    assert can_transition(
        PROPOSAL_TRANSITIONS,
        ProposalStatus.PENDING_APPROVAL,
        ProposalStatus.EXECUTED,
    )
    assert PROPOSAL_TRANSITIONS[ProposalStatus.EXECUTED] == frozenset()
    assert PROPOSAL_TRANSITIONS[ProposalStatus.REJECTED] == frozenset()
    assert PROPOSAL_TRANSITIONS[ProposalStatus.STALE] == frozenset()


def test_scenario1_incident_cannot_be_marked_resolved_by_field_visit_flow() -> None:
    assert can_transition(
        SCENARIO1_INCIDENT_TRANSITIONS,
        IncidentStatus.OPEN,
        IncidentStatus.ESCALATED,
    )
    assert not can_transition(
        SCENARIO1_INCIDENT_TRANSITIONS,
        IncidentStatus.OPEN,
        IncidentStatus.RESOLVED,
    )
    assert not can_transition(
        SCENARIO1_INCIDENT_TRANSITIONS,
        IncidentStatus.ESCALATED,
        IncidentStatus.RESOLVED,
    )


def test_run_can_pause_for_human_decision_and_resume() -> None:
    assert can_transition(RUN_TRANSITIONS, RunStatus.CREATED, RunStatus.ACTIVE)
    assert can_transition(
        RUN_TRANSITIONS, RunStatus.ACTIVE, RunStatus.WAITING_APPROVAL
    )
    assert can_transition(
        RUN_TRANSITIONS, RunStatus.WAITING_APPROVAL, RunStatus.ACTIVE
    )
