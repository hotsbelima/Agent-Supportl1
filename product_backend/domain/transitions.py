"""State-transition contracts for Scenario 1.

This module declares allowed transitions only. Phase 3B will implement the
business operations that apply them after validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

from .enums import IncidentStatus, ProposalStatus, RunStatus

S = TypeVar("S")

RUN_TRANSITIONS: Mapping[RunStatus, frozenset[RunStatus]] = {
    RunStatus.CREATED: frozenset({RunStatus.ACTIVE, RunStatus.FAILED}),
    RunStatus.ACTIVE: frozenset(
        {RunStatus.WAITING_APPROVAL, RunStatus.COMPLETED, RunStatus.FAILED}
    ),
    RunStatus.WAITING_APPROVAL: frozenset(
        {RunStatus.ACTIVE, RunStatus.COMPLETED, RunStatus.FAILED}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
}


# Scenario 1 explicitly escalates after a valid approved field visit and must
# not mark the incident RESOLVED merely because a work order was created.
SCENARIO1_INCIDENT_TRANSITIONS: Mapping[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.OPEN: frozenset({IncidentStatus.ESCALATED}),
    IncidentStatus.ESCALATED: frozenset(),
    IncidentStatus.RESOLVED: frozenset(),
}


PROPOSAL_TRANSITIONS: Mapping[ProposalStatus, frozenset[ProposalStatus]] = {
    ProposalStatus.PENDING_APPROVAL: frozenset(
        {ProposalStatus.REJECTED, ProposalStatus.STALE, ProposalStatus.EXECUTED}
    ),
    ProposalStatus.REJECTED: frozenset(),
    ProposalStatus.STALE: frozenset(),
    ProposalStatus.EXECUTED: frozenset(),
}


def can_transition(
    transitions: Mapping[S, frozenset[S]], current: S, target: S
) -> bool:
    return target in transitions.get(current, frozenset())
