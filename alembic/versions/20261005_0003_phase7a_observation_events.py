"""Phase 7A safe Product observation events.

Revision ID: 20261005_0003
Revises: 20261004_0002
Create Date: 2026-10-05
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20261005_0003"
down_revision: Union[str, Sequence[str], None] = "20261004_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _event_type_constraint(include_observation: bool) -> str:
    values = [
        "simulation.started",
        "external.signal",
        "tool.started",
        "tool.finished",
        "finding.recorded",
        "proposal.created",
        "approval.decided",
        "action.executed",
        "run.status_changed",
    ]
    if include_observation:
        values.insert(2, "observation.recorded")
    rendered = ", ".join(f"'{value}'" for value in values)
    return f"event_type IN ({rendered})"


def upgrade() -> None:
    op.drop_constraint(
        "ck_application_events_type_known",
        "application_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_application_events_type_known",
        "application_events",
        _event_type_constraint(include_observation=True),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_application_events_type_known",
        "application_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_application_events_type_known",
        "application_events",
        _event_type_constraint(include_observation=False),
    )
