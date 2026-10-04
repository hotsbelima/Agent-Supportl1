"""SQLAlchemy implementation of the persisted run-state read port."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from product_backend.contracts.run_state import RunStateSnapshot

from .repositories import (
    _approval_from_row,
    _evidence_from_row,
    _executed_action_from_row,
    _incident_from_row,
    _proposal_from_row,
    _run_from_row,
    _work_order_from_row,
)
from .tables import (
    ActionProposalRow,
    ApplicationEventRow,
    ApprovalRow,
    EvidenceRow,
    ExecutedActionRow,
    FieldServiceWorkOrderRow,
    IncidentRow,
    RunRow,
)


class SqlAlchemyRunStateQuery:
    """Read one internally consistent run snapshot.

    The owning Run row is held with a PostgreSQL shared lock while child tables
    are read. Phase 4 mutation/event transactions take a conflicting FOR UPDATE
    lock on the same Run before commit, preventing a mixed pre/post-mutation
    state bundle from being returned to the API.
    """

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
    ) -> RunStateSnapshot | None:
        async with self._session_factory() as session:
            run_result = await session.execute(
                select(RunRow)
                .where(
                    RunRow.tenant_id == tenant_id,
                    RunRow.run_id == run_id,
                )
                .with_for_update(read=True)
            )
            run_row = run_result.scalar_one_or_none()
            if run_row is None:
                return None

            incidents_result = await session.execute(
                select(IncidentRow)
                .where(
                    IncidentRow.tenant_id == tenant_id,
                    IncidentRow.run_id == run_id,
                )
                .order_by(IncidentRow.created_at, IncidentRow.incident_id)
            )
            evidence_result = await session.execute(
                select(EvidenceRow)
                .where(
                    EvidenceRow.tenant_id == tenant_id,
                    EvidenceRow.run_id == run_id,
                )
                .order_by(EvidenceRow.captured_at, EvidenceRow.evidence_id)
            )
            proposals_result = await session.execute(
                select(ActionProposalRow)
                .where(
                    ActionProposalRow.tenant_id == tenant_id,
                    ActionProposalRow.run_id == run_id,
                )
                .order_by(ActionProposalRow.created_at, ActionProposalRow.proposal_id)
            )
            approvals_result = await session.execute(
                select(ApprovalRow)
                .where(
                    ApprovalRow.tenant_id == tenant_id,
                    ApprovalRow.run_id == run_id,
                )
                .order_by(ApprovalRow.decided_at, ApprovalRow.approval_id)
            )
            actions_result = await session.execute(
                select(ExecutedActionRow)
                .where(
                    ExecutedActionRow.tenant_id == tenant_id,
                    ExecutedActionRow.run_id == run_id,
                )
                .order_by(
                    ExecutedActionRow.executed_at,
                    ExecutedActionRow.action_id,
                )
            )
            work_orders_result = await session.execute(
                select(FieldServiceWorkOrderRow)
                .where(
                    FieldServiceWorkOrderRow.tenant_id == tenant_id,
                    FieldServiceWorkOrderRow.run_id == run_id,
                )
                .order_by(
                    FieldServiceWorkOrderRow.created_at,
                    FieldServiceWorkOrderRow.work_order_id,
                )
            )
            latest_event_seq = await session.scalar(
                select(func.max(ApplicationEventRow.seq)).where(
                    ApplicationEventRow.tenant_id == tenant_id,
                    ApplicationEventRow.run_id == run_id,
                )
            )

            return RunStateSnapshot(
                run=_run_from_row(run_row),
                incidents=tuple(
                    _incident_from_row(row)
                    for row in incidents_result.scalars().all()
                ),
                evidence=tuple(
                    _evidence_from_row(row)
                    for row in evidence_result.scalars().all()
                ),
                proposals=tuple(
                    _proposal_from_row(row)
                    for row in proposals_result.scalars().all()
                ),
                approvals=tuple(
                    _approval_from_row(row)
                    for row in approvals_result.scalars().all()
                ),
                executed_actions=tuple(
                    _executed_action_from_row(row)
                    for row in actions_result.scalars().all()
                ),
                work_orders=tuple(
                    _work_order_from_row(row)
                    for row in work_orders_result.scalars().all()
                ),
                latest_event_seq=int(latest_event_seq or 0),
            )


__all__ = ["SqlAlchemyRunStateQuery"]
