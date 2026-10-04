from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

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
        lifecycle_service=lifecycle,
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


def test_concurrent_event_writers_allocate_contiguous_per_run_sequence_and_outbox():
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
            assert await _event_outbox_counts(factory, ids) == (12, 12)
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

            tail = await lifecycle.timeline(context, after_seq=1, limit=2)
            assert [item.seq for item in tail] == [2, 3]
            assert [item.event_type for item in tail] == [
                ApplicationEventType.EXTERNAL_SIGNAL,
                ApplicationEventType.FINDING_RECORDED,
            ]

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

            assert await _event_outbox_counts(factory, ids) == (3, 3)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_tool_adapter_persists_started_and_finished_for_success_and_failure():
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

            timeline = await lifecycle.timeline(context)
            assert [item.event_type for item in timeline] == [
                ApplicationEventType.TOOL_STARTED,
                ApplicationEventType.TOOL_FINISHED,
                ApplicationEventType.TOOL_STARTED,
                ApplicationEventType.TOOL_FINISHED,
            ]
            assert timeline[0].payload["tool_name"] == "get_device"
            assert timeline[1].payload["result"]["ok"] is True
            assert (
                timeline[1].payload["result"]["evidence"]["evidence_id"]
                == success.evidence.evidence_id
            )
            assert timeline[3].payload["result"]["ok"] is False
            assert (
                timeline[3].payload["result"]["error"]["code"]
                == "CONTEXT_MISMATCH"
            )
            assert await _event_outbox_counts(factory, ids) == (4, 4)
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
            assert [item.seq for item in after_replay] == list(range(1, 8))
            assert [item.event_type for item in after_replay] == [
                ApplicationEventType.TOOL_STARTED,
                ApplicationEventType.PROPOSAL_CREATED,
                ApplicationEventType.RUN_STATUS_CHANGED,
                ApplicationEventType.TOOL_FINISHED,
                ApplicationEventType.APPROVAL_DECIDED,
                ApplicationEventType.ACTION_EXECUTED,
                ApplicationEventType.RUN_STATUS_CHANGED,
            ]
            assert after_replay[2].payload == {
                "previous_status": "ACTIVE",
                "status": "WAITING_APPROVAL",
                "cause": "proposal_created",
                "proposal_id": proposed.proposal.proposal_id,
            }
            assert after_replay[4].payload["decision"] == "APPROVED"
            assert (
                after_replay[5].payload["work_order_id"]
                == approved.work_order.work_order_id
            )
            assert after_replay[6].payload["status"] == "ACTIVE"
            assert await _event_outbox_counts(factory, ids) == (7, 7)
        finally:
            await engine.dispose()

    asyncio.run(scenario())
