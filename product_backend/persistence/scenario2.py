"""SQLAlchemy persistence for Scenario 2 operational and fixture state."""

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_backend.contracts.scenario2_signal import validate_operational_signal
from product_backend.domain.enums import HealthState, IncidentStatus
from product_backend.domain.scenario2 import (
    OperationalSignal,
    Scenario2FixtureState,
    Scenario2SignalSource,
    ServiceIncident,
)

from .tables import (
    OperationalSignalRow,
    Scenario2FixtureStateRow,
    ServiceIncidentRow,
)


def _fixture_state_from_row(
    row: Scenario2FixtureStateRow,
) -> Scenario2FixtureState:
    return Scenario2FixtureState(
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        dependency_status=HealthState(row.dependency_status),
        matching_major_incident_id=row.matching_major_incident_id,
        updated_at=row.updated_at,
    )


def _fixture_state_to_row(
    state: Scenario2FixtureState,
) -> Scenario2FixtureStateRow:
    return Scenario2FixtureStateRow(
        tenant_id=state.tenant_id,
        run_id=state.run_id,
        dependency_status=state.dependency_status.value,
        matching_major_incident_id=state.matching_major_incident_id,
        updated_at=state.updated_at,
    )


def _service_incident_from_row(row: ServiceIncidentRow) -> ServiceIncident:
    return ServiceIncident(
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


def _service_incident_to_row(incident: ServiceIncident) -> ServiceIncidentRow:
    return ServiceIncidentRow(
        tenant_id=incident.tenant_id,
        run_id=incident.run_id,
        incident_id=incident.incident_id,
        site_id=incident.site_id,
        service_key=incident.service_key,
        symptom_key=incident.symptom_key,
        status=incident.status.value,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


def _signal_from_row(row: OperationalSignalRow) -> OperationalSignal:
    return OperationalSignal(
        signal_id=row.signal_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        source=Scenario2SignalSource(row.source),
        site_id=row.site_id,
        service_key=row.service_key,
        symptom_key=row.symptom_key,
        source_ref=row.source_ref,
        received_at=row.received_at,
        safe_payload=deepcopy(row.safe_payload),
        incident_id=row.incident_id,
    )


def _signal_to_row(signal: OperationalSignal) -> OperationalSignalRow:
    validate_operational_signal(signal)
    return OperationalSignalRow(
        tenant_id=signal.tenant_id,
        run_id=signal.run_id,
        signal_id=signal.signal_id,
        source=signal.source.value,
        site_id=signal.site_id,
        service_key=signal.service_key,
        symptom_key=signal.symptom_key,
        source_ref=signal.source_ref,
        received_at=signal.received_at,
        safe_payload=deepcopy(signal.safe_payload),
        incident_id=signal.incident_id,
    )


class SqlAlchemyScenario2FixtureStateRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        lock_for_update: bool = False,
    ) -> None:
        self._session = session
        self._lock_for_update = lock_for_update

    async def add(self, state: Scenario2FixtureState) -> None:
        self._session.add(_fixture_state_to_row(state))
        await self._session.flush()

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> Scenario2FixtureState | None:
        statement = select(Scenario2FixtureStateRow).where(
            Scenario2FixtureStateRow.tenant_id == tenant_id,
            Scenario2FixtureStateRow.run_id == run_id,
        )
        if self._lock_for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        return _fixture_state_from_row(row) if row is not None else None

    async def save(self, state: Scenario2FixtureState) -> None:
        statement = (
            select(Scenario2FixtureStateRow)
            .where(
                Scenario2FixtureStateRow.tenant_id == state.tenant_id,
                Scenario2FixtureStateRow.run_id == state.run_id,
            )
            .with_for_update()
        )
        result = await self._session.execute(statement)
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("Scenario 2 fixture state does not exist")
        row.dependency_status = state.dependency_status.value
        row.matching_major_incident_id = state.matching_major_incident_id
        row.updated_at = state.updated_at
        await self._session.flush()


class SqlAlchemyServiceIncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, incident: ServiceIncident) -> None:
        self._session.add(_service_incident_to_row(incident))
        await self._session.flush()

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> ServiceIncident | None:
        result = await self._session.execute(
            select(ServiceIncidentRow).where(
                ServiceIncidentRow.tenant_id == tenant_id,
                ServiceIncidentRow.run_id == run_id,
                ServiceIncidentRow.incident_id == incident_id,
            )
        )
        row = result.scalar_one_or_none()
        return _service_incident_from_row(row) if row is not None else None

    async def get_for_site_service(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
        service_key: str,
    ) -> ServiceIncident | None:
        result = await self._session.execute(
            select(ServiceIncidentRow).where(
                ServiceIncidentRow.tenant_id == tenant_id,
                ServiceIncidentRow.run_id == run_id,
                ServiceIncidentRow.site_id == site_id,
                ServiceIncidentRow.service_key == service_key,
            )
        )
        row = result.scalar_one_or_none()
        return _service_incident_from_row(row) if row is not None else None

    async def save(self, incident: ServiceIncident) -> None:
        result = await self._session.execute(
            select(ServiceIncidentRow)
            .where(
                ServiceIncidentRow.tenant_id == incident.tenant_id,
                ServiceIncidentRow.run_id == incident.run_id,
                ServiceIncidentRow.incident_id == incident.incident_id,
            )
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ValueError("service incident does not exist")
        row.site_id = incident.site_id
        row.service_key = incident.service_key
        row.symptom_key = incident.symptom_key
        row.status = incident.status.value
        row.updated_at = incident.updated_at
        await self._session.flush()


class SqlAlchemyOperationalSignalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, signal: OperationalSignal) -> None:
        self._session.add(_signal_to_row(signal))
        await self._session.flush()

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        signal_id: str,
    ) -> OperationalSignal | None:
        result = await self._session.execute(
            select(OperationalSignalRow).where(
                OperationalSignalRow.tenant_id == tenant_id,
                OperationalSignalRow.run_id == run_id,
                OperationalSignalRow.signal_id == signal_id,
            )
        )
        row = result.scalar_one_or_none()
        return _signal_from_row(row) if row is not None else None

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> tuple[OperationalSignal, ...]:
        result = await self._session.execute(
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
        return tuple(_signal_from_row(row) for row in result.scalars().all())

    async def get_by_source_identity(
        self,
        *,
        tenant_id: str,
        run_id: str,
        source: Scenario2SignalSource,
        source_ref: str,
    ) -> OperationalSignal | None:
        result = await self._session.execute(
            select(OperationalSignalRow).where(
                OperationalSignalRow.tenant_id == tenant_id,
                OperationalSignalRow.run_id == run_id,
                OperationalSignalRow.source == source.value,
                OperationalSignalRow.source_ref == source_ref,
            )
        )
        row = result.scalar_one_or_none()
        return _signal_from_row(row) if row is not None else None


__all__ = [
    "SqlAlchemyOperationalSignalRepository",
    "SqlAlchemyScenario2FixtureStateRepository",
    "SqlAlchemyServiceIncidentRepository",
]
