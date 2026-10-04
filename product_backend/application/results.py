from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from product_backend.domain.errors import DomainError
from product_backend.domain.models import (
    ActionProposal,
    Approval,
    ExecutedAction,
    FieldServiceWorkOrder,
    Incident,
)


@dataclass(frozen=True, slots=True)
class OperationFailure:
    ok: Literal[False]
    error: DomainError


@dataclass(frozen=True, slots=True)
class ProposalCreated:
    ok: Literal[True]
    proposal: ActionProposal


ProposalCreationResult: TypeAlias = ProposalCreated | OperationFailure


@dataclass(frozen=True, slots=True)
class ApprovalProcessed:
    ok: Literal[True]
    approval: Approval
    proposal: ActionProposal
    incident: Incident
    executed_action: ExecutedAction | None
    work_order: FieldServiceWorkOrder | None
    replayed: bool = False


ApprovalDecisionResult: TypeAlias = ApprovalProcessed | OperationFailure
