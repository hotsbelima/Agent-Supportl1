"""Phase 7D persisted Scenario 2 Major Incident HITL state.

Revision ID: 20261006_0006
Revises: 20261006_0005
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261006_0006"
down_revision: Union[str, Sequence[str], None] = "20261006_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "major_incident_proposals",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_key", sa.String(length=128), nullable=False),
        sa.Column("service_key", sa.String(length=128), nullable=False),
        sa.Column(
            "affected_site_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("dependency_id", sa.String(length=128), nullable=False),
        sa.Column("dependency_name", sa.String(length=256), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column(
            "evidence_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_type = 'CREATE_MAJOR_INCIDENT'",
            name="ck_major_incident_proposals_action_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING_APPROVAL', 'REJECTED', 'STALE', 'EXECUTED')",
            name="ck_major_incident_proposals_status_known",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_major_incident_proposals_run",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "proposal_id"),
    )
    op.create_index(
        "uq_major_incident_proposals_pending_equivalent",
        "major_incident_proposals",
        ["tenant_id", "service_key", "correlation_key", "dependency_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING_APPROVAL'"),
    )

    op.create_table(
        "major_incident_approvals",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("approval_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=256), nullable=False),
        sa.CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED')",
            name="ck_major_incident_approvals_decision_known",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "major_incident_proposals.tenant_id",
                "major_incident_proposals.run_id",
                "major_incident_proposals.proposal_id",
            ],
            name="fk_major_incident_approvals_proposal",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "approval_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_major_incident_approvals_proposal",
        ),
    )

    op.create_table(
        "major_incidents",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("major_incident_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_key", sa.String(length=128), nullable=False),
        sa.Column("service_key", sa.String(length=128), nullable=False),
        sa.Column(
            "affected_site_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("dependency_id", sa.String(length=128), nullable=False),
        sa.Column("dependency_name", sa.String(length=256), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status = 'OPEN'",
            name="ck_major_incidents_status_known",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "major_incident_proposals.tenant_id",
                "major_incident_proposals.run_id",
                "major_incident_proposals.proposal_id",
            ],
            name="fk_major_incidents_proposal",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "major_incident_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_major_incidents_proposal",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "service_key",
            "correlation_key",
            "dependency_id",
            name="uq_major_incidents_equivalent",
        ),
    )

    op.create_table(
        "major_incident_executions",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("execution_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("major_incident_id", sa.String(length=128), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_type = 'CREATE_MAJOR_INCIDENT'",
            name="ck_major_incident_executions_action_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "major_incident_proposals.tenant_id",
                "major_incident_proposals.run_id",
                "major_incident_proposals.proposal_id",
            ],
            name="fk_major_incident_executions_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "major_incident_id"],
            [
                "major_incidents.tenant_id",
                "major_incidents.run_id",
                "major_incidents.major_incident_id",
            ],
            name="fk_major_incident_executions_major_incident",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "execution_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_major_incident_executions_proposal",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "major_incident_id",
            name="uq_major_incident_executions_major_incident",
        ),
    )


def downgrade() -> None:
    op.drop_table("major_incident_executions")
    op.drop_table("major_incidents")
    op.drop_table("major_incident_approvals")
    op.drop_index(
        "uq_major_incident_proposals_pending_equivalent",
        table_name="major_incident_proposals",
    )
    op.drop_table("major_incident_proposals")
