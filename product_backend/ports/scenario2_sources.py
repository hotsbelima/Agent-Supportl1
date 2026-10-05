"""Provider-neutral read ports required by Scenario 2.

Phase 7B defines interfaces only. Deterministic fixture adapters and ADK wrappers
are wired in later checkpoints.
"""

from __future__ import annotations

from typing import Protocol

from product_backend.domain.scenario2 import (
    ExternalDependencyStatusSnapshot,
    LocalServiceHealthSnapshot,
    MajorIncidentSearchSnapshot,
    ServiceDependencyMappingSnapshot,
)


class LocalServiceHealthPort(Protocol):
    async def get_local_service_health(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
        service_key: str,
    ) -> LocalServiceHealthSnapshot | None: ...


class ServiceDependencyPort(Protocol):
    async def get_service_dependencies(
        self,
        *,
        tenant_id: str,
        run_id: str,
        service_key: str,
    ) -> tuple[ServiceDependencyMappingSnapshot, ...]: ...


class ExternalDependencyStatusPort(Protocol):
    async def get_external_dependency_status(
        self,
        *,
        tenant_id: str,
        run_id: str,
        dependency_id: str,
    ) -> ExternalDependencyStatusSnapshot | None: ...


class MajorIncidentDirectoryPort(Protocol):
    async def search_major_incidents(
        self,
        *,
        tenant_id: str,
        run_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ) -> MajorIncidentSearchSnapshot: ...


__all__ = [
    "ExternalDependencyStatusPort",
    "LocalServiceHealthPort",
    "MajorIncidentDirectoryPort",
    "ServiceDependencyPort",
]
