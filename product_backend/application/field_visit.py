"""Deterministic Scenario 1 field-visit proposal and human decision services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from product_backend.contracts.tools import ProposeFieldVisitRequest, ToolCallContext
from product_backend.domain.enums import (
    ActionType,
    ApprovalDecision,
    DiagnosisCode,
    DiagnosticType,
    IncidentStatus,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.domain.models import (
    ActionProposal,
    Approval,
    ExecutedAction,
    FieldServiceWorkOrder,
)
from product_backend.domain.transitions import (
    PROPOSAL_TRANSITIONS,
    RUN_TRANSITIONS,
    SCENARIO1_INCIDENT_TRANSITIONS,
    can_transition,
)
from product_backend.domain.validators import (
    validate_approval_currentness,
    validate_field_visit_evidence,
)
from product_backend.ports.repositories import (
    ApprovalExecutionUnitOfWork,
    ProposalCreationUnitOfWork,
)
from product_backend.ports.source_systems import CmdbPort, MonitoringPort

from .results import (
    ApprovalDecisionResult,
    ApprovalProcessed,
    OperationFailure,
    ProposalCreated,
    ProposalCreationResult,
)

Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
ProposalUowFactory = Callable[[], ProposalCreationUnitOfWork]
ApprovalUowFactory = Callable[[], ApprovalExecutionUnitOfWork]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix.upper()}-{uuid4().hex}"


def _failure(code: ErrorCode, message: str, reason: str) -> OperationFailure:
    return OperationFailure(
        ok=False,
        error=DomainError(
            code=code,
            message=message,
            details=(("reason", reason),),
        ),
    )


class FieldVisitProposalService:
    def __init__(
        self,
        uow_factory: ProposalUowFactory,
        *,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._id_factory = id_factory

    async def create(
        self,
        context: ToolCallContext,
        request: ProposeFieldVisitRequest,
    ) -> ProposalCreationResult:
        now = self._clock()

        if not request.rationale.strip():
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Field-visit proposal is invalid.",
                "empty_rationale",
            )
        if request.diagnosis is not DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE:
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Field-visit proposal is invalid.",
                "unsupported_diagnosis",
            )
        if not request.evidence_ids or len(set(request.evidence_ids)) != len(
            request.evidence_ids
        ):
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Field-visit proposal is invalid.",
                "missing_or_duplicate_evidence_ids",
            )

        async with self._uow_factory() as uow:
            run = await uow.runs.get(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
            )
            if run is None:
                return _failure(
                    ErrorCode.CONTEXT_MISMATCH,
                    "Run context is not valid.",
                    "run_not_found",
                )
            if run.status is not RunStatus.ACTIVE or not can_transition(
                RUN_TRANSITIONS,
                run.status,
                RunStatus.WAITING_APPROVAL,
            ):
                return _failure(
                    ErrorCode.INVALID_STATE_TRANSITION,
                    "Run cannot enter approval wait state.",
                    "run_not_active",
                )

            incident = await uow.incidents.get(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                incident_id=request.incident_id,
            )
            if incident is None:
                return _failure(
                    ErrorCode.INCIDENT_NOT_FOUND,
                    "Incident was not found in the current run.",
                    "incident_not_found",
                )
            if incident.status is not IncidentStatus.OPEN:
                return _failure(
                    ErrorCode.INVALID_PROPOSAL,
                    "Field-visit proposal is invalid.",
                    "incident_not_open",
                )
            if incident.reported_device_id != request.device_id:
                return _failure(
                    ErrorCode.INVALID_PROPOSAL,
                    "Field-visit proposal is invalid.",
                    "device_not_owned_by_incident",
                )

            existing = await uow.proposals.get_pending_for_incident(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                incident_id=request.incident_id,
            )
            if existing is not None:
                return _failure(
                    ErrorCode.INVALID_PROPOSAL,
                    "An equivalent proposal is already awaiting approval.",
                    "duplicate_pending_proposal",
                )

            evidence = await uow.evidence.get_many(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                evidence_ids=request.evidence_ids,
            )
            evidence_error = validate_field_visit_evidence(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                incident=incident,
                device_id=request.device_id,
                diagnosis=request.diagnosis,
                action_type=ActionType.ONSITE_FIELD_VISIT,
                evidence_ids=request.evidence_ids,
                evidence=evidence,
                now=now,
            )
            if evidence_error:
                return OperationFailure(ok=False, error=evidence_error)

            proposal = ActionProposal(
                proposal_id=self._id_factory("proposal"),
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                incident_id=request.incident_id,
                device_id=request.device_id,
                diagnosis=request.diagnosis,
                action_type=ActionType.ONSITE_FIELD_VISIT,
                evidence_ids=request.evidence_ids,
                rationale=request.rationale,
                status=ProposalStatus.PENDING_APPROVAL,
                created_at=now,
                updated_at=now,
            )

            await uow.proposals.add(proposal)
            await uow.runs.save(
                replace(
                    run,
                    status=RunStatus.WAITING_APPROVAL,
                    updated_at=now,
                )
            )
            await uow.commit()
            return ProposalCreated(ok=True, proposal=proposal)


class FieldVisitApprovalService:
    def __init__(
        self,
        uow_factory: ApprovalUowFactory,
        *,
        cmdb: CmdbPort,
        monitoring: MonitoringPort,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._uow_factory = uow_factory
        self._cmdb = cmdb
        self._monitoring = monitoring
        self._clock = clock
        self._id_factory = id_factory

    async def decide(
        self,
        context: ToolCallContext,
        *,
        proposal_id: str,
        decision: ApprovalDecision,
        decided_by: str,
    ) -> ApprovalDecisionResult:
        now = self._clock()

        if not isinstance(decision, ApprovalDecision):
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Approval decision is invalid.",
                "invalid_decision",
            )
        if not decided_by.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Human actor is required.",
                "empty_decided_by",
            )

        async with self._uow_factory() as uow:
            proposal = await uow.proposals.get(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal_id,
            )
            if proposal is None:
                return _failure(
                    ErrorCode.PROPOSAL_NOT_FOUND,
                    "Proposal was not found in the current run.",
                    "proposal_not_found",
                )

            existing_approval = await uow.approvals.get_for_proposal(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal_id,
            )
            if existing_approval is not None:
                if existing_approval.decision is not decision:
                    return _failure(
                        ErrorCode.PROPOSAL_NOT_PENDING,
                        "Proposal already has a different human decision.",
                        "decision_conflict",
                    )

                incident = await uow.incidents.get(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    incident_id=proposal.incident_id,
                )
                if incident is None:
                    return _failure(
                        ErrorCode.INCIDENT_NOT_FOUND,
                        "Incident for stored approval result is missing.",
                        "incident_not_found",
                    )

                return ApprovalProcessed(
                    ok=True,
                    approval=existing_approval,
                    proposal=proposal,
                    incident=incident,
                    executed_action=await uow.executed_actions.get_for_proposal(
                        tenant_id=context.tenant_id,
                        run_id=context.run_id,
                        proposal_id=proposal_id,
                    ),
                    work_order=await uow.work_orders.get_for_proposal(
                        tenant_id=context.tenant_id,
                        run_id=context.run_id,
                        proposal_id=proposal_id,
                    ),
                    replayed=True,
                )

            if proposal.status is not ProposalStatus.PENDING_APPROVAL:
                return _failure(
                    ErrorCode.PROPOSAL_NOT_PENDING,
                    "Proposal is no longer pending approval.",
                    "proposal_not_pending",
                )

            run = await uow.runs.get(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
            )
            if run is None:
                return _failure(
                    ErrorCode.CONTEXT_MISMATCH,
                    "Run context is not valid.",
                    "run_not_found",
                )
            if run.status is not RunStatus.WAITING_APPROVAL or not can_transition(
                RUN_TRANSITIONS,
                run.status,
                RunStatus.ACTIVE,
            ):
                return _failure(
                    ErrorCode.INVALID_STATE_TRANSITION,
                    "Run is not waiting for this human decision.",
                    "run_not_waiting_approval",
                )

            incident = await uow.incidents.get(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                incident_id=proposal.incident_id,
            )
            if incident is None:
                return _failure(
                    ErrorCode.INCIDENT_NOT_FOUND,
                    "Incident was not found in the current run.",
                    "incident_not_found",
                )

            approval = Approval(
                approval_id=self._id_factory("approval"),
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal_id,
                decision=decision,
                decided_at=now,
                decided_by=decided_by,
            )

            if decision is ApprovalDecision.REJECTED:
                if not can_transition(
                    PROPOSAL_TRANSITIONS,
                    proposal.status,
                    ProposalStatus.REJECTED,
                ):
                    return _failure(
                        ErrorCode.INVALID_STATE_TRANSITION,
                        "Proposal cannot be rejected from its current state.",
                        "invalid_proposal_transition",
                    )

                updated_proposal = replace(
                    proposal,
                    status=ProposalStatus.REJECTED,
                    updated_at=now,
                )
                await uow.approvals.add(approval)
                await uow.proposals.save(updated_proposal)
                await uow.runs.save(
                    replace(
                        run,
                        status=RunStatus.ACTIVE,
                        updated_at=now,
                    )
                )
                await uow.commit()
                return ApprovalProcessed(
                    ok=True,
                    approval=approval,
                    proposal=updated_proposal,
                    incident=incident,
                    executed_action=None,
                    work_order=None,
                )

            current_topology = await self._cmdb.get_device(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                device_id=proposal.device_id,
            )
            current_diagnostic = None
            if current_topology is not None:
                current_diagnostic = await self._monitoring.run_diagnostic(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    diagnostic_type=DiagnosticType.ACCESS_LINK,
                    target_id=current_topology.attachment_id,
                )

            currentness_error = validate_approval_currentness(
                proposal=proposal,
                incident=incident,
                current_topology=current_topology,
                current_diagnostic=current_diagnostic,
            )
            equivalent_action = await uow.executed_actions.get_equivalent(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                incident_id=proposal.incident_id,
                device_id=proposal.device_id,
                action_type=proposal.action_type,
            )
            existing_work_order = await uow.work_orders.get_for_incident(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                incident_id=proposal.incident_id,
            )

            if (
                currentness_error is not None
                or equivalent_action is not None
                or existing_work_order is not None
            ):
                if not can_transition(
                    PROPOSAL_TRANSITIONS,
                    proposal.status,
                    ProposalStatus.STALE,
                ):
                    return _failure(
                        ErrorCode.INVALID_STATE_TRANSITION,
                        "Proposal cannot become stale from its current state.",
                        "invalid_proposal_transition",
                    )

                updated_proposal = replace(
                    proposal,
                    status=ProposalStatus.STALE,
                    updated_at=now,
                )
                await uow.approvals.add(approval)
                await uow.proposals.save(updated_proposal)
                await uow.runs.save(
                    replace(
                        run,
                        status=RunStatus.ACTIVE,
                        updated_at=now,
                    )
                )
                await uow.commit()
                return ApprovalProcessed(
                    ok=True,
                    approval=approval,
                    proposal=updated_proposal,
                    incident=incident,
                    executed_action=None,
                    work_order=None,
                )

            if not can_transition(
                PROPOSAL_TRANSITIONS,
                proposal.status,
                ProposalStatus.EXECUTED,
            ):
                return _failure(
                    ErrorCode.INVALID_STATE_TRANSITION,
                    "Proposal cannot execute from its current state.",
                    "invalid_proposal_transition",
                )
            if not can_transition(
                SCENARIO1_INCIDENT_TRANSITIONS,
                incident.status,
                IncidentStatus.ESCALATED,
            ):
                return _failure(
                    ErrorCode.INVALID_STATE_TRANSITION,
                    "Incident cannot be escalated from its current state.",
                    "invalid_incident_transition",
                )

            action = ExecutedAction(
                action_id=self._id_factory("action"),
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal_id,
                incident_id=proposal.incident_id,
                device_id=proposal.device_id,
                action_type=proposal.action_type,
                executed_at=now,
            )
            work_order = FieldServiceWorkOrder(
                work_order_id=self._id_factory("workorder"),
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal_id,
                incident_id=proposal.incident_id,
                device_id=proposal.device_id,
                site_id=current_topology.site_id,
                attachment_id=current_topology.attachment_id,
                switch_id=current_topology.expected_switch_id,
                port_id=current_topology.expected_port_id,
                created_at=now,
            )
            updated_proposal = replace(
                proposal,
                status=ProposalStatus.EXECUTED,
                updated_at=now,
            )
            updated_incident = replace(
                incident,
                status=IncidentStatus.ESCALATED,
                updated_at=now,
            )

            await uow.approvals.add(approval)
            await uow.executed_actions.add(action)
            await uow.work_orders.add(work_order)
            await uow.proposals.save(updated_proposal)
            await uow.incidents.save(updated_incident)
            await uow.runs.save(
                replace(
                    run,
                    status=RunStatus.ACTIVE,
                    updated_at=now,
                )
            )
            await uow.commit()

            return ApprovalProcessed(
                ok=True,
                approval=approval,
                proposal=updated_proposal,
                incident=updated_incident,
                executed_action=action,
                work_order=work_order,
            )
