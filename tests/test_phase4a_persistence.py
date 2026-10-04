from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from product_backend.application.field_visit import (
    FieldVisitApprovalService,
    FieldVisitProposalService,
)
from product_backend.contracts.tools import ProposeFieldVisitRequest, ToolCallContext
from product_backend.domain.enums import (
    ActionType,
    AdminState,
    ApprovalDecision,
    ConfigurationState,
    DiagnosisCode,
    EvidenceSourceType,
    HealthState,
    IncidentSearchScope,
    IncidentStatus,
    OperationalState,
    PortSecurityState,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.models import (
    AccessLinkDiagnosticSnapshot,
    Approval,
    DeviceTopology,
    Evidence,
    Incident,
    IncidentSearchSnapshot,
    KbArticle,
    Run,
    SiteHealthSnapshot,
)
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.repositories import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyIncidentRepository,
    SqlAlchemyProposalRepository,
    SqlAlchemyRunRepository,
)
from product_backend.persistence.serialization import (
    deserialize_evidence_payload,
    serialize_evidence_payload,
)
from product_backend.persistence.tables import (
    ActionProposalRow,
    ApplicationEventRow,
    ApplicationOutboxRow,
    ApprovalRow,
    EvidenceRow,
    ExecutedActionRow,
    FieldServiceWorkOrderRow,
    IncidentRow,
    RunRow,
)
from product_backend.persistence.uow import (
    SqlAlchemyApprovalExecutionUnitOfWork,
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)


T0 = datetime(2026, 10, 4, 18, 0, tzinfo=UTC)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    return normalize_database_url(value)


def _new_db():
    engine = create_engine(DatabaseSettings(url=_database_url()))
    return engine, create_session_factory(engine)


def _suffix() -> str:
    return uuid4().hex[:12]


def _ids(suffix: str) -> dict[str, str]:
    return {
        "tenant": f"TENANT-{suffix}",
        "run": f"RUN-{suffix}",
        "incident": f"INC-{suffix}",
        "site": f"SITE-{suffix}",
        "device": f"POS-{suffix}",
        "peer": f"POS-PEER-{suffix}",
        "attachment": f"ATT-{suffix}",
        "switch": f"SW-{suffix}",
        "port": f"PORT-{suffix}",
        "kb": f"KB-{suffix}",
    }


def _topology(ids: dict[str, str]) -> DeviceTopology:
    return DeviceTopology(
        device_id=ids["device"],
        site_id=ids["site"],
        attachment_id=ids["attachment"],
        device_type="POS_TERMINAL",
        expected_switch_id=ids["switch"],
        expected_port_id=ids["port"],
    )


def _site_health(ids: dict[str, str]) -> SiteHealthSnapshot:
    return SiteHealthSnapshot(
        site_id=ids["site"],
        site_network=HealthState.HEALTHY,
        payment_service=HealthState.HEALTHY,
        peer_device_id=ids["peer"],
        peer_reachable=True,
        affected_device_id=ids["device"],
        affected_device_reachable=False,
    )


def _diagnostic(ids: dict[str, str]) -> AccessLinkDiagnosticSnapshot:
    return AccessLinkDiagnosticSnapshot(
        target_id=ids["attachment"],
        attachment_id=ids["attachment"],
        switch_id=ids["switch"],
        port_id=ids["port"],
        switch_reachable=True,
        admin_state=AdminState.UP,
        operational_state=OperationalState.DOWN,
        port_security=PortSecurityState.NORMAL,
        configuration=ConfigurationState.EXPECTED,
    )


def _kb(ids: dict[str, str]) -> KbArticle:
    return KbArticle(
        article_id=ids["kb"],
        title="Approved local access-link inspection",
        approved=True,
        diagnosis_codes=(DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,),
        allowed_actions=(ActionType.ONSITE_FIELD_VISIT,),
    )


def _evidence(ids: dict[str, str]) -> tuple[Evidence, ...]:
    expiry = T0 + timedelta(minutes=30)
    return (
        Evidence(
            evidence_id=f"E-CMDB-{ids['run']}",
            tenant_id=ids["tenant"],
            run_id=ids["run"],
            source_type=EvidenceSourceType.CMDB_SNAPSHOT,
            captured_at=T0,
            entity_ids=(
                ids["device"],
                ids["site"],
                ids["attachment"],
                ids["switch"],
                ids["port"],
            ),
            payload=_topology(ids),
        ),
        Evidence(
            evidence_id=f"E-SITE-{ids['run']}",
            tenant_id=ids["tenant"],
            run_id=ids["run"],
            source_type=EvidenceSourceType.SITE_HEALTH,
            captured_at=T0,
            entity_ids=(ids["site"], ids["peer"], ids["device"]),
            payload=_site_health(ids),
            expires_at=expiry,
        ),
        Evidence(
            evidence_id=f"E-DIAG-{ids['run']}",
            tenant_id=ids["tenant"],
            run_id=ids["run"],
            source_type=EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
            captured_at=T0,
            entity_ids=(ids["attachment"], ids["switch"], ids["port"]),
            payload=_diagnostic(ids),
            expires_at=expiry,
        ),
        Evidence(
            evidence_id=f"E-KB-{ids['run']}",
            tenant_id=ids["tenant"],
            run_id=ids["run"],
            source_type=EvidenceSourceType.KB_ARTICLE,
            captured_at=T0,
            entity_ids=(ids["kb"],),
            payload=_kb(ids),
        ),
        Evidence(
            evidence_id=f"E-SEARCH-{ids['run']}",
            tenant_id=ids["tenant"],
            run_id=ids["run"],
            source_type=EvidenceSourceType.INCIDENT_SEARCH,
            captured_at=T0,
            entity_ids=(ids["device"], ids["incident"]),
            payload=IncidentSearchSnapshot(
                scope=IncidentSearchScope.DEVICE,
                entity_id=ids["device"],
                open_incident_ids=(ids["incident"],),
            ),
        ),
    )


async def _seed_run(factory, ids: dict[str, str]) -> tuple[Evidence, ...]:
    evidence = _evidence(ids)
    async with SqlAlchemyToolReadUnitOfWork(factory) as uow:
        await uow.runs.add(
            Run(
                run_id=ids["run"],
                tenant_id=ids["tenant"],
                scenario_id="scenario-1",
                status=RunStatus.ACTIVE,
                created_at=T0,
                updated_at=T0,
            )
        )
        await uow.incidents.save(
            Incident(
                incident_id=ids["incident"],
                tenant_id=ids["tenant"],
                run_id=ids["run"],
                site_id=ids["site"],
                reported_device_id=ids["device"],
                symptom="Payment terminal is unreachable.",
                status=IncidentStatus.OPEN,
                created_at=T0,
                updated_at=T0,
            )
        )
        for item in evidence:
            await uow.evidence.add(item)
        await uow.commit()
    return evidence


def _id_factory(suffix: str):
    def make(prefix: str) -> str:
        return f"{prefix.upper()}-{suffix}"
    return make


class StaticCmdb:
    def __init__(self, topology: DeviceTopology) -> None:
        self.topology = topology
        self.calls = 0

    async def get_device(
        self,
        *,
        tenant_id: str,
        run_id: str,
        device_id: str,
    ) -> DeviceTopology | None:
        self.calls += 1
        if device_id != self.topology.device_id:
            return None
        return self.topology


class StaticMonitoring:
    def __init__(self, diagnostic: AccessLinkDiagnosticSnapshot) -> None:
        self.diagnostic = diagnostic
        self.calls = 0

    async def get_site_health(self, *, tenant_id: str, run_id: str, site_id: str):
        return None

    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type,
        target_id: str,
    ) -> AccessLinkDiagnosticSnapshot | None:
        self.calls += 1
        if target_id != self.diagnostic.target_id:
            return None
        return self.diagnostic


async def _create_proposal(factory, ids: dict[str, str], evidence: tuple[Evidence, ...]):
    proposal_service = FieldVisitProposalService(
        lambda: SqlAlchemyProposalCreationUnitOfWork(factory),
        clock=lambda: T0 + timedelta(minutes=1),
        id_factory=_id_factory(ids["run"]),
    )
    required = tuple(
        item.evidence_id
        for item in evidence
        if item.source_type
        in {
            EvidenceSourceType.CMDB_SNAPSHOT,
            EvidenceSourceType.SITE_HEALTH,
            EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
            EvidenceSourceType.KB_ARTICLE,
        }
    )
    return await proposal_service.create(
        ToolCallContext(ids["tenant"], ids["run"]),
        ProposeFieldVisitRequest(
            incident_id=ids["incident"],
            device_id=ids["device"],
            diagnosis=DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
            evidence_ids=required,
            rationale="Evidence supports an onsite physical access-path inspection.",
        ),
    )


async def _counts(factory, ids: dict[str, str]) -> tuple[int, int, int]:
    async with factory() as session:
        approval_count = await session.scalar(
            select(func.count())
            .select_from(ApprovalRow)
            .where(
                ApprovalRow.tenant_id == ids["tenant"],
                ApprovalRow.run_id == ids["run"],
            )
        )
        action_count = await session.scalar(
            select(func.count())
            .select_from(ExecutedActionRow)
            .where(
                ExecutedActionRow.tenant_id == ids["tenant"],
                ExecutedActionRow.run_id == ids["run"],
            )
        )
        work_order_count = await session.scalar(
            select(func.count())
            .select_from(FieldServiceWorkOrderRow)
            .where(
                FieldServiceWorkOrderRow.tenant_id == ids["tenant"],
                FieldServiceWorkOrderRow.run_id == ids["run"],
            )
        )
    return int(approval_count or 0), int(action_count or 0), int(work_order_count or 0)


def test_database_url_normalization_is_postgres_only():
    assert (
        normalize_database_url("postgresql://u:p@db/app")
        == "postgresql+psycopg://u:p@db/app"
    )
    assert (
        normalize_database_url("postgres://u:p@db/app")
        == "postgresql+psycopg://u:p@db/app"
    )
    assert (
        normalize_database_url("postgresql+psycopg://u:p@db/app")
        == "postgresql+psycopg://u:p@db/app"
    )
    with pytest.raises(ValueError):
        normalize_database_url("sqlite:///tmp/app.db")


def test_evidence_payload_deserialization_rejects_coercion():
    ids = _ids(_suffix())
    payload = serialize_evidence_payload(
        EvidenceSourceType.SITE_HEALTH,
        _site_health(ids),
    )
    payload["peer_reachable"] = "false"
    with pytest.raises(ValueError, match="peer_reachable must be a boolean"):
        deserialize_evidence_payload(EvidenceSourceType.SITE_HEALTH, payload)


def test_phase4a_schema_contains_all_product_owned_tables():
    async def scenario() -> None:
        engine, _ = _new_db()
        try:
            async with engine.connect() as connection:
                names = await connection.run_sync(
                    lambda sync_connection: set(
                        inspect(sync_connection).get_table_names()
                    )
                )
            assert {
                RunRow.__tablename__,
                IncidentRow.__tablename__,
                EvidenceRow.__tablename__,
                ActionProposalRow.__tablename__,
                ApprovalRow.__tablename__,
                ExecutedActionRow.__tablename__,
                FieldServiceWorkOrderRow.__tablename__,
                ApplicationEventRow.__tablename__,
                ApplicationOutboxRow.__tablename__,
            }.issubset(names)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_repository_round_trip_survives_new_engine_and_preserves_typed_evidence():
    async def scenario() -> None:
        ids = _ids(_suffix())
        engine, factory = _new_db()
        evidence = await _seed_run(factory, ids)
        await engine.dispose()

        restarted_engine, restarted_factory = _new_db()
        try:
            async with restarted_factory() as session:
                runs = SqlAlchemyRunRepository(session)
                incidents = SqlAlchemyIncidentRepository(session)
                evidence_repo = SqlAlchemyEvidenceRepository(session)

                run = await runs.get(
                    tenant_id=ids["tenant"],
                    run_id=ids["run"],
                )
                incident = await incidents.get(
                    tenant_id=ids["tenant"],
                    run_id=ids["run"],
                    incident_id=ids["incident"],
                )
                restored = await evidence_repo.get_many(
                    tenant_id=ids["tenant"],
                    run_id=ids["run"],
                    evidence_ids=tuple(item.evidence_id for item in evidence),
                )

            assert run is not None and run.status is RunStatus.ACTIVE
            assert incident is not None and incident.status is IncidentStatus.OPEN
            assert restored == evidence
            assert isinstance(restored[0].payload, DeviceTopology)
            assert isinstance(restored[1].payload, SiteHealthSnapshot)
            assert isinstance(restored[2].payload, AccessLinkDiagnosticSnapshot)
            assert isinstance(restored[3].payload, KbArticle)
            assert isinstance(restored[4].payload, IncidentSearchSnapshot)
        finally:
            await restarted_engine.dispose()

    asyncio.run(scenario())


def test_tenant_and_run_scoped_reads_do_not_bleed_between_contexts():
    async def scenario() -> None:
        suffix = _suffix()
        left = _ids(suffix)
        right = dict(left)
        right["tenant"] = f"TENANT-OTHER-{suffix}"

        engine, factory = _new_db()
        try:
            left_evidence = await _seed_run(factory, left)
            await _seed_run(factory, right)

            async with factory() as session:
                incidents = SqlAlchemyIncidentRepository(session)
                evidence_repo = SqlAlchemyEvidenceRepository(session)

                assert (
                    await incidents.get(
                        tenant_id=left["tenant"],
                        run_id=left["run"],
                        incident_id=left["incident"],
                    )
                ) is not None
                assert (
                    await incidents.get(
                        tenant_id="TENANT-DOES-NOT-EXIST",
                        run_id=left["run"],
                        incident_id=left["incident"],
                    )
                ) is None

                own = await evidence_repo.get_many(
                    tenant_id=left["tenant"],
                    run_id=left["run"],
                    evidence_ids=(left_evidence[0].evidence_id,),
                )
                foreign = await evidence_repo.get_many(
                    tenant_id="TENANT-DOES-NOT-EXIST",
                    run_id=left["run"],
                    evidence_ids=(left_evidence[0].evidence_id,),
                )
                assert own == (left_evidence[0],)
                assert foreign == ()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_composite_foreign_keys_block_cross_tenant_child_write():
    async def scenario() -> None:
        suffix = _suffix()
        left = _ids(suffix)
        right = _ids(f"OTHER-{suffix}")
        engine, factory = _new_db()
        try:
            left_evidence = await _seed_run(factory, left)
            await _seed_run(factory, right)
            created = await _create_proposal(factory, left, left_evidence)
            assert created.ok is True

            with pytest.raises(IntegrityError):
                async with SqlAlchemyApprovalExecutionUnitOfWork(factory) as uow:
                    await uow.approvals.add(
                        Approval(
                            approval_id=f"APPROVAL-X-{suffix}",
                            tenant_id=right["tenant"],
                            run_id=right["run"],
                            proposal_id=created.proposal.proposal_id,
                            decision=ApprovalDecision.APPROVED,
                            decided_at=T0 + timedelta(minutes=2),
                            decided_by="integration-test",
                        )
                    )
                    await uow.commit()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_repeat_and_concurrent_approve_create_exactly_one_execution():
    async def scenario() -> None:
        ids = _ids(_suffix())
        engine, factory = _new_db()
        try:
            evidence = await _seed_run(factory, ids)
            created = await _create_proposal(factory, ids, evidence)
            assert created.ok is True
            assert created.proposal.status is ProposalStatus.PENDING_APPROVAL

            cmdb = StaticCmdb(_topology(ids))
            monitoring = StaticMonitoring(_diagnostic(ids))
            service = FieldVisitApprovalService(
                lambda: SqlAlchemyApprovalExecutionUnitOfWork(factory),
                cmdb=cmdb,
                monitoring=monitoring,
                clock=lambda: T0 + timedelta(minutes=2),
                id_factory=lambda prefix: f"{prefix.upper()}-{uuid4().hex}",
            )
            context = ToolCallContext(ids["tenant"], ids["run"])

            first, second = await asyncio.gather(
                service.decide(
                    context,
                    proposal_id=created.proposal.proposal_id,
                    decision=ApprovalDecision.APPROVED,
                    decided_by="human-operator",
                ),
                service.decide(
                    context,
                    proposal_id=created.proposal.proposal_id,
                    decision=ApprovalDecision.APPROVED,
                    decided_by="human-operator",
                ),
            )

            assert first.ok is True and second.ok is True
            assert sorted((first.replayed, second.replayed)) == [False, True]
            assert first.approval.approval_id == second.approval.approval_id
            assert await _counts(factory, ids) == (1, 1, 1)
            assert cmdb.calls == 1
            assert monitoring.calls == 1

            replay = await service.decide(
                context,
                proposal_id=created.proposal.proposal_id,
                decision=ApprovalDecision.APPROVED,
                decided_by="human-operator",
            )
            assert replay.ok is True and replay.replayed is True
            assert replay.approval.approval_id == first.approval.approval_id
            assert await _counts(factory, ids) == (1, 1, 1)

            async with factory() as session:
                proposals = SqlAlchemyProposalRepository(session)
                incidents = SqlAlchemyIncidentRepository(session)
                approvals = SqlAlchemyApprovalRepository(session)
                runs = SqlAlchemyRunRepository(session)

                proposal = await proposals.get(
                    tenant_id=ids["tenant"],
                    run_id=ids["run"],
                    proposal_id=created.proposal.proposal_id,
                )
                incident = await incidents.get(
                    tenant_id=ids["tenant"],
                    run_id=ids["run"],
                    incident_id=ids["incident"],
                )
                approval = await approvals.get_for_proposal(
                    tenant_id=ids["tenant"],
                    run_id=ids["run"],
                    proposal_id=created.proposal.proposal_id,
                )
                run = await runs.get(
                    tenant_id=ids["tenant"],
                    run_id=ids["run"],
                )

            assert proposal is not None and proposal.status is ProposalStatus.EXECUTED
            assert incident is not None and incident.status is IncidentStatus.ESCALATED
            assert approval is not None and approval.decision is ApprovalDecision.APPROVED
            assert run is not None and run.status is RunStatus.ACTIVE
        finally:
            await engine.dispose()

    asyncio.run(scenario())
