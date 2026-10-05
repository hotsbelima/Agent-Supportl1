"""Read model for persisted Scenario 2 ingestion state."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from product_backend.contracts.scenario2_ingestion import (
    Scenario2IngestionStateSnapshot,
)
from product_backend.domain.enums import HealthState, IncidentStatus, RunStatus
from product_backend.domain.models import Run
from product_backend.domain.scenario2 import (
    OperationalSignal,
    Scenario2FixtureState,
    Scenario2SignalSource,
    ServiceIncident,
)

from .repositories import _evidence_from_row

from .tables import (
    ApplicationEventRow,
    EvidenceRow,
    OperationalSignalRow,
    RunRow,
    Scenario2FixtureStateRow,
    ServiceIncidentRow,
)


class SqlAlchemyScenario2StateQuery:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> Scenario2IngestionStateSnapshot | None:
        async with self._session_factory() as session:
            run_row = (
                await session.execute(
                    select(RunRow).where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.run_id == run_id,
                        RunRow.scenario_id == "scenario-2",
                    )
                )
            ).scalar_one_or_none()
            if run_row is None:
                return None

            incident_rows = (
                await session.execute(
                    select(ServiceIncidentRow)
                    .where(
                        ServiceIncidentRow.tenant_id == tenant_id,
                        ServiceIncidentRow.run_id == run_id,
                    )
                    .order_by(
                        ServiceIncidentRow.created_at,
                        ServiceIncidentRow.incident_id,
                    )
                )
            ).scalars().all()

            signal_rows = (
                await session.execute(
                    select(OperationalSignalRow)
                    .where(
                        OperationalSignalRow.tenant_id == tenant_id,
                        OperationalSignalRow.run_id == run_id,
                    )
                    .order_by(
                        OperationalSignalRow.received_at,
                        OperationalSignalRow.signal_id,
                    )
                )
            ).scalars().all()

            evidence_rows = (
                await session.execute(
                    select(EvidenceRow)
                    .where(
                        EvidenceRow.tenant_id == tenant_id,
                        EvidenceRow.run_id == run_id,
                    )
                    .order_by(EvidenceRow.captured_at, EvidenceRow.evidence_id)
                )
            ).scalars().all()

            fixture_row = (
                await session.execute(
                    select(Scenario2FixtureStateRow).where(
                        Scenario2FixtureStateRow.tenant_id == tenant_id,
                        Scenario2FixtureStateRow.run_id == run_id,
                    )
                )
            ).scalar_one_or_none()
            if fixture_row is None:
                raise ValueError("Scenario 2 fixture state is missing")

            latest_event_seq = int(
                await session.scalar(
                    select(func.max(ApplicationEventRow.seq)).where(
                        ApplicationEventRow.tenant_id == tenant_id,
                        ApplicationEventRow.run_id == run_id,
                    )
                )
                or 0
            )

            run = Run(
                run_id=run_row.run_id,
                tenant_id=run_row.tenant_id,
                scenario_id=run_row.scenario_id,
                status=RunStatus(run_row.status),
                created_at=run_row.created_at,
                updated_at=run_row.updated_at,
            )
            incidents = tuple(
                ServiceIncident(
                    incident_id=row.incident_id,
                    tenant_id=row.tenant_id,
                    run_id=row.run_id,
                    site_id=row.site_id,
                    service_key=row.service_key,
                    symptom_key=row.symptom_key,
                    status=IncidentStatus(row.status),
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in incident_rows
            )
            signals = tuple(
                OperationalSignal(
                    signal_id=row.signal_id,
                    tenant_id=row.tenant_id,
                    run_id=row.run_id,
                    source=Scenario2SignalSource(row.source),
                    site_id=row.site_id,
                    service_key=row.service_key,
                    symptom_key=row.symptom_key,
                    source_ref=row.source_ref,
                    received_at=row.received_at,
                    safe_payload=dict(row.safe_payload),
                    incident_id=row.incident_id,
                )
                for row in signal_rows
            )
            fixture_state = Scenario2FixtureState(
                tenant_id=fixture_row.tenant_id,
                run_id=fixture_row.run_id,
                dependency_status=HealthState(fixture_row.dependency_status),
                matching_major_incident_id=fixture_row.matching_major_incident_id,
                updated_at=fixture_row.updated_at,
            )
            return Scenario2IngestionStateSnapshot(
                run=run,
                service_incidents=incidents,
                operational_signals=signals,
                evidence=tuple(_evidence_from_row(row) for row in evidence_rows),
                fixture_state=fixture_state,
                latest_event_seq=latest_event_seq,
            )


__all__ = ["SqlAlchemyScenario2StateQuery"]
