"""Canonical deterministic Scenario 3 Product/source fixture.

Scenario 3 reuses the Scenario 1 local/device world while adding only the
provider observations required to disconfirm the initial upstream hypothesis.
The source adapter returns observations, never a precomputed diagnosis/replan.
"""

from __future__ import annotations

from product_backend.contracts.run_state import Scenario1Bootstrap
from product_backend.domain.enums import HealthState
from product_backend.domain.scenario2 import (
    DependencyKind,
    ExternalDependencyStatusSnapshot,
    ServiceDependencyMappingSnapshot,
)

from .scenario1_fixture import Scenario1FixtureSources


SCENARIO_ID = "scenario-3"
INCIDENT_ID = "INC-S3-KZN-001"
SITE_ID = "SITE-KZN-017"
AFFECTED_DEVICE_ID = "POS-KZN17-02"

SERVICE_KEY = "payment_gateway"
SYMPTOM_KEY = "payment_gateway_timeout"

ACMEPAY_DEPENDENCY_ID = "DEP-ACMEPAY-PAYMENTS"
ACMEPAY_NAME = "AcmePay"

INCIDENT_SYMPTOM = "Payment attempts time out on this terminal."


class Scenario3FixtureSources(Scenario1FixtureSources):
    """Scenario 1 local sources plus Scenario 3 provider observations."""

    def bootstrap(self) -> Scenario1Bootstrap:
        return Scenario1Bootstrap(
            scenario_id=SCENARIO_ID,
            incident_id=INCIDENT_ID,
            site_id=SITE_ID,
            reported_device_id=AFFECTED_DEVICE_ID,
            symptom=INCIDENT_SYMPTOM,
            service_key=SERVICE_KEY,
            symptom_key=SYMPTOM_KEY,
        )

    async def get_service_dependencies(
        self,
        *,
        tenant_id: str,
        run_id: str,
        service_key: str,
    ) -> tuple[ServiceDependencyMappingSnapshot, ...]:
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
    "AFFECTED_DEVICE_ID",
    "INCIDENT_ID",
    "INCIDENT_SYMPTOM",
    "SCENARIO_ID",
    "SERVICE_KEY",
    "SITE_ID",
    "SYMPTOM_KEY",
    "Scenario3FixtureSources",
]
