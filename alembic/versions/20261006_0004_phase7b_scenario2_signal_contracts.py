"""Phase 7B Scenario 2 persisted operational fact contracts.

Revision ID: 20261006_0004
Revises: 20261005_0003
Create Date: 2026-10-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20261006_0004"
down_revision: Union[str, Sequence[str], None] = "20261005_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_incidents",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("incident_id", sa.String(length=128), nullable=False),
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("service_key", sa.String(length=128), nullable=False),
        sa.Column("symptom_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('OPEN', 'ESCALATED', 'RESOLVED')",
            name="ck_service_incidents_status_known",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_service_incidents_run",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "incident_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "site_id",
            "service_key",
            name="uq_service_incidents_run_site_service",
        ),
    )
    op.create_index(
        "ix_service_incidents_tenant_run_site",
        "service_incidents",
        ["tenant_id", "run_id", "site_id"],
    )

    op.create_table(
        "operational_signals",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("signal_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("service_key", sa.String(length=128), nullable=False),
        sa.Column("symptom_key", sa.String(length=128), nullable=False),
        sa.Column("source_ref", sa.String(length=256), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "safe_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("incident_id", sa.String(length=128), nullable=True),
        sa.CheckConstraint(
            "source IN ('MONITORING', 'ITSM')",
            name="ck_operational_signals_source_known",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_operational_signals_run",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id", "incident_id"],
            [
                "service_incidents.tenant_id",
                "service_incidents.run_id",
                "service_incidents.incident_id",
            ],
            name="fk_operational_signals_service_incident",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "run_id", "signal_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "run_id",
            "source",
            "source_ref",
            name="uq_operational_signals_source_identity",
        ),
    )
    op.create_index(
        "ix_operational_signals_tenant_run_received",
        "operational_signals",
        ["tenant_id", "run_id", "received_at"],
    )
    op.create_index(
        "ix_operational_signals_tenant_run_site",
        "operational_signals",
        ["tenant_id", "run_id", "site_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_signals_tenant_run_site",
        table_name="operational_signals",
    )
    op.drop_index(
        "ix_operational_signals_tenant_run_received",
        table_name="operational_signals",
    )
    op.drop_table("operational_signals")

    op.drop_index(
        "ix_service_incidents_tenant_run_site",
        table_name="service_incidents",
    )
    op.drop_table("service_incidents")
