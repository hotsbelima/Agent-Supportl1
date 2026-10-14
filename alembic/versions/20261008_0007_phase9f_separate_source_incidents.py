"""Phase 9F: keep Scenario 2 source incidents separate.

Revision ID: 20261008_0007
Revises: 20261006_0006
Create Date: 2026-10-08
"""

from alembic import op


revision = "20261008_0007"
down_revision = "20261006_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_service_incidents_run_site_service",
        "service_incidents",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_service_incidents_run_site_service",
        "service_incidents",
        ["tenant_id", "run_id", "site_id", "service_key"],
    )
