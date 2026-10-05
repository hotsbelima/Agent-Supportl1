"""Canonical deterministic Scenario 2 world for Phase 7B.

This file defines fixture truth and exact incoming templates only. It is not
wired to Product ingestion or ADK in Phase 7B.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from product_backend.domain.enums import HealthState
from product_backend.domain.scenario2 import (
    DependencyKind,
    ExternalDependencyStatusSnapshot,
    LocalServiceHealthSnapshot,
    MajorIncidentSearchSnapshot,
    Scenario2SignalSource,
    ServiceDependencyMappingSnapshot,
)


SCENARIO2_ID = "scenario-2"
SERVICE_KEY = "payment_gateway"
CORRELATION_KEY = "payment_gateway_timeout"

SITE_KZN = "SITE-KZN-017"
SITE_SAM = "SITE-SAM-024"

INCIDENT_KZN = "INC-S2-KZN-001"
INCIDENT_SAM = "INC-S2-SAM-001"

SIGNAL_1_ID = "SIG-S2-001"
SIGNAL_2_ID = "SIG-S2-002"
SIGNAL_3_ID = "SIG-S2-003"

ACMEPAY_DEPENDENCY_ID = "DEP-ACMEPAY-PAYMENTS"
ACMEPAY_NAME = "AcmePay"

STALE_MATCHING_MAJOR_INCIDENT_ID = "MI-ACMEPAY-EXISTING-001"


@dataclass(frozen=True, slots=True)
class Scenario2SignalTemplate:
    signal_id: str
    source: Scenario2SignalSource
    site_id: str
    service_key: str
    symptom_key: str
    source_ref: str
    incident_id: str
    safe_payload: dict[str, Any]


CANONICAL_SIGNAL_SEQUENCE = (
    Scenario2SignalTemplate(
        signal_id=SIGNAL_1_ID,
        source=Scenario2SignalSource.MONITORING,
        site_id=SITE_KZN,
        service_key=SERVICE_KEY,
        symptom_key=CORRELATION_KEY,
        source_ref="MON-ALERT-KZN-901",
        incident_id=INCIDENT_KZN,
        safe_payload={
            "kind": "payment_timeout_rate",
            "service_key": SERVICE_KEY,
            "severity": "warning",
        },
    ),
    Scenario2SignalTemplate(
        signal_id=SIGNAL_2_ID,
        source=Scenario2SignalSource.ITSM,
        site_id=SITE_KZN,
        service_key=SERVICE_KEY,
        symptom_key=CORRELATION_KEY,
        source_ref="TICKET-KZN-5521",
        incident_id=INCIDENT_KZN,
        safe_payload={
            "kind": "user_ticket",
            "service_key": SERVICE_KEY,
            "impact": "payment_attempts_timing_out",
        },
    ),
    Scenario2SignalTemplate(
        signal_id=SIGNAL_3_ID,
        source=Scenario2SignalSource.MONITORING,
        site_id=SITE_SAM,
        service_key=SERVICE_KEY,
        symptom_key=CORRELATION_KEY,
        source_ref="MON-ALERT-SAM-337",
        incident_id=INCIDENT_SAM,
        safe_payload={
            "kind": "payment_timeout_rate",
            "service_key": SERVICE_KEY,
            "severity": "warning",
        },
    ),
)


class Scenario2FixtureWorld:
    """Deterministic hidden truth with narrow stale-path state transitions."""

    def __init__(self) -> None:
        self._dependency_status = HealthState.DEGRADED
        self._open_major_incident_ids: tuple[str, ...] = ()

    def signal_sequence(self) -> tuple[Scenario2SignalTemplate, ...]:
        return CANONICAL_SIGNAL_SEQUENCE

    def local_service_health(
        self,
        *,
        site_id: str,
        service_key: str,
    ) -> LocalServiceHealthSnapshot | None:
        if service_key != SERVICE_KEY or site_id not in {SITE_KZN, SITE_SAM}:
            return None
        return LocalServiceHealthSnapshot(
            site_id=site_id,
            service_key=service_key,
            network_health=HealthState.HEALTHY,
            local_service_health=HealthState.HEALTHY,
        )

    def dependency_mapping(
        self,
        *,
        service_key: str,
    ) -> ServiceDependencyMappingSnapshot | None:
        if service_key != SERVICE_KEY:
            return None
        return ServiceDependencyMappingSnapshot(
            service_key=SERVICE_KEY,
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            dependency_name=ACMEPAY_NAME,
            dependency_kind=DependencyKind.EXTERNAL_PROVIDER,
        )

    def dependency_status(
        self,
        *,
        dependency_id: str,
    ) -> ExternalDependencyStatusSnapshot | None:
        if dependency_id != ACMEPAY_DEPENDENCY_ID:
            return None
        return ExternalDependencyStatusSnapshot(
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            dependency_name=ACMEPAY_NAME,
            status=self._dependency_status,
            status_detail=(
                "elevated_timeout_rate"
                if self._dependency_status is HealthState.DEGRADED
                else "operating_normally"
            ),
        )

    def major_incident_search(
        self,
        *,
        correlation_key: str,
        dependency_id: str,
    ) -> MajorIncidentSearchSnapshot:
        open_ids: tuple[str, ...] = ()
        if (
            correlation_key == CORRELATION_KEY
            and dependency_id == ACMEPAY_DEPENDENCY_ID
        ):
            open_ids = self._open_major_incident_ids
        return MajorIncidentSearchSnapshot(
            correlation_key=correlation_key,
            dependency_id=dependency_id,
            open_major_incident_ids=open_ids,
        )

    def recover_acmepay(self) -> None:
        """Controlled fixture transition reserved for later stale acceptance."""
        self._dependency_status = HealthState.HEALTHY

    def restore_acmepay_degraded(self) -> None:
        self._dependency_status = HealthState.DEGRADED

    def inject_matching_major_incident(self) -> None:
        """Controlled duplicate-prevention transition for later stale acceptance."""
        self._open_major_incident_ids = (STALE_MATCHING_MAJOR_INCIDENT_ID,)

    def clear_matching_major_incident(self) -> None:
        self._open_major_incident_ids = ()


__all__ = [
    "ACMEPAY_DEPENDENCY_ID",
    "ACMEPAY_NAME",
    "CANONICAL_SIGNAL_SEQUENCE",
    "CORRELATION_KEY",
    "INCIDENT_KZN",
    "INCIDENT_SAM",
    "SCENARIO2_ID",
    "SERVICE_KEY",
    "SIGNAL_1_ID",
    "SIGNAL_2_ID",
    "SIGNAL_3_ID",
    "SITE_KZN",
    "SITE_SAM",
    "STALE_MATCHING_MAJOR_INCIDENT_ID",
    "Scenario2FixtureWorld",
    "Scenario2SignalTemplate",
]
