"""Deterministic Scenario 2 fact simulator for Phase 7C.

The simulator only chooses the next canonical input fact. It never decides that a
Major Incident exists and never invokes ADK.
"""

from __future__ import annotations

from product_backend.application.results import OperationFailure
from product_backend.application.scenario2_ingestion import (
    Scenario2SignalIngestionService,
)
from product_backend.application.scenario2_state import Scenario2StateService
from product_backend.contracts.scenario2_ingestion import (
    Scenario2SignalInput,
    Scenario2SimulatorStep,
)
from product_backend.domain.errors import DomainError, ErrorCode

from .scenario2_fixture import CANONICAL_SIGNAL_SEQUENCE


def _canonical_progress(signals):
    by_identity = {
        (signal.source, signal.source_ref): signal
        for signal in signals
    }
    for index, template in enumerate(CANONICAL_SIGNAL_SEQUENCE):
        existing = by_identity.get((template.source, template.source_ref))
        if existing is None:
            return index, None
        if (
            existing.site_id != template.site_id
            or existing.service_key != template.service_key
            or existing.symptom_key != template.symptom_key
            or existing.safe_payload != template.safe_payload
        ):
            return index, OperationFailure(
                ok=False,
                error=DomainError(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message=(
                        "Persisted fact conflicts with the canonical "
                        "Scenario 2 simulator sequence."
                    ),
                    details=(
                        ("reason", "canonical_signal_identity_conflict"),
                        ("source_ref", template.source_ref),
                    ),
                ),
            )
    return len(CANONICAL_SIGNAL_SEQUENCE), None


class Scenario2SimulatorService:
    def __init__(
        self,
        *,
        state_service: Scenario2StateService,
        ingestion_service: Scenario2SignalIngestionService,
    ) -> None:
        self._state_service = state_service
        self._ingestion_service = ingestion_service

    async def next(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> Scenario2SimulatorStep | OperationFailure:
        state = await self._state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if state is None:
            return OperationFailure(
                ok=False,
                error=DomainError(
                    code=ErrorCode.CONTEXT_MISMATCH,
                    message="Scenario 2 run was not found.",
                    details=(("reason", "run_not_found"),),
                ),
            )

        next_index, conflict = _canonical_progress(
            state.operational_signals
        )
        if conflict is not None:
            return conflict

        if next_index >= len(CANONICAL_SIGNAL_SEQUENCE):
            return Scenario2SimulatorStep(
                state=state,
                ingested=None,
                complete=True,
                next_index=next_index,
            )

        template = CANONICAL_SIGNAL_SEQUENCE[next_index]
        ingested = await self._ingestion_service.ingest(
            tenant_id=tenant_id,
            run_id=run_id,
            signal_input=Scenario2SignalInput(
                source=template.source,
                site_id=template.site_id,
                service_key=template.service_key,
                symptom_key=template.symptom_key,
                source_ref=template.source_ref,
                safe_payload=dict(template.safe_payload),
                signal_id_hint=template.signal_id,
                incident_id_hint=template.incident_id,
            ),
        )
        if isinstance(ingested, OperationFailure):
            return ingested

        refreshed = await self._state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if refreshed is None:
            return OperationFailure(
                ok=False,
                error=DomainError(
                    code=ErrorCode.CONTEXT_MISMATCH,
                    message="Scenario 2 state disappeared after ingestion.",
                    details=(("reason", "state_missing_after_ingestion"),),
                ),
            )

        next_after_ingest, conflict = _canonical_progress(
            refreshed.operational_signals
        )
        if conflict is not None:
            return conflict

        return Scenario2SimulatorStep(
            state=refreshed,
            ingested=ingested,
            complete=next_after_ingest >= len(CANONICAL_SIGNAL_SEQUENCE),
            next_index=next_after_ingest,
        )


__all__ = ["Scenario2SimulatorService"]
