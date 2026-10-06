"""Application-facing contracts for Scenario 1 run lifecycle/state."""

from __future__ import annotations

from dataclasses import dataclass

from product_backend.domain.models import (
    ActionProposal,
    Approval,
    Evidence,
    ExecutedAction,
    FieldServiceWorkOrder,
    Incident,
    Run,
)


@dataclass(frozen=True, slots=True)
class Scenario1Bootstrap:
    scenario_id: str
    incident_id: str
    site_id: str
    reported_device_id: str
    symptom: str
    service_key: str | None = None
    symptom_key: str | None = None


@dataclass(frozen=True, slots=True)
class Scenario1RunStarted:
    run: Run
    incident: Incident


@dataclass(frozen=True, slots=True)
class RunStateSnapshot:
    run: Run
    incidents: tuple[Incident, ...]
    evidence: tuple[Evidence, ...]
    proposals: tuple[ActionProposal, ...]
    approvals: tuple[Approval, ...]
    executed_actions: tuple[ExecutedAction, ...]
    work_orders: tuple[FieldServiceWorkOrder, ...]
    latest_event_seq: int


__all__ = [
    "RunStateSnapshot",
    "Scenario1Bootstrap",
    "Scenario1RunStarted",
]
