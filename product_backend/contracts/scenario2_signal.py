"""Validation contract for persisted Scenario 2 operational signals."""

from __future__ import annotations

from datetime import timedelta

from product_backend.domain.scenario2 import OperationalSignal

from .events import validate_safe_event_payload


def validate_operational_signal(signal: OperationalSignal) -> None:
    required = {
        "signal_id": signal.signal_id,
        "tenant_id": signal.tenant_id,
        "run_id": signal.run_id,
        "site_id": signal.site_id,
        "service_key": signal.service_key,
        "symptom_key": signal.symptom_key,
        "source_ref": signal.source_ref,
    }
    for name, value in required.items():
        if not value.strip():
            raise ValueError(f"{name} is required")

    if signal.incident_id is not None and not signal.incident_id.strip():
        raise ValueError("incident_id must be non-empty when present")

    if (
        signal.received_at.tzinfo is None
        or signal.received_at.utcoffset() is None
        or signal.received_at.utcoffset() != timedelta(0)
    ):
        raise ValueError("received_at must be an aware server UTC timestamp")

    validate_safe_event_payload(signal.safe_payload)


__all__ = ["validate_operational_signal"]
