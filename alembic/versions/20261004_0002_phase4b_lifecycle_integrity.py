"""Phase 4B lifecycle integrity constraints.

Revision ID: 20261004_0002
Revises: 20261004_0001
Create Date: 2026-10-04
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20261004_0002"
down_revision: Union[str, Sequence[str], None] = "20261004_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_application_events_seq_positive",
        "application_events",
        "seq > 0",
    )
    op.create_foreign_key(
        "fk_application_outbox_event",
        "application_outbox",
        "application_events",
        ["tenant_id", "run_id", "event_seq"],
        ["tenant_id", "run_id", "seq"],
    )
    op.create_unique_constraint(
        "uq_application_outbox_event",
        "application_outbox",
        ["tenant_id", "run_id", "event_seq"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_application_outbox_event",
        "application_outbox",
        type_="unique",
    )
    op.drop_constraint(
        "fk_application_outbox_event",
        "application_outbox",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_application_events_seq_positive",
        "application_events",
        type_="check",
    )
