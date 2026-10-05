"""Scenario 2 model-visible tool contracts.

These are schema contracts only in Phase 7B. Live ADK wiring belongs to Phase 7D.
Trusted tenant/run context remains outside model-visible arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from product_backend.domain.errors import DomainError
from product_backend.domain.models import Evidence
from product_backend.domain.scenario2 import (
    ExternalDependencyStatusSnapshot,
    LocalServiceHealthSnapshot,
    MajorIncidentProposal,
    MajorIncidentSearchSnapshot,
    ServiceDependencyMappingSnapshot,
)


@dataclass(frozen=True, slots=True)
class GetLocalServiceHealthRequest:
    site_id: str
    service_key: str


@dataclass(frozen=True, slots=True)
class GetServiceDependenciesRequest:
    service_key: str


@dataclass(frozen=True, slots=True)
class GetExternalDependencyStatusRequest:
    dependency_id: str


@dataclass(frozen=True, slots=True)
class SearchMajorIncidentsRequest:
    correlation_key: str
    dependency_id: str


@dataclass(frozen=True, slots=True)
class ProposeMajorIncidentRequest:
    correlation_key: str
    affected_site_ids: tuple[str, ...]
    dependency_id: str
    evidence_ids: tuple[str, ...]
    summary: str
    rationale: str


@dataclass(frozen=True, slots=True)
class GetLocalServiceHealthSuccess:
    ok: Literal[True]
    site_id: str
    service_key: str
    health: LocalServiceHealthSnapshot
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class GetServiceDependenciesSuccess:
    ok: Literal[True]
    service_key: str
    mappings: tuple[ServiceDependencyMappingSnapshot, ...]
    evidence: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class GetExternalDependencyStatusSuccess:
    ok: Literal[True]
    dependency_id: str
    status: ExternalDependencyStatusSnapshot
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class SearchMajorIncidentsSuccess:
    ok: Literal[True]
    correlation_key: str
    dependency_id: str
    snapshot: MajorIncidentSearchSnapshot
    evidence: Evidence


@dataclass(frozen=True, slots=True)
class ProposeMajorIncidentSuccess:
    ok: Literal[True]
    proposal: MajorIncidentProposal


@dataclass(frozen=True, slots=True)
class Scenario2ToolFailure:
    ok: Literal[False]
    error: DomainError


GetLocalServiceHealthResult: TypeAlias = (
    GetLocalServiceHealthSuccess | Scenario2ToolFailure
)
GetServiceDependenciesResult: TypeAlias = (
    GetServiceDependenciesSuccess | Scenario2ToolFailure
)
GetExternalDependencyStatusResult: TypeAlias = (
    GetExternalDependencyStatusSuccess | Scenario2ToolFailure
)
SearchMajorIncidentsResult: TypeAlias = (
    SearchMajorIncidentsSuccess | Scenario2ToolFailure
)
ProposeMajorIncidentResult: TypeAlias = (
    ProposeMajorIncidentSuccess | Scenario2ToolFailure
)


SCENARIO2_MODEL_VISIBLE_TOOL_NAMES = (
    "get_local_service_health",
    "get_service_dependencies",
    "get_external_dependency_status",
    "search_major_incidents",
    "propose_major_incident",
)


__all__ = [
    "GetExternalDependencyStatusRequest",
    "GetExternalDependencyStatusResult",
    "GetExternalDependencyStatusSuccess",
    "GetLocalServiceHealthRequest",
    "GetLocalServiceHealthResult",
    "GetLocalServiceHealthSuccess",
    "GetServiceDependenciesRequest",
    "GetServiceDependenciesResult",
    "GetServiceDependenciesSuccess",
    "ProposeMajorIncidentRequest",
    "ProposeMajorIncidentResult",
    "ProposeMajorIncidentSuccess",
    "SCENARIO2_MODEL_VISIBLE_TOOL_NAMES",
    "Scenario2ToolFailure",
    "SearchMajorIncidentsRequest",
    "SearchMajorIncidentsResult",
    "SearchMajorIncidentsSuccess",
]
