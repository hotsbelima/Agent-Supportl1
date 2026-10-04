"""Concrete SQLAlchemy implementations of the Phase 3 repository ports."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from product_backend.domain.enums import (
    ActionType,
    ApprovalDecision,
    DiagnosisCode,
    EvidenceSourceType,
    IncidentStatus,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.models import (
    ActionProposal,
    Approval,
    Evidence,
    ExecutedAction,
    FieldServiceWorkOrder,
    Incident,
    Run,
)

from .serialization import (
    deserialize_evidence_payload,
    serialize_evidence_payload,
)
from .tables import (
    ActionProposalRow,
    ApprovalRow,
    EvidenceRow,
    ExecutedActionRow,
    FieldServiceWorkOrderRow,
    IncidentRow,
    RunRow,
)


def _maybe_lock(statement: Select, lock_for_update: bool) -> Select:
    return statement.with_for_update() if lock_for_update else statement


def _run_from_row(row: RunRow) -> Run:
    return Run(
        run_id=row.run_id,
        tenant_id=row.tenant_id,
        scenario_id=row.scenario_id,
        status=RunStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _run_to_row(run: Run) -> RunRow:
    return RunRow(
        tenant_id=run.tenant_id,
        run_id=run.run_id,
        scenario_id=run.scenario_id,
        status=run.status.value,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _incident_from_row(row: IncidentRow) -> Incident:
    return Incident(
        incident_id=row.incident_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        site_id=row.site_id,
        reported_device_id=row.reported_device_id,
        symptom=row.symptom,
        status=IncidentStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _incident_to_row(incident: Incident) -> IncidentRow:
    return IncidentRow(
        tenant_id=incident.tenant_id,
        run_id=incident.run_id,
        incident_id=incident.incident_id,
        site_id=incident.site_id,
        reported_device_id=incident.reported_device_id,
        symptom=incident.symptom,
        status=incident.status.value,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
    )


def _evidence_from_row(row: EvidenceRow) -> Evidence:
    source_type = EvidenceSourceType(row.source_type)
    return Evidence(
        evidence_id=row.evidence_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        source_type=source_type,
        captured_at=row.captured_at,
        entity_ids=tuple(row.entity_ids),
        payload=deserialize_evidence_payload(source_type, row.payload),
        facts=tuple(row.facts),
        expires_at=row.expires_at,
    )


def _evidence_to_row(evidence: Evidence) -> EvidenceRow:
    return EvidenceRow(
        tenant_id=evidence.tenant_id,
        run_id=evidence.run_id,
        evidence_id=evidence.evidence_id,
        source_type=evidence.source_type.value,
        captured_at=evidence.captured_at,
        entity_ids=list(evidence.entity_ids),
        payload=serialize_evidence_payload(
            evidence.source_type,
            evidence.payload,
        ),
        facts=list(evidence.facts),
        expires_at=evidence.expires_at,
    )


def _proposal_from_row(row: ActionProposalRow) -> ActionProposal:
    return ActionProposal(
        proposal_id=row.proposal_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        incident_id=row.incident_id,
        device_id=row.device_id,
        diagnosis=DiagnosisCode(row.diagnosis),
        action_type=ActionType(row.action_type),
        evidence_ids=tuple(row.evidence_ids),
        rationale=row.rationale,
        status=ProposalStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _proposal_to_row(proposal: ActionProposal) -> ActionProposalRow:
    return ActionProposalRow(
        tenant_id=proposal.tenant_id,
        run_id=proposal.run_id,
        proposal_id=proposal.proposal_id,
        incident_id=proposal.incident_id,
        device_id=proposal.device_id,
        diagnosis=proposal.diagnosis.value,
        action_type=proposal.action_type.value,
        evidence_ids=list(proposal.evidence_ids),
        rationale=proposal.rationale,
        status=proposal.status.value,
        created_at=proposal.created_at,
        updated_at=proposal.updated_at,
    )


def _approval_from_row(row: ApprovalRow) -> Approval:
    return Approval(
        approval_id=row.approval_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        proposal_id=row.proposal_id,
        decision=ApprovalDecision(row.decision),
        decided_at=row.decided_at,
        decided_by=row.decided_by,
    )


def _approval_to_row(approval: Approval) -> ApprovalRow:
    return ApprovalRow(
        tenant_id=approval.tenant_id,
        run_id=approval.run_id,
        approval_id=approval.approval_id,
        proposal_id=approval.proposal_id,
        decision=approval.decision.value,
        decided_at=approval.decided_at,
        decided_by=approval.decided_by,
    )


def _executed_action_from_row(row: ExecutedActionRow) -> ExecutedAction:
    return ExecutedAction(
        action_id=row.action_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        proposal_id=row.proposal_id,
        incident_id=row.incident_id,
        device_id=row.device_id,
        action_type=ActionType(row.action_type),
        executed_at=row.executed_at,
    )


def _executed_action_to_row(action: ExecutedAction) -> ExecutedActionRow:
    return ExecutedActionRow(
        tenant_id=action.tenant_id,
        run_id=action.run_id,
        action_id=action.action_id,
        proposal_id=action.proposal_id,
        incident_id=action.incident_id,
        device_id=action.device_id,
        action_type=action.action_type.value,
        executed_at=action.executed_at,
    )


def _work_order_from_row(row: FieldServiceWorkOrderRow) -> FieldServiceWorkOrder:
    return FieldServiceWorkOrder(
        work_order_id=row.work_order_id,
        tenant_id=row.tenant_id,
        run_id=row.run_id,
        proposal_id=row.proposal_id,
        incident_id=row.incident_id,
        device_id=row.device_id,
        site_id=row.site_id,
        attachment_id=row.attachment_id,
        switch_id=row.switch_id,
        port_id=row.port_id,
        created_at=row.created_at,
    )


def _work_order_to_row(
    work_order: FieldServiceWorkOrder,
) -> FieldServiceWorkOrderRow:
    return FieldServiceWorkOrderRow(
        tenant_id=work_order.tenant_id,
        run_id=work_order.run_id,
        work_order_id=work_order.work_order_id,
        proposal_id=work_order.proposal_id,
        incident_id=work_order.incident_id,
        device_id=work_order.device_id,
        site_id=work_order.site_id,
        attachment_id=work_order.attachment_id,
        switch_id=work_order.switch_id,
        port_id=work_order.port_id,
        created_at=work_order.created_at,
    )


class SqlAlchemyRunRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        lock_for_update: bool = False,
    ) -> None:
        self._session = session
        self._lock_for_update = lock_for_update

    async def add(self, run: Run) -> None:
        self._session.add(_run_to_row(run))

    async def get(self, *, tenant_id: str, run_id: str) -> Run | None:
        statement = select(RunRow).where(
            RunRow.tenant_id == tenant_id,
            RunRow.run_id == run_id,
        )
        result = await self._session.execute(
            _maybe_lock(statement, self._lock_for_update)
        )
        row = result.scalar_one_or_none()
        return _run_from_row(row) if row is not None else None

    async def save(self, run: Run) -> None:
        await self._session.merge(_run_to_row(run))


class SqlAlchemyIncidentRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        lock_for_update: bool = False,
    ) -> None:
        self._session = session
        self._lock_for_update = lock_for_update

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> Incident | None:
        statement = select(IncidentRow).where(
            IncidentRow.tenant_id == tenant_id,
            IncidentRow.run_id == run_id,
            IncidentRow.incident_id == incident_id,
        )
        result = await self._session.execute(
            _maybe_lock(statement, self._lock_for_update)
        )
        row = result.scalar_one_or_none()
        return _incident_from_row(row) if row is not None else None

    async def find_by_device(
        self,
        *,
        tenant_id: str,
        run_id: str,
        device_id: str,
    ) -> Incident | None:
        statement = select(IncidentRow).where(
            IncidentRow.tenant_id == tenant_id,
            IncidentRow.run_id == run_id,
            IncidentRow.reported_device_id == device_id,
        )
        result = await self._session.execute(statement)
        row = result.scalars().first()
        return _incident_from_row(row) if row is not None else None

    async def find_by_site(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
    ) -> Incident | None:
        statement = select(IncidentRow).where(
            IncidentRow.tenant_id == tenant_id,
            IncidentRow.run_id == run_id,
            IncidentRow.site_id == site_id,
        )
        result = await self._session.execute(statement)
        row = result.scalars().first()
        return _incident_from_row(row) if row is not None else None

    async def save(self, incident: Incident) -> None:
        await self._session.merge(_incident_to_row(incident))


class SqlAlchemyEvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, evidence: Evidence) -> None:
        self._session.add(_evidence_to_row(evidence))

    async def get_many(
        self,
        *,
        tenant_id: str,
        run_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[Evidence, ...]:
        if not evidence_ids:
            return ()
        result = await self._session.execute(
            select(EvidenceRow).where(
                EvidenceRow.tenant_id == tenant_id,
                EvidenceRow.run_id == run_id,
                EvidenceRow.evidence_id.in_(evidence_ids),
            )
        )
        rows = result.scalars().all()
        by_id = {row.evidence_id: _evidence_from_row(row) for row in rows}
        return tuple(by_id[value] for value in evidence_ids if value in by_id)

    async def find_by_entity_id(
        self,
        *,
        tenant_id: str,
        run_id: str,
        entity_id: str,
    ) -> tuple[Evidence, ...]:
        result = await self._session.execute(
            select(EvidenceRow)
            .where(
                EvidenceRow.tenant_id == tenant_id,
                EvidenceRow.run_id == run_id,
                EvidenceRow.entity_ids.contains([entity_id]),
            )
            .order_by(EvidenceRow.captured_at, EvidenceRow.evidence_id)
        )
        return tuple(_evidence_from_row(row) for row in result.scalars().all())


class SqlAlchemyProposalRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        lock_for_update: bool = False,
    ) -> None:
        self._session = session
        self._lock_for_update = lock_for_update

    async def add(self, proposal: ActionProposal) -> None:
        self._session.add(_proposal_to_row(proposal))

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> ActionProposal | None:
        statement = select(ActionProposalRow).where(
            ActionProposalRow.tenant_id == tenant_id,
            ActionProposalRow.run_id == run_id,
            ActionProposalRow.proposal_id == proposal_id,
        )
        result = await self._session.execute(
            _maybe_lock(statement, self._lock_for_update)
        )
        row = result.scalar_one_or_none()
        return _proposal_from_row(row) if row is not None else None

    async def save(self, proposal: ActionProposal) -> None:
        await self._session.merge(_proposal_to_row(proposal))

    async def get_pending_for_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> ActionProposal | None:
        statement = select(ActionProposalRow).where(
            ActionProposalRow.tenant_id == tenant_id,
            ActionProposalRow.run_id == run_id,
            ActionProposalRow.incident_id == incident_id,
            ActionProposalRow.status == ProposalStatus.PENDING_APPROVAL.value,
        )
        result = await self._session.execute(
            _maybe_lock(statement, self._lock_for_update)
        )
        row = result.scalars().first()
        return _proposal_from_row(row) if row is not None else None


class SqlAlchemyApprovalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, approval: Approval) -> None:
        self._session.add(_approval_to_row(approval))

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> Approval | None:
        result = await self._session.execute(
            select(ApprovalRow).where(
                ApprovalRow.tenant_id == tenant_id,
                ApprovalRow.run_id == run_id,
                ApprovalRow.proposal_id == proposal_id,
            )
        )
        row = result.scalar_one_or_none()
        return _approval_from_row(row) if row is not None else None


class SqlAlchemyExecutedActionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, action: ExecutedAction) -> None:
        self._session.add(_executed_action_to_row(action))

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> ExecutedAction | None:
        result = await self._session.execute(
            select(ExecutedActionRow).where(
                ExecutedActionRow.tenant_id == tenant_id,
                ExecutedActionRow.run_id == run_id,
                ExecutedActionRow.proposal_id == proposal_id,
            )
        )
        row = result.scalar_one_or_none()
        return _executed_action_from_row(row) if row is not None else None

    async def get_equivalent(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
        device_id: str,
        action_type: ActionType,
    ) -> ExecutedAction | None:
        result = await self._session.execute(
            select(ExecutedActionRow).where(
                ExecutedActionRow.tenant_id == tenant_id,
                ExecutedActionRow.run_id == run_id,
                ExecutedActionRow.incident_id == incident_id,
                ExecutedActionRow.device_id == device_id,
                ExecutedActionRow.action_type == action_type.value,
            )
        )
        row = result.scalar_one_or_none()
        return _executed_action_from_row(row) if row is not None else None


class SqlAlchemyWorkOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, work_order: FieldServiceWorkOrder) -> None:
        self._session.add(_work_order_to_row(work_order))

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> FieldServiceWorkOrder | None:
        result = await self._session.execute(
            select(FieldServiceWorkOrderRow).where(
                FieldServiceWorkOrderRow.tenant_id == tenant_id,
                FieldServiceWorkOrderRow.run_id == run_id,
                FieldServiceWorkOrderRow.proposal_id == proposal_id,
            )
        )
        row = result.scalar_one_or_none()
        return _work_order_from_row(row) if row is not None else None

    async def get_for_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> FieldServiceWorkOrder | None:
        result = await self._session.execute(
            select(FieldServiceWorkOrderRow).where(
                FieldServiceWorkOrderRow.tenant_id == tenant_id,
                FieldServiceWorkOrderRow.run_id == run_id,
                FieldServiceWorkOrderRow.incident_id == incident_id,
            )
        )
        row = result.scalar_one_or_none()
        return _work_order_from_row(row) if row is not None else None
