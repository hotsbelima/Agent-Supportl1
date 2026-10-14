"""Track browser activity so abandoned runs stop dispatching agent work.

Revision ID: 20261008_0008
Revises: 20261008_0007
Create Date: 2026-10-08
"""

from alembic import op
import sqlalchemy as sa


revision = "20261008_0008"
down_revision = "20261008_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("client_last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("dispatch_abandoned_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "dispatch_abandoned_at")
    op.drop_column("runs", "client_last_seen_at")
