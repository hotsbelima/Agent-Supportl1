"""Phase 4A initial product persistence schema.

Revision ID: 20261004_0001
Revises:
Create Date: 2026-10-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261004_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "run_id"),
    )

    op.create_table(
        "incidents",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("reported_device_id", sa.String(length=128), nullable=False),
        sa.Column("symptom", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_incidents_run",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "incident_id"),
    )
    op.create_index(
        "ix_incidents_tenant_run_device",
        "incidents",
        ["tenant_id", "run_id", "reported_device_id"],
    )
    op.create_index(
        "ix_incidents_tenant_run_site",
        "incidents",
        ["tenant_id", "run_id", "site_id"],
    )

    op.create_table(
        "evidence",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "entity_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "facts",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_evidence_run",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "evidence_id"),
    )
    op.create_index(
        "ix_evidence_entity_ids_gin",
        "evidence",
        ["entity_ids"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_evidence_tenant_run_captured",
        "evidence",
        ["tenant_id", "run_id", "captured_at"],
    )

    op.create_table(
        "action_proposals",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("diagnosis", sa.String(length=64), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column(
            "evidence_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_action_proposals_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "incident_id"],
            [
                "incidents.tenant_id",
                "incidents.run_id",
                "incidents.incident_id",
            ],
            name="fk_action_proposals_incident",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "proposal_id"),
    )
    op.create_index(
        "uq_action_proposals_pending_incident",
        "action_proposals",
        ["tenant_id", "run_id", "incident_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING_APPROVAL'"),
    )

    op.create_table(
        "approvals",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("approval_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=256), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "action_proposals.tenant_id",
                "action_proposals.run_id",
                "action_proposals.proposal_id",
            ],
            name="fk_approvals_proposal",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "approval_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_approvals_proposal",
        ),
    )

    op.create_table(
        "executed_actions",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("action_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "action_proposals.tenant_id",
                "action_proposals.run_id",
                "action_proposals.proposal_id",
            ],
            name="fk_executed_actions_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "incident_id"],
            [
                "incidents.tenant_id",
                "incidents.run_id",
                "incidents.incident_id",
            ],
            name="fk_executed_actions_incident",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "action_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_executed_actions_proposal",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "incident_id",
            "device_id",
            "action_type",
            name="uq_executed_actions_equivalent",
        ),
    )

    op.create_table(
        "field_service_work_orders",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("work_order_id", sa.String(length=128), nullable=False),
        sa.Column("proposal_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("attachment_id", sa.String(length=128), nullable=False),
        sa.Column("switch_id", sa.String(length=128), nullable=False),
        sa.Column("port_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "action_proposals.tenant_id",
                "action_proposals.run_id",
                "action_proposals.proposal_id",
            ],
            name="fk_work_orders_proposal",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "incident_id"],
            [
                "incidents.tenant_id",
                "incidents.run_id",
                "incidents.incident_id",
            ],
            name="fk_work_orders_incident",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "work_order_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_work_orders_proposal",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "incident_id",
            name="uq_work_orders_incident",
        ),
    )

    op.create_table(
        "application_events",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_application_events_run",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "seq"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "event_id",
            name="uq_application_events_event_id",
        ),
    )

    op.create_table(
        "application_outbox",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("outbox_id", sa.String(length=128), nullable=False),
        sa.Column("event_seq", sa.BigInteger(), nullable=True),
        sa.Column("topic", sa.String(length=128), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_application_outbox_run",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "outbox_id"),
    )
    op.create_index(
        "ix_application_outbox_pending",
        "application_outbox",
        ["delivered_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("application_outbox")
    op.drop_table("application_events")
    op.drop_table("field_service_work_orders")
    op.drop_table("executed_actions")
    op.drop_table("approvals")
    op.drop_table("action_proposals")
    op.drop_table("evidence")
    op.drop_table("incidents")
    op.drop_table("runs")
