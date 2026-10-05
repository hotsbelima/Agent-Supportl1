from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from product_backend.adapters.tool_adapters import DefaultScenario1ToolAdapter
from product_backend.application.field_visit import (
    FieldVisitApprovalService,
    FieldVisitProposalService,
)
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.read_tools import (
    EvidenceTtlPolicy,
    Scenario1ReadToolService,
)
from product_backend.contracts.events import (
    ApplicationEventType,
    validate_safe_event_payload,
)
from product_backend.contracts.tools import (
    GetDeviceRequest,
    ProposeFieldVisitRequest,
    ToolCallContext,
)
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
from product_backend.persistence.tables import (
    ApplicationEventRow,
    ApplicationOutboxRow,
)
from product_backend.persistence.uow import (
    SqlAlchemyApprovalExecutionUnitOfWork,
    SqlAlchemyLifecycleUnitOfWork,
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


def _ids(prefix: str | None = None) -> dict[str, str]:
    suffix = prefix or uuid4().hex[:12]
    return {
        "tenant": f"TENANT-{suffix}",
        "run": f"RUN-{suffix}",
        "incident": f"INC-{suffix}",
        "site": f"SITE-{suffix}",
        "device": f"POS-{suffix}",
        "peer": f"POS-PEER-{suffix}",
        "attachment": f"ATT-{suffix}",
        "switch": f"SW-{suffix}",
        "port": f"Gi-{suffix}",
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
        title="Approved local physical-path inspection",
        approved=True,
        diagnosis_codes=(DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,),
        allowed_actions=(ActionType.ONSITE_FIELD_VISIT,),
    )


def _required_evidence(ids: dict[str, str]) -> tuple[Evidence, ...]:
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
    )


async def _seed(
    factory,
    ids: dict[str, str],
    *,
    evidence: tuple[Evidence, ...] = (),
) -> None:
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


class StaticCmdb:
    def __init__(self, topology: DeviceTopology) -> None:
        self.topology = topology

    async def get_device(
        self,
        *,
        tenant_id: str,
        run_id: str,
        device_id: str,
    ) -> DeviceTopology | None:
        if device_id != self.topology.device_id:
            return None
        return self.topology


class StaticMonitoring:
    def __init__(
        self,
        ids: dict[str, str],
        diagnostic: AccessLinkDiagnosticSnapshot,
    ) -> None:
        self.ids = ids
        self.diagnostic = diagnostic

    async def get_site_health(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
    ) -> SiteHealthSnapshot | None:
        if site_id != self.ids["site"]:
            return None
        return _site_health(self.ids)

    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type,
        target_id: str,
    ) -> AccessLinkDiagnosticSnapshot | None:
        if target_id != self.diagnostic.target_id:
            return None
        return self.diagnostic


class StaticItsm:
    def __init__(self, ids: dict[str, str]) -> None:
        self.ids = ids

    async def get_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> Incident | None:
        return None

    async def search_incidents(
        self,
        *,
        tenant_id: str,
        run_id: str,
        scope: IncidentSearchScope,
        entity_id: str,
    ) -> IncidentSearchSnapshot:
        return IncidentSearchSnapshot(
            scope=scope,
            entity_id=entity_id,
            open_incident_ids=(self.ids["incident"],),
        )


class StaticKb:
    def __init__(self, ids: dict[str, str]) -> None:
        self.ids = ids

    async def search(
        self,
        *,
        tenant_id: str,
        run_id: str,
        query: str,
    ) -> tuple[KbArticle, ...]:
        return (_kb(self.ids),)


def _services(factory, ids: dict[str, str]):
    lifecycle = ApplicationLifecycleService(
        lambda: SqlAlchemyLifecycleUnitOfWork(factory)
    )
    read_service = Scenario1ReadToolService(
        read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
        cmdb=StaticCmdb(_topology(ids)),
        monitoring=StaticMonitoring(ids, _diagnostic(ids)),
        itsm=StaticItsm(ids),
        kb=StaticKb(ids),
        ttl_policy=EvidenceTtlPolicy(
            site_health=timedelta(minutes=5),
            access_link_diagnostic=timedelta(minutes=2),
        ),
        clock=lambda: T0 + timedelta(minutes=1),
        id_factory=lambda prefix: f"{prefix.upper()}-{uuid4().hex}",
    )
    proposal_service = FieldVisitProposalService(
        lambda: SqlAlchemyProposalCreationUnitOfWork(factory),
        clock=lambda: T0 + timedelta(minutes=2),
        id_factory=lambda prefix: f"{prefix.upper()}-{uuid4().hex}",
    )
    adapter = DefaultScenario1ToolAdapter(
        read_service=read_service,
        proposal_service=proposal_service,
    )
    approval_service = FieldVisitApprovalService(
        lambda: SqlAlchemyApprovalExecutionUnitOfWork(factory),
        cmdb=StaticCmdb(_topology(ids)),
        monitoring=StaticMonitoring(ids, _diagnostic(ids)),
        clock=lambda: T0 + timedelta(minutes=3),
        id_factory=lambda prefix: f"{prefix.upper()}-{uuid4().hex}",
    )
    return lifecycle, adapter, approval_service


async def _event_outbox_counts(factory, ids: dict[str, str]) -> tuple[int, int]:
    async with factory() as session:
        events = await session.scalar(
            select(func.count())
            .select_from(ApplicationEventRow)
            .where(
                ApplicationEventRow.tenant_id == ids["tenant"],
                ApplicationEventRow.run_id == ids["run"],
            )
        )
        outbox = await session.scalar(
            select(func.count())
            .select_from(ApplicationOutboxRow)
            .where(
                ApplicationOutboxRow.tenant_id == ids["tenant"],
                ApplicationOutboxRow.run_id == ids["run"],
            )
        )
    return int(events or 0), int(outbox or 0)


def test_safe_event_payload_rejects_hidden_reasoning_and_secrets():
    validate_safe_event_payload(
        {
            "tool_name": "get_device",
            "result": {"ok": True, "device_id": "POS-1"},
        }
    )
    with pytest.raises(ValueError, match="reasoning"):
        validate_safe_event_payload(
            {"result": {"reasoning": "hidden model scratchpad"}}
        )
    with pytest.raises(ValueError, match="api_key"):
        validate_safe_event_payload(
            {"nested": {"api_key": "must-not-persist"}}
        )
    with pytest.raises(ValueError, match="reasoning_trace"):
        validate_safe_event_payload(
            {"nested": {"reasoning_trace": "must-not-persist"}}
        )
    with pytest.raises(ValueError, match="client_secret_value"):
        validate_safe_event_payload(
            {"nested": {"client_secret_value": "must-not-persist"}}
        )
    with pytest.raises(ValueError, match="thought_trace"):
        validate_safe_event_payload(
            {"nested": {"thought_trace": "must-not-persist"}}
        )
    for key in (
        "chainOfThought",
        "modelReasoning",
        "clientSecret",
        "accessToken",
    ):
        with pytest.raises(ValueError, match=key):
            validate_safe_event_payload(
                {"nested": {key: "must-not-persist"}}
            )


def test_database_constraint_accepts_every_declared_event_type():
    async def scenario() -> None:
        ids = _ids()
        engine, factory = _new_db()
        try:
            await _seed(factory, ids)
            async with SqlAlchemyLifecycleUnitOfWork(factory) as uow:
                for event_type in ApplicationEventType:
                    await uow.events.append(
                        tenant_id=ids["tenant"],
                        run_id=ids["run"],
                        event_type=event_type,
                        payload={"contract_test": event_type.value},
                    )
                await uow.commit()

            lifecycle = ApplicationLifecycleService(
                lambda: SqlAlchemyLifecycleUnitOfWork(factory)
            )
            timeline = await lifecycle.timeline(
                ToolCallContext(ids["tenant"], ids["run"])
            )
            assert tuple(item.event_type for item in timeline) == tuple(
                ApplicationEventType
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_concurrent_event_writers_allocate_contiguous_sequence_without_generic_outbox():
    async def scenario() -> None:
        ids = _ids()
        engine, factory = _new_db()
        try:
            await _seed(factory, ids)
            lifecycle = ApplicationLifecycleService(
                lambda: SqlAlchemyLifecycleUnitOfWork(factory)
            )
            context = ToolCallContext(ids["tenant"], ids["run"])

            events = await asyncio.gather(
                *(
                    lifecycle.record_external_signal(
                        context,
                        signal_type="test.signal",
                        details={"writer": index},
                    )
                    for index in range(12)
                )
            )

            assert sorted(event.seq for event in events) == list(range(1, 13))
            timeline = await lifecycle.timeline(context)
            assert [event.seq for event in timeline] == list(range(1, 13))
            assert all(
                event.event_type is ApplicationEventType.EXTERNAL_SIGNAL
                for event in timeline
            )
            assert await _event_outbox_counts(factory, ids) == (12, 0)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_lifecycle_service_uses_server_time_validates_context_and_supports_cursor():
    async def scenario() -> None:
        ids = _ids()
        evidence = _required_evidence(ids)
        engine, factory = _new_db()
        try:
            await _seed(factory, ids, evidence=evidence)
            lifecycle = ApplicationLifecycleService(
                lambda: SqlAlchemyLifecycleUnitOfWork(factory)
            )
            context = ToolCallContext(ids["tenant"], ids["run"])

            before = datetime.now(UTC)
            started = await lifecycle.record_simulation_started(
                context,
                scenario_id="scenario-1",
            )
            signal = await lifecycle.record_external_signal(
                context,
                signal_type="itsm.incident.created",
                details={
                    "incident_id": ids["incident"],
                    "fixture_offset_seconds": 30,
                },
            )
            finding = await lifecycle.record_finding(
                context,
                finding_code="LOCAL_LINK_OBSERVED",
                summary="Evidence supports a local access-path fault.",
                evidence_ids=(evidence[0].evidence_id, evidence[2].evidence_id),
            )
            after = datetime.now(UTC)

            assert before <= started.occurred_at <= after
            assert before <= signal.occurred_at <= after
            assert before <= finding.occurred_at <= after
            assert [started.seq, signal.seq, finding.seq] == [1, 2, 3]
            assert started.payload == {
                "scenario_id": "scenario-1",
                "status": "ACTIVE",
            }

            tail = await lifecycle.timeline(context, after_seq=1, limit=2)
            assert [item.seq for item in tail] == [2, 3]
            assert [item.event_type for item in tail] == [
                ApplicationEventType.EXTERNAL_SIGNAL,
                ApplicationEventType.FINDING_RECORDED,
            ]

            with pytest.raises(ValueError, match="unique"):
                await lifecycle.record_finding(
                    context,
                    finding_code="DUPLICATE",
                    summary="Must not persist duplicate references.",
                    evidence_ids=(
                        evidence[0].evidence_id,
                        evidence[0].evidence_id,
                    ),
                )

            with pytest.raises(ValueError, match="evidence"):
                await lifecycle.record_finding(
                    context,
                    finding_code="FOREIGN",
                    summary="Must not persist.",
                    evidence_ids=("E-FOREIGN",),
                )

            with pytest.raises(ValueError, match="scenario_id"):
                await lifecycle.record_simulation_started(
                    context,
                    scenario_id="scenario-2",
                )

            with pytest.raises(ValueError, match="run context"):
                await lifecycle.timeline(
                    ToolCallContext("OTHER-TENANT", ids["run"])
                )

            assert await _event_outbox_counts(factory, ids) == (3, 0)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_tool_adapter_does_not_persist_generic_runtime_lifecycle():
    async def scenario() -> None:
        ids = _ids()
        engine, factory = _new_db()
        try:
            await _seed(factory, ids)
            lifecycle, adapter, _ = _services(factory, ids)
            context = ToolCallContext(ids["tenant"], ids["run"])

            success = await adapter.get_device(
                context,
                GetDeviceRequest(ids["device"]),
            )
            assert success.ok is True

            failure = await adapter.get_device(
                context,
                GetDeviceRequest("POS-UNKNOWN"),
            )
            assert failure.ok is False

            # Generic tool invocation lifecycle remains ADK-owned. Phase 7A
            # adds only a safe Product observation projection for persisted
            # Evidence so the operational UI can update in realtime.
            timeline = await lifecycle.timeline(context)
            assert [item.event_type for item in timeline] == [
                ApplicationEventType.OBSERVATION_RECORDED
            ]
            assert timeline[0].payload["evidence_id"] == success.evidence.evidence_id
            assert all(
                item.event_type
                not in {
                    ApplicationEventType.TOOL_STARTED,
                    ApplicationEventType.TOOL_FINISHED,
                }
                for item in timeline
            )
            assert await _event_outbox_counts(factory, ids) == (1, 0)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_database_constraints_and_read_boundary_reject_invalid_event_records():
    async def scenario() -> None:
        ids = _ids()
        engine, factory = _new_db()
        try:
            await _seed(factory, ids)
            lifecycle = ApplicationLifecycleService(
                lambda: SqlAlchemyLifecycleUnitOfWork(factory)
            )
            context = ToolCallContext(ids["tenant"], ids["run"])
            event = await lifecycle.record_external_signal(
                context,
                signal_type="test.signal",
                details={"ok": True},
            )

            async with factory() as session:
                session.add(
                    ApplicationEventRow(
                        tenant_id=ids["tenant"],
                        run_id=ids["run"],
                        seq=event.seq + 1,
                        event_id=f"EVENT-BAD-{uuid4().hex}",
                        event_type="unknown.event",
                        occurred_at=datetime.now(UTC),
                        payload={},
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()

            async with factory() as session:
                session.add(
                    ApplicationOutboxRow(
                        tenant_id=ids["tenant"],
                        run_id=ids["run"],
                        outbox_id=f"OUTBOX-BAD-{uuid4().hex}",
                        event_seq=None,
                        topic="application.event",
                        payload={},
                        created_at=datetime.now(UTC),
                        available_at=datetime.now(UTC),
                        delivered_at=None,
                        attempt_count=0,
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()
                await session.rollback()

            async with factory() as session:
                await session.execute(
                    update(ApplicationEventRow)
                    .where(
                        ApplicationEventRow.tenant_id == ids["tenant"],
                        ApplicationEventRow.run_id == ids["run"],
                        ApplicationEventRow.seq == event.seq,
                    )
                    .values(payload={"reasoning_trace": "corrupt raw write"})
                )
                await session.commit()

            with pytest.raises(ValueError, match="reasoning_trace"):
                await lifecycle.timeline(context)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_stale_approval_event_records_deterministic_reason():
    async def scenario() -> None:
        ids = _ids()
        evidence = _required_evidence(ids)
        engine, factory = _new_db()
        try:
            await _seed(factory, ids, evidence=evidence)
            lifecycle, adapter, _ = _services(factory, ids)
            context = ToolCallContext(ids["tenant"], ids["run"])
            proposed = await adapter.propose_field_visit(
                context,
                ProposeFieldVisitRequest(
                    incident_id=ids["incident"],
                    device_id=ids["device"],
                    diagnosis=DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
                    evidence_ids=tuple(item.evidence_id for item in evidence),
                    rationale="Request onsite physical-path inspection.",
                ),
            )
            assert proposed.ok is True

            recovered = replace(
                _diagnostic(ids),
                operational_state=OperationalState.UP,
            )
            approval_service = FieldVisitApprovalService(
                lambda: SqlAlchemyApprovalExecutionUnitOfWork(factory),
                cmdb=StaticCmdb(_topology(ids)),
                monitoring=StaticMonitoring(ids, recovered),
                clock=lambda: T0 + timedelta(minutes=3),
                id_factory=lambda prefix: f"{prefix.upper()}-{uuid4().hex}",
            )
            result = await approval_service.decide(
                context,
                proposal_id=proposed.proposal.proposal_id,
                decision=ApprovalDecision.APPROVED,
                decided_by="human-operator",
            )

            assert result.ok is True
            assert result.proposal.status is ProposalStatus.STALE
            assert result.executed_action is None
            assert result.work_order is None

            timeline = await lifecycle.timeline(context)
            approval_event = next(
                item
                for item in timeline
                if item.event_type is ApplicationEventType.APPROVAL_DECIDED
            )
            assert approval_event.payload["decision"] == "APPROVED"
            assert approval_event.payload["proposal_status"] == "STALE"
            assert (
                approval_event.payload["stale_reason"]
                == "link_no_longer_matches_down_pattern"
            )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_proposal_approval_action_timeline_is_complete_and_replay_is_not_duplicated():
    async def scenario() -> None:
        ids = _ids()
        evidence = _required_evidence(ids)
        engine, factory = _new_db()
        try:
            await _seed(factory, ids, evidence=evidence)
            lifecycle, adapter, approval_service = _services(factory, ids)
            context = ToolCallContext(ids["tenant"], ids["run"])
            evidence_ids = tuple(item.evidence_id for item in evidence)

            proposed = await adapter.propose_field_visit(
                context,
                ProposeFieldVisitRequest(
                    incident_id=ids["incident"],
                    device_id=ids["device"],
                    diagnosis=DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
                    evidence_ids=evidence_ids,
                    rationale=(
                        "Evidence supports local access-path failure; "
                        "request onsite inspection."
                    ),
                ),
            )
            assert proposed.ok is True
            assert proposed.proposal.status is ProposalStatus.PENDING_APPROVAL

            approved = await approval_service.decide(
                context,
                proposal_id=proposed.proposal.proposal_id,
                decision=ApprovalDecision.APPROVED,
                decided_by="human-operator",
            )
            assert approved.ok is True
            assert approved.replayed is False
            assert approved.executed_action is not None
            assert approved.work_order is not None

            before_replay = await lifecycle.timeline(context)
            replay = await approval_service.decide(
                context,
                proposal_id=proposed.proposal.proposal_id,
                decision=ApprovalDecision.APPROVED,
                decided_by="human-operator",
            )
            after_replay = await lifecycle.timeline(context)

            assert replay.ok is True and replay.replayed is True
            assert after_replay == before_replay
            assert [item.seq for item in after_replay] == list(range(1, 6))
            assert [item.event_type for item in after_replay] == [
                ApplicationEventType.PROPOSAL_CREATED,
                ApplicationEventType.RUN_STATUS_CHANGED,
                ApplicationEventType.APPROVAL_DECIDED,
                ApplicationEventType.ACTION_EXECUTED,
                ApplicationEventType.RUN_STATUS_CHANGED,
            ]
            assert after_replay[1].payload == {
                "previous_status": "ACTIVE",
                "status": "WAITING_APPROVAL",
                "cause": "proposal_created",
                "proposal_id": proposed.proposal.proposal_id,
            }
            assert after_replay[2].payload["decision"] == "APPROVED"
            assert (
                after_replay[3].payload["work_order_id"]
                == approved.work_order.work_order_id
            )
            assert after_replay[4].payload["status"] == "ACTIVE"
            assert await _event_outbox_counts(factory, ids) == (5, 0)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
