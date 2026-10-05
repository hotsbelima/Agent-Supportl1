"""Typed application results for Scenario 2 Product operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from product_backend.domain.errors import DomainError
from product_backend.domain.scenario2 import (
    MajorIncidentApproval,
    MajorIncidentExecution,
    MajorIncidentProposal,
    MajorIncidentRecord,
)


@dataclass(frozen=True, slots=True)
class Scenario2OperationFailure:
    ok: Literal[False]
    error: DomainError


@dataclass(frozen=True, slots=True)
class MajorIncidentProposalCreated:
    ok: Literal[True]
    proposal: MajorIncidentProposal


MajorIncidentProposalResult: TypeAlias = (
    MajorIncidentProposalCreated | Scenario2OperationFailure
)


@dataclass(frozen=True, slots=True)
class MajorIncidentDecisionProcessed:
    ok: Literal[True]
    approval: MajorIncidentApproval
    proposal: MajorIncidentProposal
    execution: MajorIncidentExecution | None
    major_incident: MajorIncidentRecord | None
    replayed: bool = False


MajorIncidentDecisionResult: TypeAlias = (
    MajorIncidentDecisionProcessed | Scenario2OperationFailure
)


__all__ = [
    "MajorIncidentDecisionProcessed",
    "MajorIncidentDecisionResult",
    "MajorIncidentProposalCreated",
    "MajorIncidentProposalResult",
    "Scenario2OperationFailure",
]
