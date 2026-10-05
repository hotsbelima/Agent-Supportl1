"""Persistence ports for Product-owned Scenario 2 state and transactions."""

from __future__ import annotations

from typing import Protocol

from product_backend.domain.scenario2 import (
    MajorIncidentApproval,
    MajorIncidentExecution,
    MajorIncidentProposal,
    MajorIncidentRecord,
    OperationalSignal,
    Scenario2FixtureState,
    Scenario2SignalSource,
    ServiceIncident,
)

from .events import ApplicationEventRepository, ApplicationOutboxRepository
from .repositories import EvidenceRepository, RunRepository


class Scenario2FixtureStateRepository(Protocol):
    async def add(self, state: Scenario2FixtureState) -> None: ...

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> Scenario2FixtureState | None: ...

    async def save(self, state: Scenario2FixtureState) -> None: ...


class ServiceIncidentRepository(Protocol):
    async def add(self, incident: ServiceIncident) -> None: ...

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> ServiceIncident | None: ...

    async def get_for_site_service(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
        service_key: str,
    ) -> ServiceIncident | None: ...

    async def save(self, incident: ServiceIncident) -> None: ...


class OperationalSignalRepository(Protocol):
    async def add(self, signal: OperationalSignal) -> None: ...

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        signal_id: str,
    ) -> OperationalSignal | None: ...

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> tuple[OperationalSignal, ...]: ...

    async def get_by_source_identity(
        self,
        *,
        tenant_id: str,
        run_id: str,
        source: Scenario2SignalSource,
        source_ref: str,
    ) -> OperationalSignal | None: ...


class MajorIncidentProposalRepository(Protocol):
    async def add(self, proposal: MajorIncidentProposal) -> None: ...

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentProposal | None: ...

    async def save(self, proposal: MajorIncidentProposal) -> None: ...

    async def get_pending_equivalent(
        self,
        *,
        tenant_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ) -> MajorIncidentProposal | None: ...


class MajorIncidentApprovalRepository(Protocol):
    async def add(self, approval: MajorIncidentApproval) -> None: ...

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentApproval | None: ...


class MajorIncidentRepository(Protocol):
    async def add(self, major_incident: MajorIncidentRecord) -> None: ...

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentRecord | None: ...

    async def get_equivalent(
        self,
        *,
        tenant_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ) -> MajorIncidentRecord | None: ...


class MajorIncidentExecutionRepository(Protocol):
    async def add(self, execution: MajorIncidentExecution) -> None: ...

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentExecution | None: ...


class Scenario2RunStartUnitOfWork(Protocol):
    runs: RunRepository
    fixture_states: Scenario2FixtureStateRepository
    events: ApplicationEventRepository

    async def __aenter__(self) -> "Scenario2RunStartUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class Scenario2SignalIngestionUnitOfWork(Protocol):
    runs: RunRepository
    service_incidents: ServiceIncidentRepository
    signals: OperationalSignalRepository
    events: ApplicationEventRepository
    outbox: ApplicationOutboxRepository

    async def __aenter__(self) -> "Scenario2SignalIngestionUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class Scenario2FixtureStateUnitOfWork(Protocol):
    runs: RunRepository
    fixture_states: Scenario2FixtureStateRepository

    async def __aenter__(self) -> "Scenario2FixtureStateUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class Scenario2ProposalUnitOfWork(Protocol):
    runs: RunRepository
    service_incidents: ServiceIncidentRepository
    signals: OperationalSignalRepository
    evidence: EvidenceRepository
    major_incident_proposals: MajorIncidentProposalRepository
    major_incidents: MajorIncidentRepository

    async def __aenter__(self) -> "Scenario2ProposalUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class Scenario2ApprovalUnitOfWork(Protocol):
    runs: RunRepository
    service_incidents: ServiceIncidentRepository
    signals: OperationalSignalRepository
    evidence: EvidenceRepository
    major_incident_proposals: MajorIncidentProposalRepository
    major_incident_approvals: MajorIncidentApprovalRepository
    major_incidents: MajorIncidentRepository
    major_incident_executions: MajorIncidentExecutionRepository

    async def __aenter__(self) -> "Scenario2ApprovalUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


__all__ = [
    "MajorIncidentApprovalRepository",
    "MajorIncidentExecutionRepository",
    "MajorIncidentProposalRepository",
    "MajorIncidentRepository",
    "OperationalSignalRepository",
    "Scenario2ApprovalUnitOfWork",
    "Scenario2FixtureStateUnitOfWork",
    "Scenario2FixtureStateRepository",
    "ServiceIncidentRepository",
    "Scenario2ProposalUnitOfWork",
    "Scenario2RunStartUnitOfWork",
    "Scenario2SignalIngestionUnitOfWork",
]
