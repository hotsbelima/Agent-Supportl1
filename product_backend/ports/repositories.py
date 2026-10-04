"""Persistence interfaces for product-owned Scenario 1 state.

Concrete persistence is intentionally outside Phase 3B; services depend on
these transactional ports so PostgreSQL can be added later without moving the
business rules into database/adapters.
"""

from __future__ import annotations

from typing import Protocol

from product_backend.domain.enums import ActionType
from product_backend.domain.models import (
    ActionProposal,
    Approval,
    Evidence,
    ExecutedAction,
    FieldServiceWorkOrder,
    Incident,
    Run,
)


class RunRepository(Protocol):
    async def add(self, run: Run) -> None: ...
    async def get(self, *, tenant_id: str, run_id: str) -> Run | None: ...
    async def save(self, run: Run) -> None: ...


class IncidentRepository(Protocol):
    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> Incident | None: ...
    async def save(self, incident: Incident) -> None: ...


class EvidenceRepository(Protocol):
    async def add(self, evidence: Evidence) -> None: ...
    async def get_many(
        self,
        *,
        tenant_id: str,
        run_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[Evidence, ...]: ...


class ProposalRepository(Protocol):
    async def add(self, proposal: ActionProposal) -> None: ...
    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> ActionProposal | None: ...
    async def save(self, proposal: ActionProposal) -> None: ...
    async def get_pending_for_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> ActionProposal | None: ...


class ApprovalRepository(Protocol):
    async def add(self, approval: Approval) -> None: ...
    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> Approval | None: ...


class ExecutedActionRepository(Protocol):
    async def add(self, action: ExecutedAction) -> None: ...
    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> ExecutedAction | None: ...
    async def get_equivalent(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
        device_id: str,
        action_type: ActionType,
    ) -> ExecutedAction | None: ...


class WorkOrderRepository(Protocol):
    async def add(self, work_order: FieldServiceWorkOrder) -> None: ...
    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> FieldServiceWorkOrder | None: ...
    async def get_for_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> FieldServiceWorkOrder | None: ...


class ProposalCreationUnitOfWork(Protocol):
    runs: RunRepository
    incidents: IncidentRepository
    evidence: EvidenceRepository
    proposals: ProposalRepository

    async def __aenter__(self) -> "ProposalCreationUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class ApprovalExecutionUnitOfWork(Protocol):
    runs: RunRepository
    incidents: IncidentRepository
    evidence: EvidenceRepository
    proposals: ProposalRepository
    approvals: ApprovalRepository
    executed_actions: ExecutedActionRepository
    work_orders: WorkOrderRepository

    async def __aenter__(self) -> "ApprovalExecutionUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...
