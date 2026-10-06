"""Scenario 3 Product-facing provider-read contracts.

Phase 8C1 intentionally exposes only the two provider-domain reads required to
test the initial upstream hypothesis. Native ADK wrappers are added in Phase
8C2; trusted tenant/run context never belongs in model-visible arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from product_backend.domain.errors import DomainError
from product_backend.domain.models import Evidence
from product_backend.domain.scenario2 import (
    ExternalDependencyStatusSnapshot,
    ServiceDependencyMappingSnapshot,
)


@dataclass(frozen=True, slots=True)
class GetServiceDependenciesRequest:
    service_key: str


@dataclass(frozen=True, slots=True)
class GetExternalDependencyStatusRequest:
    dependency_id: str


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
class Scenario3ProviderToolFailure:
    ok: Literal[False]
    error: DomainError


GetServiceDependenciesResult: TypeAlias = (
    GetServiceDependenciesSuccess | Scenario3ProviderToolFailure
)
GetExternalDependencyStatusResult: TypeAlias = (
    GetExternalDependencyStatusSuccess | Scenario3ProviderToolFailure
)


__all__ = [
    "GetExternalDependencyStatusRequest",
    "GetExternalDependencyStatusResult",
    "GetExternalDependencyStatusSuccess",
    "GetServiceDependenciesRequest",
    "GetServiceDependenciesResult",
    "GetServiceDependenciesSuccess",
    "Scenario3ProviderToolFailure",
]
