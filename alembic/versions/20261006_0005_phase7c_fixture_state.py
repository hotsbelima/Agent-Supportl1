"""Phase 7C persisted Scenario 2 fixture state.

Revision ID: 20261006_0005
Revises: 20261006_0004
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261006_0005"
down_revision: Union[str, Sequence[str], None] = "20261006_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenario2_fixture_states",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("dependency_status", sa.String(length=64), nullable=False),
        sa.Column(
            "matching_major_incident_id",
            sa.String(length=128),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dependency_status IN ('HEALTHY', 'DEGRADED', 'DOWN')",
            name="ck_scenario2_fixture_dependency_status_known",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_scenario2_fixture_states_run",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id"),
    )


def downgrade() -> None:
    op.drop_table("scenario2_fixture_states")
