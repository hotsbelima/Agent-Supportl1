"""Deterministic authoritative provider source for canonical Scenario 3."""

from __future__ import annotations

from product_backend.domain.enums import HealthState
from product_backend.domain.scenario2 import (
    DependencyKind,
    ExternalDependencyStatusSnapshot,
    ServiceDependencyMappingSnapshot,
)

from .scenario3_fixture import SERVICE_KEY


ACMEPAY_DEPENDENCY_ID = "DEP-ACMEPAY-PAYMENTS"
ACMEPAY_NAME = "AcmePay"


class Scenario3ProviderSources:
    """Return provider observations only; Product/agent owns interpretation."""

    async def get_service_dependencies(
        self,
        *,
        tenant_id: str,
        run_id: str,
        service_key: str,
    ) -> tuple[ServiceDependencyMappingSnapshot, ...]:
        del tenant_id, run_id
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
        del tenant_id, run_id
        if dependency_id != ACMEPAY_DEPENDENCY_ID:
            return None
        return ExternalDependencyStatusSnapshot(
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            dependency_name=ACMEPAY_NAME,
            status=HealthState.HEALTHY,
            status_detail="operating_normally",
        )


__all__ = [
    "ACMEPAY_DEPENDENCY_ID",
    "ACMEPAY_NAME",
    "Scenario3ProviderSources",
]
