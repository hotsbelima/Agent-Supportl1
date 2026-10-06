"""Scenario 2 deterministic source adapter backed by persisted Product state.

Phase 7D exposes these provider-neutral reads only through typed Product/ADK
tool wrappers; hidden fixture truth never bypasses that boundary.
"""

from __future__ import annotations

from product_backend.application.scenario2_state import Scenario2StateService
from product_backend.domain.enums import HealthState
from product_backend.domain.scenario2 import (
    DependencyKind,
    ExternalDependencyStatusSnapshot,
    LocalServiceHealthSnapshot,
    MajorIncidentSearchSnapshot,
    ServiceDependencyMappingSnapshot,
)

from .scenario2_fixture import (
    ACMEPAY_DEPENDENCY_ID,
    ACMEPAY_NAME,
    CORRELATION_KEY,
    SERVICE_KEY,
    SITE_KZN,
    SITE_SAM,
)


class PersistedScenario2FixtureSources:
    def __init__(self, state_service: Scenario2StateService) -> None:
        self._state_service = state_service

    async def get_local_service_health(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
        service_key: str,
    ) -> LocalServiceHealthSnapshot | None:
        state = await self._state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if state is None:
            return None
        if service_key != SERVICE_KEY or site_id not in {SITE_KZN, SITE_SAM}:
            return None
        return LocalServiceHealthSnapshot(
            site_id=site_id,
            service_key=service_key,
            network_health=HealthState.HEALTHY,
            local_service_health=HealthState.HEALTHY,
        )

    async def get_service_dependencies(
        self,
        *,
        tenant_id: str,
        run_id: str,
        service_key: str,
    ) -> tuple[ServiceDependencyMappingSnapshot, ...]:
        state = await self._state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if state is None:
            raise RuntimeError("Scenario 2 Product state is unavailable")
        if service_key != SERVICE_KEY:
            return ()
        return (
            ServiceDependencyMappingSnapshot(
                service_key=SERVICE_KEY,
                dependency_id=ACMEPAY_DEPENDENCY_ID,
                dependency_name=ACMEPAY_NAME,
                dependency_kind=DependencyKind.EXTERNAL_PROVIDER,
            ),
        )

    async def get_external_dependency_status(
        self,
        *,
        tenant_id: str,
        run_id: str,
        dependency_id: str,
    ) -> ExternalDependencyStatusSnapshot | None:
        state = await self._state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if state is None or dependency_id != ACMEPAY_DEPENDENCY_ID:
            return None
        status = state.fixture_state.dependency_status
        return ExternalDependencyStatusSnapshot(
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            dependency_name=ACMEPAY_NAME,
            status=status,
            status_detail=(
                "elevated_timeout_rate"
                if status is HealthState.DEGRADED
                else "operating_normally"
            ),
        )

    async def search_major_incidents(
        self,
        *,
        tenant_id: str,
        run_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ) -> MajorIncidentSearchSnapshot:
        state = await self._state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if state is None:
            raise RuntimeError("Scenario 2 Product state is unavailable")

        open_ids = {
            item.major_incident_id
            for item in state.major_incidents
            if (
                item.service_key == service_key
                and item.correlation_key == correlation_key
                and item.dependency_id == dependency_id
            )
        }
        if (
            service_key == SERVICE_KEY
            and correlation_key == CORRELATION_KEY
            and dependency_id == ACMEPAY_DEPENDENCY_ID
            and state.fixture_state.matching_major_incident_id is not None
        ):
            open_ids.add(state.fixture_state.matching_major_incident_id)

        return MajorIncidentSearchSnapshot(
            service_key=service_key,
            correlation_key=correlation_key,
            dependency_id=dependency_id,
            open_major_incident_ids=tuple(sorted(open_ids)),
        )


__all__ = ["PersistedScenario2FixtureSources"]
