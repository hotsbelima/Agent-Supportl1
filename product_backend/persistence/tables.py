"""SQLAlchemy table mappings for Phase 4A product-owned state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class IncidentRow(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_incidents_run",
        ),
        Index(
            "ix_incidents_tenant_run_device",
            "tenant_id",
            "run_id",
            "reported_device_id",
        ),
        Index(
            "ix_incidents_tenant_run_site",
            "tenant_id",
            "run_id",
            "site_id",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reported_device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symptom: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EvidenceRow(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_evidence_run",
        ),
        Index(
            "ix_evidence_entity_ids_gin",
            "entity_ids",
            postgresql_using="gin",
        ),
        Index(
            "ix_evidence_tenant_run_captured",
            "tenant_id",
            "run_id",
            "captured_at",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    entity_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    facts: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ActionProposalRow(Base):
    __tablename__ = "action_proposals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_action_proposals_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "incident_id"],
            [
                "incidents.tenant_id",
                "incidents.run_id",
                "incidents.incident_id",
            ],
            name="fk_action_proposals_incident",
        ),
        Index(
            "uq_action_proposals_pending_incident",
            "tenant_id",
            "run_id",
            "incident_id",
            unique=True,
            postgresql_where=text("status = 'PENDING_APPROVAL'"),
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    diagnosis: Mapped[str] = mapped_column(String(64), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "action_proposals.tenant_id",
                "action_proposals.run_id",
                "action_proposals.proposal_id",
            ],
            name="fk_approvals_proposal",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_approvals_proposal",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decided_by: Mapped[str] = mapped_column(String(256), nullable=False)


class ExecutedActionRow(Base):
    __tablename__ = "executed_actions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "action_proposals.tenant_id",
                "action_proposals.run_id",
                "action_proposals.proposal_id",
            ],
            name="fk_executed_actions_proposal",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "incident_id"],
            [
                "incidents.tenant_id",
                "incidents.run_id",
                "incidents.incident_id",
            ],
            name="fk_executed_actions_incident",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_executed_actions_proposal",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "incident_id",
            "device_id",
            "action_type",
            name="uq_executed_actions_equivalent",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    incident_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class FieldServiceWorkOrderRow(Base):
    __tablename__ = "field_service_work_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "proposal_id"],
            [
                "action_proposals.tenant_id",
                "action_proposals.run_id",
                "action_proposals.proposal_id",
            ],
            name="fk_work_orders_proposal",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "incident_id"],
            [
                "incidents.tenant_id",
                "incidents.run_id",
                "incidents.incident_id",
            ],
            name="fk_work_orders_incident",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "proposal_id",
            name="uq_work_orders_proposal",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "incident_id",
            name="uq_work_orders_incident",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    work_order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    incident_id: Mapped[str] = mapped_column(String(128), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    site_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attachment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    switch_id: Mapped[str] = mapped_column(String(128), nullable=False)
    port_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ApplicationEventRow(Base):
    """Persisted safe event record; lifecycle semantics are added in Phase 4B."""

    __tablename__ = "application_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_application_events_run",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "event_id",
            name="uq_application_events_event_id",
        ),
        CheckConstraint("seq > 0", name="ck_application_events_seq_positive"),
        CheckConstraint(
            "event_type IN ("
            "'simulation.started', "
            "'external.signal', "
            "'tool.started', "
            "'tool.finished', "
            "'finding.recorded', "
            "'proposal.created', "
            "'approval.decided', "
            "'action.executed', "
            "'run.status_changed'"
            ")",
            name="ck_application_events_type_known",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class ApplicationOutboxRow(Base):
    """Legacy reserved outbox table; no generic producer exists in Phase 6A.

    The applied Phase 4 schema is intentionally left intact. Phase 6C may add
    a dedicated durable approval-to-ADK-resume producer/consumer after the
    required invocation/function-call correlation exists.
    """

    __tablename__ = "application_outbox"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["runs.tenant_id", "runs.run_id"],
            name="fk_application_outbox_run",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id", "event_seq"],
            [
                "application_events.tenant_id",
                "application_events.run_id",
                "application_events.seq",
            ],
            name="fk_application_outbox_event",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "event_seq",
            name="uq_application_outbox_event",
        ),
        Index(
            "ix_application_outbox_pending",
            "delivered_at",
            "created_at",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    outbox_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
