import ast
from dataclasses import fields
from inspect import signature
from pathlib import Path

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
from product_backend.ports.source_systems import CmdbPort, ItsmPort, KnowledgeBasePort, MonitoringPort
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


def test_source_system_ports_are_run_scoped() -> None:
    methods = (
        CmdbPort.get_device,
        MonitoringPort.get_site_health,
        MonitoringPort.run_diagnostic,
        ItsmPort.get_incident,
        ItsmPort.search_incidents,
        KnowledgeBasePort.search,
    )
    for method in methods:
        params = signature(method).parameters
        assert "tenant_id" in params
        assert "run_id" in params


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_pure_domain_does_not_depend_on_framework_application_or_ports() -> None:
    forbidden_prefixes = (
        "google",
        "fastapi",
        "sqlalchemy",
        "psycopg",
        "product_backend.adapters",
        "product_backend.application",
        "product_backend.contracts",
        "product_backend.ports",
    )
    for path in Path("product_backend/domain").glob("*.py"):
        for module in _imported_modules(path):
            assert not module.startswith(forbidden_prefixes), (path, module)


def test_model_facing_adapter_does_not_reach_repositories_or_source_ports_directly() -> None:
    modules = _imported_modules(Path("product_backend/adapters/tool_adapters.py"))
    assert "product_backend.ports.repositories" not in modules
    assert "product_backend.ports.source_systems" not in modules
