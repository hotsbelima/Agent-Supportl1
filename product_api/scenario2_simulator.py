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

        persisted_identities = {
            (signal.source, signal.source_ref)
            for signal in state.operational_signals
        }
        next_index = next(
            (
                index
                for index, template in enumerate(CANONICAL_SIGNAL_SEQUENCE)
                if (template.source, template.source_ref)
                not in persisted_identities
            ),
            len(CANONICAL_SIGNAL_SEQUENCE),
        )

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

        refreshed_identities = {
            (signal.source, signal.source_ref)
            for signal in refreshed.operational_signals
        }
        next_after_ingest = next(
            (
                index
                for index, candidate in enumerate(CANONICAL_SIGNAL_SEQUENCE)
                if (candidate.source, candidate.source_ref)
                not in refreshed_identities
            ),
            len(CANONICAL_SIGNAL_SEQUENCE),
        )

        return Scenario2SimulatorStep(
            state=refreshed,
            ingested=ingested,
            complete=next_after_ingest >= len(CANONICAL_SIGNAL_SEQUENCE),
            next_index=next_after_ingest,
        )


__all__ = ["Scenario2SimulatorService"]
