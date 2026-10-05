"""Product application semantics for Scenario 2 Major Incident flow.

Phase 7B defines deterministic Product behavior without ADK wiring or database
implementations. Human decisions remain Product operations.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from product_backend.contracts.scenario2_tools import ProposeMajorIncidentRequest
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import (
    ApprovalDecision,
    EvidenceSourceType,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.domain.models import Evidence
from product_backend.domain.scenario2 import (
    DependencyKind,
    MajorIncidentApproval,
    MajorIncidentExecution,
    MajorIncidentProposal,
    MajorIncidentRecord,
    MajorIncidentStatus,
    Scenario2ActionType,
    ServiceDependencyMappingSnapshot,
)
from product_backend.domain.transitions import (
    PROPOSAL_TRANSITIONS,
    RUN_TRANSITIONS,
    can_transition,
)
from product_backend.domain.validators_scenario2 import (
    validate_major_incident_approval_currentness,
    validate_major_incident_proposal_evidence,
)
from product_backend.ports.scenario2 import (
    Scenario2ApprovalUnitOfWork,
    Scenario2ProposalUnitOfWork,
)
from product_backend.ports.scenario2_sources import (
    ExternalDependencyStatusPort,
    LocalServiceHealthPort,
    MajorIncidentDirectoryPort,
)

from .scenario2_results import (
    MajorIncidentDecisionProcessed,
    MajorIncidentDecisionResult,
    MajorIncidentProposalCreated,
    MajorIncidentProposalResult,
    Scenario2OperationFailure,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
ProposalUowFactory = Callable[[], Scenario2ProposalUnitOfWork]
ApprovalUowFactory = Callable[[], Scenario2ApprovalUnitOfWork]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix.upper()}-{uuid4().hex}"


def _failure(
    code: ErrorCode,
    message: str,
    reason: str,
    *,
    retryable: bool = False,
) -> Scenario2OperationFailure:
    return Scenario2OperationFailure(
        ok=False,
        error=DomainError(
            code=code,
            message=message,
            retryable=retryable,
            details=(("reason", reason),),
        ),
    )


def _dependency_name_from_evidence(
    *,
    request: ProposeMajorIncidentRequest,
    evidence: tuple[Evidence, ...],
) -> str | None:
    names = {
        item.payload.dependency_name
        for item in evidence
        if (
            item.source_type is EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING
            and isinstance(item.payload, ServiceDependencyMappingSnapshot)
            and item.payload.service_key == request.service_key
            and item.payload.dependency_id == request.dependency_id
            and item.payload.dependency_kind is DependencyKind.EXTERNAL_PROVIDER
            and item.payload.dependency_name.strip()
        )
    }
    if len(names) != 1:
        return None
    return next(iter(names))


class MajorIncidentProposalService:
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
        request: ProposeMajorIncidentRequest,
    ) -> MajorIncidentProposalResult:
        now = self._clock()

        if not request.correlation_key.strip():
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Major Incident proposal is invalid.",
                "missing_correlation_key",
            )
        if not request.service_key.strip():
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Major Incident proposal is invalid.",
                "missing_service_key",
            )
        if not request.dependency_id.strip():
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Major Incident proposal is invalid.",
                "missing_dependency_id",
            )
        if len(request.affected_site_ids) < 2:
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Major Incident requires evidence from multiple sites.",
                "insufficient_cross_site_evidence",
            )
        if len(set(request.affected_site_ids)) != len(request.affected_site_ids):
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Major Incident proposal is invalid.",
                "duplicate_affected_site",
            )
        if not request.evidence_ids or len(set(request.evidence_ids)) != len(
            request.evidence_ids
        ):
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Major Incident proposal is invalid.",
                "missing_or_duplicate_evidence_ids",
            )
        if not request.summary.strip() or not request.rationale.strip():
            return _failure(
                ErrorCode.INVALID_PROPOSAL,
                "Major Incident proposal is invalid.",
                "missing_summary_or_rationale",
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

            existing_pending = (
                await uow.major_incident_proposals.get_pending_equivalent(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    correlation_key=request.correlation_key,
                    dependency_id=request.dependency_id,
                )
            )
            if existing_pending is not None:
                return _failure(
                    ErrorCode.INVALID_PROPOSAL,
                    "An equivalent Major Incident proposal is already pending.",
                    "duplicate_pending_major_incident_proposal",
                )

            existing_major_incident = await uow.major_incidents.get_equivalent(
                tenant_id=context.tenant_id,
                correlation_key=request.correlation_key,
                dependency_id=request.dependency_id,
            )
            if existing_major_incident is not None:
                return _failure(
                    ErrorCode.INVALID_PROPOSAL,
                    "An equivalent Major Incident already exists.",
                    "duplicate_major_incident_exists",
                )

            evidence = await uow.evidence.get_many(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                evidence_ids=request.evidence_ids,
            )
            dependency_name = _dependency_name_from_evidence(
                request=request,
                evidence=evidence,
            )
            if dependency_name is None:
                return _failure(
                    ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE,
                    "Major Incident dependency mapping is missing or ambiguous.",
                    "dependency_mapping_not_resolved",
                )

            proposal = MajorIncidentProposal(
                proposal_id=self._id_factory("mi-proposal"),
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                correlation_key=request.correlation_key,
                service_key=request.service_key,
                affected_site_ids=request.affected_site_ids,
                dependency_id=request.dependency_id,
                dependency_name=dependency_name,
                action_type=Scenario2ActionType.CREATE_MAJOR_INCIDENT,
                evidence_ids=request.evidence_ids,
                summary=request.summary,
                rationale=request.rationale,
                status=ProposalStatus.PENDING_APPROVAL,
                created_at=now,
                updated_at=now,
            )

            evidence_error = validate_major_incident_proposal_evidence(
                proposal=proposal,
                evidence=evidence,
                now=now,
            )
            if evidence_error is not None:
                return Scenario2OperationFailure(
                    ok=False,
                    error=evidence_error,
                )

            updated_run = replace(
                run,
                status=RunStatus.WAITING_APPROVAL,
                updated_at=now,
            )
            await uow.major_incident_proposals.add(proposal)
            await uow.runs.save(updated_run)
            await uow.commit()
            return MajorIncidentProposalCreated(
                ok=True,
                proposal=proposal,
            )


class MajorIncidentApprovalService:
    def __init__(
        self,
        uow_factory: ApprovalUowFactory,
        *,
        local_health: LocalServiceHealthPort,
        dependency_status: ExternalDependencyStatusPort,
        major_incident_directory: MajorIncidentDirectoryPort,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._uow_factory = uow_factory
        self._local_health = local_health
        self._dependency_status = dependency_status
        self._major_incident_directory = major_incident_directory
        self._clock = clock
        self._id_factory = id_factory

    async def decide(
        self,
        context: ToolCallContext,
        *,
        proposal_id: str,
        decision: ApprovalDecision,
        decided_by: str,
    ) -> MajorIncidentDecisionResult:
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
            proposal = await uow.major_incident_proposals.get(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal_id,
            )
            if proposal is None:
                return _failure(
                    ErrorCode.PROPOSAL_NOT_FOUND,
                    "Major Incident proposal was not found.",
                    "proposal_not_found",
                )

            existing_approval = await uow.major_incident_approvals.get_for_proposal(
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
                return MajorIncidentDecisionProcessed(
                    ok=True,
                    approval=existing_approval,
                    proposal=proposal,
                    execution=(
                        await uow.major_incident_executions.get_for_proposal(
                            tenant_id=context.tenant_id,
                            run_id=context.run_id,
                            proposal_id=proposal_id,
                        )
                    ),
                    major_incident=(
                        await uow.major_incidents.get_for_proposal(
                            tenant_id=context.tenant_id,
                            run_id=context.run_id,
                            proposal_id=proposal_id,
                        )
                    ),
                    replayed=True,
                )

            if proposal.status is not ProposalStatus.PENDING_APPROVAL:
                return _failure(
                    ErrorCode.PROPOSAL_NOT_PENDING,
                    "Major Incident proposal is no longer pending.",
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

            approval = MajorIncidentApproval(
                approval_id=self._id_factory("mi-approval"),
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
                rejected = replace(
                    proposal,
                    status=ProposalStatus.REJECTED,
                    updated_at=now,
                )
                active_run = replace(
                    run,
                    status=RunStatus.ACTIVE,
                    updated_at=now,
                )
                await uow.major_incident_approvals.add(approval)
                await uow.major_incident_proposals.save(rejected)
                await uow.runs.save(active_run)
                await uow.commit()
                return MajorIncidentDecisionProcessed(
                    ok=True,
                    approval=approval,
                    proposal=rejected,
                    execution=None,
                    major_incident=None,
                )

            proposal_evidence = await uow.evidence.get_many(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                evidence_ids=proposal.evidence_ids,
            )

            equivalent = await uow.major_incidents.get_equivalent(
                tenant_id=context.tenant_id,
                correlation_key=proposal.correlation_key,
                dependency_id=proposal.dependency_id,
            )

            if equivalent is None:
                try:
                    health_results = [
                        await self._local_health.get_local_service_health(
                            tenant_id=context.tenant_id,
                            run_id=context.run_id,
                            site_id=site_id,
                            service_key=proposal.service_key,
                        )
                        for site_id in proposal.affected_site_ids
                    ]
                    current_health = tuple(
                        item for item in health_results if item is not None
                    )
                    if len(current_health) != len(proposal.affected_site_ids):
                        return _failure(
                            ErrorCode.UPSTREAM_UNAVAILABLE,
                            "Current local service health is unavailable.",
                            "local_health_revalidation_unavailable",
                            retryable=True,
                        )
                    current_status = (
                        await self._dependency_status.get_external_dependency_status(
                            tenant_id=context.tenant_id,
                            run_id=context.run_id,
                            dependency_id=proposal.dependency_id,
                        )
                    )
                    if current_status is None:
                        return _failure(
                            ErrorCode.UPSTREAM_UNAVAILABLE,
                            "Current dependency status is unavailable.",
                            "dependency_status_revalidation_unavailable",
                            retryable=True,
                        )
                    current_search = (
                        await self._major_incident_directory.search_major_incidents(
                            tenant_id=context.tenant_id,
                            run_id=context.run_id,
                            correlation_key=proposal.correlation_key,
                            dependency_id=proposal.dependency_id,
                        )
                    )
                except Exception:
                    return _failure(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "Scenario 2 revalidation source is unavailable.",
                        "major_incident_revalidation_unavailable",
                        retryable=True,
                    )

                currentness_error = validate_major_incident_approval_currentness(
                    proposal=proposal,
                    proposal_evidence=proposal_evidence,
                    current_local_health=current_health,
                    current_dependency_status=current_status,
                    current_major_incident_search=current_search,
                    now=now,
                )
            else:
                currentness_error = DomainError(
                    code=ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE,
                    message="An equivalent Major Incident already exists.",
                    details=(("reason", "matching_major_incident_now_exists"),),
                )

            if currentness_error is not None:
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
                stale = replace(
                    proposal,
                    status=ProposalStatus.STALE,
                    updated_at=now,
                )
                active_run = replace(
                    run,
                    status=RunStatus.ACTIVE,
                    updated_at=now,
                )
                await uow.major_incident_approvals.add(approval)
                await uow.major_incident_proposals.save(stale)
                await uow.runs.save(active_run)
                await uow.commit()
                return MajorIncidentDecisionProcessed(
                    ok=True,
                    approval=approval,
                    proposal=stale,
                    execution=None,
                    major_incident=None,
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

            major_incident = MajorIncidentRecord(
                major_incident_id=self._id_factory("major-incident"),
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal.proposal_id,
                correlation_key=proposal.correlation_key,
                service_key=proposal.service_key,
                affected_site_ids=proposal.affected_site_ids,
                dependency_id=proposal.dependency_id,
                dependency_name=proposal.dependency_name,
                summary=proposal.summary,
                status=MajorIncidentStatus.OPEN,
                created_at=now,
            )
            execution = MajorIncidentExecution(
                execution_id=self._id_factory("mi-execution"),
                tenant_id=context.tenant_id,
                run_id=context.run_id,
                proposal_id=proposal.proposal_id,
                action_type=Scenario2ActionType.CREATE_MAJOR_INCIDENT,
                major_incident_id=major_incident.major_incident_id,
                executed_at=now,
            )
            executed = replace(
                proposal,
                status=ProposalStatus.EXECUTED,
                updated_at=now,
            )
            active_run = replace(
                run,
                status=RunStatus.ACTIVE,
                updated_at=now,
            )

            await uow.major_incident_approvals.add(approval)
            await uow.major_incidents.add(major_incident)
            await uow.major_incident_executions.add(execution)
            await uow.major_incident_proposals.save(executed)
            await uow.runs.save(active_run)
            await uow.commit()

            return MajorIncidentDecisionProcessed(
                ok=True,
                approval=approval,
                proposal=executed,
                execution=execution,
                major_incident=major_incident,
            )


__all__ = [
    "MajorIncidentApprovalService",
    "MajorIncidentProposalService",
]
