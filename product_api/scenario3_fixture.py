"""Canonical Scenario 3 fixture/bootstrap for Phase 8C1.

Local device/topology source behavior is intentionally reused from Scenario 1.
Scenario 3 adds only safe service/symptom bootstrap context here; provider truth
is kept in the separate provider source adapter.
"""

from __future__ import annotations

from product_backend.contracts.run_state import Scenario1Bootstrap

from .scenario1_fixture import (
    AFFECTED_DEVICE_ID,
    ATTACHMENT_ID,
    PEER_DEVICE_ID,
    PORT_ID,
    SITE_ID,
    SWITCH_ID,
    Scenario1FixtureSources,
)


SCENARIO_ID = "scenario-3"
INCIDENT_ID = "INC-S3-KZN-001"
SERVICE_KEY = "payment_gateway"
SYMPTOM_KEY = "payment_gateway_timeout"
INCIDENT_SYMPTOM = "Single payment terminal reports payment gateway timeouts."


class Scenario3FixtureSources(Scenario1FixtureSources):
    """Scenario 1 local fixtures plus Scenario 3 bootstrap identity."""

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


__all__ = [
    "AFFECTED_DEVICE_ID",
    "ATTACHMENT_ID",
    "INCIDENT_ID",
    "INCIDENT_SYMPTOM",
    "PEER_DEVICE_ID",
    "PORT_ID",
    "SCENARIO_ID",
    "SERVICE_KEY",
    "SITE_ID",
    "SWITCH_ID",
    "SYMPTOM_KEY",
    "Scenario3FixtureSources",
]
