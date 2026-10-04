"""Scenario 1 model-visible tool contracts.

The request dataclasses contain only fields the model is allowed to choose.
Tenant/run context is injected by the application and is deliberately absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from product_backend.domain.enums import (
    ActionType,
    DiagnosisCode,
    DiagnosticType,
    IncidentSearchScope,
)
from product_backend.domain.errors import DomainError
from product_backend.domain.models import (
    AccessLinkDiagnosticSnapshot,
    ActionProposal,
    DeviceTopology,
    Evidence,
    IncidentSearchSnapshot,
    KbArticle,
    SiteHealthSnapshot,
)


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    """Trusted context injected outside the model-visible schema."""

    tenant_id: str
    run_id: str


@dataclass(frozen=True, slots=True)
class GetDeviceRequest:
    device_id: str


@dataclass(frozen=True, slots=True)
class GetSiteHealthRequest:
    site_id: str


@dataclass(frozen=True, slots=True)
class RunDiagnosticRequest:
    diagnostic_type: DiagnosticType
    target_id: str


@dataclass(frozen=True, slots=True)
class SearchIncidentsRequest:
    scope: IncidentSearchScope
    entity_id: str


@dataclass(frozen=True, slots=True)
class SearchKbRequest:
    query: str


@dataclass(frozen=True, slots=True)
class ProposeFieldVisitRequest:
    incident_id: str
    device_id: str
    diagnosis: DiagnosisCode
    evidence_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class GetDeviceSuccess:
    ok: Literal[True]
    device_id: str
    attachment_id: str
    site_id: str
    device_type: str
    topology: DeviceTopology
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class GetSiteHealthSuccess:
    ok: Literal[True]
    site_id: str
    health: SiteHealthSnapshot
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class RunDiagnosticSuccess:
    ok: Literal[True]
    diagnostic_type: DiagnosticType
    target_id: str
    attachment_id: str
    diagnostic: str
    observed_state: str
    snapshot: AccessLinkDiagnosticSnapshot
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class SearchIncidentsSuccess:
    ok: Literal[True]
    scope: IncidentSearchScope
    entity_id: str
    snapshot: IncidentSearchSnapshot
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class SearchKbSuccess:
    ok: Literal[True]
    query: str
    articles: tuple[KbArticle, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class ProposeFieldVisitSuccess:
    ok: Literal[True]
    proposal: ActionProposal


@dataclass(frozen=True, slots=True)
class ToolFailure:
    ok: Literal[False]
    error: DomainError


GetDeviceResult: TypeAlias = GetDeviceSuccess | ToolFailure
GetSiteHealthResult: TypeAlias = GetSiteHealthSuccess | ToolFailure
RunDiagnosticResult: TypeAlias = RunDiagnosticSuccess | ToolFailure
SearchIncidentsResult: TypeAlias = SearchIncidentsSuccess | ToolFailure
SearchKbResult: TypeAlias = SearchKbSuccess | ToolFailure
ProposeFieldVisitResult: TypeAlias = ProposeFieldVisitSuccess | ToolFailure


MODEL_VISIBLE_TOOL_NAMES = (
    "get_device",
    "get_site_health",
    "run_diagnostic",
    "search_incidents",
    "search_kb",
    "propose_field_visit",
)

# `propose_field_visit` itself fixes the action type. The model does not select
# queue, address, engineer or work type. The returned proposal must carry the
# canonical action type after deterministic validation.
PROPOSE_FIELD_VISIT_ACTION = ActionType.ONSITE_FIELD_VISIT
