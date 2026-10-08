"""Isolate public demo equivalence while preserving tenant-wide default guards."""

from alembic import op
import sqlalchemy as sa

revision = "20261009_0009"
down_revision = "20261008_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("major_incident_proposals", "major_incidents"):
        op.add_column(table, sa.Column(
            "deduplication_scope", sa.String(128), nullable=False, server_default="",
        ))
    op.drop_index("uq_major_incident_proposals_pending_equivalent",
                  table_name="major_incident_proposals")
    op.create_index("uq_major_incident_proposals_pending_equivalent",
                    "major_incident_proposals",
                    ["tenant_id", "deduplication_scope", "service_key", "correlation_key", "dependency_id"],
                    unique=True, postgresql_where=sa.text("status = 'PENDING_APPROVAL'"))
    op.drop_constraint("uq_major_incidents_equivalent", "major_incidents", type_="unique")
    op.create_unique_constraint("uq_major_incidents_equivalent", "major_incidents",
                                ["tenant_id", "service_key", "correlation_key", "dependency_id", "deduplication_scope"])


def downgrade() -> None:
    # Refuse an unsafe rollback if independent demo runs now contain equivalent
    # records. PostgreSQL will reject recreating the old unique keys atomically.
    op.drop_constraint("uq_major_incidents_equivalent", "major_incidents", type_="unique")
    op.create_unique_constraint("uq_major_incidents_equivalent", "major_incidents",
                                ["tenant_id", "service_key", "correlation_key", "dependency_id"])
    op.drop_index("uq_major_incident_proposals_pending_equivalent",
                  table_name="major_incident_proposals")
    op.create_index("uq_major_incident_proposals_pending_equivalent", "major_incident_proposals",
                    ["tenant_id", "service_key", "correlation_key", "dependency_id"],
                    unique=True, postgresql_where=sa.text("status = 'PENDING_APPROVAL'"))
    for table in ("major_incident_proposals", "major_incidents"):
        op.drop_column(table, "deduplication_scope")
