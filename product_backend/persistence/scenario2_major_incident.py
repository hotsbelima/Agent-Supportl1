"""SQLAlchemy repositories for Scenario 2 Major Incident HITL state."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from product_backend.domain.enums import ApprovalDecision, ProposalStatus
from product_backend.domain.scenario2 import (
    MajorIncidentApproval,
    MajorIncidentExecution,
    MajorIncidentProposal,
    MajorIncidentRecord,
    MajorIncidentStatus,
    Scenario2ActionType,
)

from .tables import (
    MajorIncidentApprovalRow,
    MajorIncidentExecutionRow,
    MajorIncidentProposalRow,
    MajorIncidentRow,
)


def _proposal_from_row(row: MajorIncidentProposalRow) -> MajorIncidentProposal:
    return MajorIncidentProposal(
        proposal_id=row.proposal_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        correlation_key=row.correlation_key,
        service_key=row.service_key,
        affected_site_ids=tuple(row.affected_site_ids),
        dependency_id=row.dependency_id,
        dependency_name=row.dependency_name,
        action_type=Scenario2ActionType(row.action_type),
        evidence_ids=tuple(row.evidence_ids),
        summary=row.summary,
        rationale=row.rationale,
        status=ProposalStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _proposal_to_row(proposal: MajorIncidentProposal) -> MajorIncidentProposalRow:
    return MajorIncidentProposalRow(
        tenant_id=proposal.tenant_id,
        run_id=proposal.run_id,
        proposal_id=proposal.proposal_id,
        correlation_key=proposal.correlation_key,
        service_key=proposal.service_key,
        affected_site_ids=list(proposal.affected_site_ids),
        dependency_id=proposal.dependency_id,
        dependency_name=proposal.dependency_name,
        action_type=proposal.action_type.value,
        evidence_ids=list(proposal.evidence_ids),
        summary=proposal.summary,
        rationale=proposal.rationale,
        status=proposal.status.value,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


def _approval_from_row(row: MajorIncidentApprovalRow) -> MajorIncidentApproval:
    return MajorIncidentApproval(
        approval_id=row.approval_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        proposal_id=row.proposal_id,
        decision=ApprovalDecision(row.decision),
        decided_at=row.decided_at,
        decided_by=row.decided_by,
    )


def _approval_to_row(approval: MajorIncidentApproval) -> MajorIncidentApprovalRow:
    return MajorIncidentApprovalRow(
        tenant_id=approval.tenant_id,
        run_id=approval.run_id,
        approval_id=approval.approval_id,
        proposal_id=approval.proposal_id,
        decision=approval.decision.value,
        decided_at=approval.decided_at,
        decided_by=approval.decided_by,
    )


def _major_incident_from_row(row: MajorIncidentRow) -> MajorIncidentRecord:
    return MajorIncidentRecord(
        major_incident_id=row.major_incident_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        proposal_id=row.proposal_id,
        correlation_key=row.correlation_key,
        service_key=row.service_key,
        affected_site_ids=tuple(row.affected_site_ids),
        dependency_id=row.dependency_id,
        dependency_name=row.dependency_name,
        summary=row.summary,
        status=MajorIncidentStatus(row.status),
        created_at=row.created_at,
    )


def _major_incident_to_row(item: MajorIncidentRecord) -> MajorIncidentRow:
    return MajorIncidentRow(
        tenant_id=item.tenant_id,
        run_id=item.run_id,
        major_incident_id=item.major_incident_id,
        proposal_id=item.proposal_id,
        correlation_key=item.correlation_key,
        service_key=item.service_key,
        affected_site_ids=list(item.affected_site_ids),
        dependency_id=item.dependency_id,
        dependency_name=item.dependency_name,
        summary=item.summary,
        status=item.status.value,
        created_at=item.created_at,
    )


def _execution_from_row(row: MajorIncidentExecutionRow) -> MajorIncidentExecution:
    return MajorIncidentExecution(
        execution_id=row.execution_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        proposal_id=row.proposal_id,
        action_type=Scenario2ActionType(row.action_type),
        major_incident_id=row.major_incident_id,
        executed_at=row.executed_at,
    )


def _execution_to_row(item: MajorIncidentExecution) -> MajorIncidentExecutionRow:
    return MajorIncidentExecutionRow(
        tenant_id=item.tenant_id,
        run_id=item.run_id,
        execution_id=item.execution_id,
        proposal_id=item.proposal_id,
        action_type=item.action_type.value,
        major_incident_id=item.major_incident_id,
        executed_at=item.executed_at,
    )


def _maybe_lock(statement, enabled: bool):
    return statement.with_for_update() if enabled else statement


class SqlAlchemyMajorIncidentProposalRepository:
    def __init__(self, session: AsyncSession, *, lock_for_update: bool = False) -> None:
        self._session = session
        self._lock_for_update = lock_for_update

    async def add(self, proposal: MajorIncidentProposal) -> None:
        self._session.add(_proposal_to_row(proposal))

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentProposal | None:
        result = await self._session.execute(
            _maybe_lock(
                select(MajorIncidentProposalRow).where(
                    MajorIncidentProposalRow.tenant_id == tenant_id,
                    MajorIncidentProposalRow.run_id == run_id,
                    MajorIncidentProposalRow.proposal_id == proposal_id,
                ),
                self._lock_for_update,
            )
        )
        row = result.scalar_one_or_none()
        return _proposal_from_row(row) if row is not None else None

    async def save(self, proposal: MajorIncidentProposal) -> None:
        await self._session.merge(_proposal_to_row(proposal))

    async def get_pending_equivalent(
        self,
        *,
        tenant_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ) -> MajorIncidentProposal | None:
        result = await self._session.execute(
            _maybe_lock(
                select(MajorIncidentProposalRow).where(
                    MajorIncidentProposalRow.tenant_id == tenant_id,
                    MajorIncidentProposalRow.service_key == service_key,
                    MajorIncidentProposalRow.correlation_key == correlation_key,
                    MajorIncidentProposalRow.dependency_id == dependency_id,
                    MajorIncidentProposalRow.status
                    == ProposalStatus.PENDING_APPROVAL.value,
                ),
                self._lock_for_update,
            )
        )
        row = result.scalars().first()
        return _proposal_from_row(row) if row is not None else None

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> tuple[MajorIncidentProposal, ...]:
        result = await self._session.execute(
            select(MajorIncidentProposalRow)
            .where(
                MajorIncidentProposalRow.tenant_id == tenant_id,
                MajorIncidentProposalRow.run_id == run_id,
            )
            .order_by(
                MajorIncidentProposalRow.created_at,
                MajorIncidentProposalRow.proposal_id,
            )
        )
        return tuple(_proposal_from_row(row) for row in result.scalars().all())


class SqlAlchemyMajorIncidentApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, approval: MajorIncidentApproval) -> None:
        self._session.add(_approval_to_row(approval))

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentApproval | None:
        result = await self._session.execute(
            select(MajorIncidentApprovalRow).where(
                MajorIncidentApprovalRow.tenant_id == tenant_id,
                MajorIncidentApprovalRow.run_id == run_id,
                MajorIncidentApprovalRow.proposal_id == proposal_id,
            )
        )
        row = result.scalar_one_or_none()
        return _approval_from_row(row) if row is not None else None

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> tuple[MajorIncidentApproval, ...]:
        result = await self._session.execute(
            select(MajorIncidentApprovalRow)
            .where(
                MajorIncidentApprovalRow.tenant_id == tenant_id,
                MajorIncidentApprovalRow.run_id == run_id,
            )
            .order_by(
                MajorIncidentApprovalRow.decided_at,
                MajorIncidentApprovalRow.approval_id,
            )
        )
        return tuple(_approval_from_row(row) for row in result.scalars().all())


class SqlAlchemyMajorIncidentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, item: MajorIncidentRecord) -> None:
        self._session.add(_major_incident_to_row(item))
        # MajorIncidentExecution has a composite FK to this row and is created
        # in the same approval transaction. Flush the FK target explicitly
        # before any later query/autoflush can attempt the execution insert.
        await self._session.flush()

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentRecord | None:
        result = await self._session.execute(
            select(MajorIncidentRow).where(
                MajorIncidentRow.tenant_id == tenant_id,
                MajorIncidentRow.run_id == run_id,
                MajorIncidentRow.proposal_id == proposal_id,
            )
        )
        row = result.scalar_one_or_none()
        return _major_incident_from_row(row) if row is not None else None

    async def get_equivalent(
        self,
        *,
        tenant_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ) -> MajorIncidentRecord | None:
        result = await self._session.execute(
            select(MajorIncidentRow).where(
                MajorIncidentRow.tenant_id == tenant_id,
                MajorIncidentRow.service_key == service_key,
                MajorIncidentRow.correlation_key == correlation_key,
                MajorIncidentRow.dependency_id == dependency_id,
            )
        )
        row = result.scalars().first()
        return _major_incident_from_row(row) if row is not None else None

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> tuple[MajorIncidentRecord, ...]:
        result = await self._session.execute(
            select(MajorIncidentRow)
            .where(
                MajorIncidentRow.tenant_id == tenant_id,
                MajorIncidentRow.run_id == run_id,
            )
            .order_by(MajorIncidentRow.created_at, MajorIncidentRow.major_incident_id)
        )
        return tuple(_major_incident_from_row(row) for row in result.scalars().all())


class SqlAlchemyMajorIncidentExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, execution: MajorIncidentExecution) -> None:
        self._session.add(_execution_to_row(execution))

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> MajorIncidentExecution | None:
        result = await self._session.execute(
            select(MajorIncidentExecutionRow).where(
                MajorIncidentExecutionRow.tenant_id == tenant_id,
                MajorIncidentExecutionRow.run_id == run_id,
                MajorIncidentExecutionRow.proposal_id == proposal_id,
            )
        )
        row = result.scalar_one_or_none()
        return _execution_from_row(row) if row is not None else None

    async def list_for_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> tuple[MajorIncidentExecution, ...]:
        result = await self._session.execute(
            select(MajorIncidentExecutionRow)
            .where(
                MajorIncidentExecutionRow.tenant_id == tenant_id,
                MajorIncidentExecutionRow.run_id == run_id,
            )
            .order_by(
                MajorIncidentExecutionRow.executed_at,
                MajorIncidentExecutionRow.execution_id,
            )
        )
        return tuple(_execution_from_row(row) for row in result.scalars().all())


__all__ = [
    "SqlAlchemyMajorIncidentApprovalRepository",
    "SqlAlchemyMajorIncidentExecutionRepository",
    "SqlAlchemyMajorIncidentProposalRepository",
    "SqlAlchemyMajorIncidentRepository",
]
