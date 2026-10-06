from __future__ import annotations

import asyncio
import importlib
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from agent_runtime.human_decision import WAIT_FOR_HUMAN_DECISION_TOOL
from agent_runtime.service import _find_operational_event_correlation
from product_api.app import create_app
from product_api.dispatch import Scenario1DispatchWorker
from product_api.scenario1_fixture import AFFECTED_DEVICE_ID, Scenario1FixtureSources
from product_backend.application.read_tools import EvidenceTtlPolicy, Scenario1ReadToolService
from product_backend.application.run_lifecycle import Scenario1RunStartService
from product_backend.application.run_state import RunStateService
from product_backend.contracts.events import AGENT_DISPATCH_TOPIC, ApplicationEventType
from product_backend.contracts.tools import GetDeviceRequest, ToolCallContext
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.run_state import SqlAlchemyRunStateQuery
from product_backend.persistence.tables import ApplicationEventRow, ApplicationOutboxRow
from product_backend.persistence.uow import (
    SqlAlchemyDispatchUnitOfWork,
    SqlAlchemyRunStartUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 7A integration tests")
    return normalize_database_url(value)


class _RecordingRuntime:
    gemini_configured = True

    def __init__(self, *, fail_event_id: str | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.fail_event_id = fail_event_id
        self.failed_once = False

    async def invoke_operational_event(
        self,
        *,
        tenant_id: str,
        run_id: str,
        operational_event_id: str | None,
        operational_signal: dict[str, object],
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "operational_event_id": operational_event_id,
                "operational_signal": operational_signal,
            }
        )
        if (
            operational_event_id == self.fail_event_id
            and not self.failed_once
        ):
            self.failed_once = True
            raise RuntimeError("synthetic provider failure")
        return SimpleNamespace(
            session_id=run_id,
            invocation_id="INV-TEST",
            final_answer=None,
            awaiting_human_decision=False,
            pending_proposal_id=None,
        )


async def _target_outbox(factory, *, tenant_id: str, run_id: str):
    async with factory() as session:
        result = await session.execute(
            select(ApplicationOutboxRow).where(
                ApplicationOutboxRow.tenant_id == tenant_id,
                ApplicationOutboxRow.run_id == run_id,
                ApplicationOutboxRow.topic == AGENT_DISPATCH_TOPIC,
            )
        )
        return result.scalar_one()


async def _drain_until_delivered(
    worker: Scenario1DispatchWorker,
    factory,
    *,
    tenant_id: str,
    run_id: str,
    max_attempts: int = 500,
) -> ApplicationOutboxRow:
    for _ in range(max_attempts):
        row = await _target_outbox(
            factory,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if row.delivered_at is not None:
            return row
        processed = await worker.dispatch_once()
        if not processed:
            await asyncio.sleep(0)
    raise AssertionError("target dispatch row was not delivered")




class _FlakyClaimOutbox:
    def __init__(self) -> None:
        self.claim_calls = 0

    async def claim_next(self, *, topic: str, lease_seconds: float):
        self.claim_calls += 1
        if self.claim_calls == 1:
            raise RuntimeError("synthetic transient database failure")
        return None


class _FlakyClaimUow:
    def __init__(self, outbox: _FlakyClaimOutbox) -> None:
        self.outbox = outbox

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


def test_dispatch_worker_survives_transient_claim_failure():
    async def scenario() -> None:
        outbox = _FlakyClaimOutbox()
        runtime = _RecordingRuntime()
        worker = Scenario1DispatchWorker(
            uow_factory=lambda: _FlakyClaimUow(outbox),
            state_service=SimpleNamespace(),  # unused when claim returns no row
            agent_runtime=runtime,  # type: ignore[arg-type]
            poll_interval_seconds=0.01,
            lease_seconds=1.0,
            invocation_timeout_seconds=0.5,
        )
        worker.start()
        try:
            await asyncio.sleep(0.02)
            assert worker.running is True
            worker.wake()
            await asyncio.sleep(0.03)
            assert outbox.claim_calls >= 2
            assert worker.running is True
        finally:
            await worker.close()
        assert worker.running is False

    asyncio.run(scenario())


def test_dispatch_lease_must_outlive_bounded_agent_invocation():
    with pytest.raises(
        ValueError,
        match="lease_seconds must exceed invocation_timeout_seconds",
    ):
        Scenario1DispatchWorker(
            uow_factory=lambda: SimpleNamespace(),
            state_service=SimpleNamespace(),  # type: ignore[arg-type]
            agent_runtime=_RecordingRuntime(),  # type: ignore[arg-type]
            lease_seconds=5.0,
            invocation_timeout_seconds=5.0,
        )


def test_start_stays_successful_when_eager_adk_session_provisioning_fails(
    monkeypatch,
):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    async def fail_session_provisioning(*args, **kwargs):
        raise RuntimeError("synthetic ADK session provisioning failure")

    app_module = importlib.import_module("product_api.app")
    monkeypatch.setattr(
        app_module,
        "ensure_run_session",
        fail_session_provisioning,
    )
    tenant_id = f"TENANT-7A-START-RECOVERY-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/scenario-1/runs",
            headers={"X-Tenant-ID": tenant_id},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["run"]["tenant_id"] == tenant_id
        assert body["run"]["status"] == "ACTIVE"
        assert body["latest_event_seq"] == 3


def test_run_start_atomically_persists_signal_and_dispatch_envelope():
    async def scenario() -> None:
        tenant_id = f"TENANT-7A-OUTBOX-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        fixture = Scenario1FixtureSources()
        start = Scenario1RunStartService(
            lambda: SqlAlchemyRunStartUnitOfWork(factory)
        )
        try:
            started = await start.start(
                tenant_id=tenant_id,
                bootstrap=fixture.bootstrap(),
            )
            async with factory() as session:
                events = (
                    await session.execute(
                        select(ApplicationEventRow)
                        .where(
                            ApplicationEventRow.tenant_id == tenant_id,
                            ApplicationEventRow.run_id == started.run.run_id,
                        )
                        .order_by(ApplicationEventRow.seq)
                    )
                ).scalars().all()
                rows = (
                    await session.execute(
                        select(ApplicationOutboxRow).where(
                            ApplicationOutboxRow.tenant_id == tenant_id,
                            ApplicationOutboxRow.run_id == started.run.run_id,
                        )
                    )
                ).scalars().all()

            signal = next(
                item
                for item in events
                if item.event_type == ApplicationEventType.EXTERNAL_SIGNAL.value
            )
            assert len(rows) == 1
            assert rows[0].topic == AGENT_DISPATCH_TOPIC
            assert rows[0].event_seq == signal.seq
            assert rows[0].payload["event_id"] == signal.event_id
            assert rows[0].payload["event_seq"] == signal.seq
            assert rows[0].payload["signal"] == signal.payload
            assert rows[0].delivered_at is None
            assert rows[0].attempt_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_dispatch_worker_delivers_each_persisted_event_once():
    async def scenario() -> None:
        tenant_id = f"TENANT-7A-DISPATCH-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        fixture = Scenario1FixtureSources()
        start = Scenario1RunStartService(
            lambda: SqlAlchemyRunStartUnitOfWork(factory)
        )
        state = RunStateService(SqlAlchemyRunStateQuery(factory))
        runtime = _RecordingRuntime()
        worker = Scenario1DispatchWorker(
            uow_factory=lambda: SqlAlchemyDispatchUnitOfWork(factory),
            state_service=state,
            agent_runtime=runtime,  # type: ignore[arg-type]
            poll_interval_seconds=0.01,
            lease_seconds=5.0,
            invocation_timeout_seconds=1.0,
        )
        try:
            started = await start.start(
                tenant_id=tenant_id,
                bootstrap=fixture.bootstrap(),
            )
            target = await _target_outbox(
                factory,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            event_id = str(target.payload["event_id"])

            delivered = await _drain_until_delivered(
                worker,
                factory,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            assert delivered.attempt_count == 1
            assert delivered.delivered_at is not None

            # Process any other due rows left by earlier regression tests. The
            # target event itself must never be dispatched again once delivered.
            for _ in range(10):
                if not await worker.dispatch_once():
                    break

            matching = [
                call
                for call in runtime.calls
                if call["operational_event_id"] == event_id
            ]
            assert len(matching) == 1
            signal = matching[0]["operational_signal"]
            assert isinstance(signal, dict)
            assert signal["event_id"] == event_id
            assert signal["event_seq"] == target.event_seq
            assert signal["scenario_id"] == "scenario-1"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_failed_dispatch_remains_durable_and_is_retryable():
    async def scenario() -> None:
        tenant_id = f"TENANT-7A-RETRY-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        fixture = Scenario1FixtureSources()
        start = Scenario1RunStartService(
            lambda: SqlAlchemyRunStartUnitOfWork(factory)
        )
        state = RunStateService(SqlAlchemyRunStateQuery(factory))
        try:
            started = await start.start(
                tenant_id=tenant_id,
                bootstrap=fixture.bootstrap(),
            )
            target = await _target_outbox(
                factory,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            event_id = str(target.payload["event_id"])
            runtime = _RecordingRuntime(fail_event_id=event_id)
            worker = Scenario1DispatchWorker(
                uow_factory=lambda: SqlAlchemyDispatchUnitOfWork(factory),
                state_service=state,
                agent_runtime=runtime,  # type: ignore[arg-type]
                poll_interval_seconds=0.01,
                lease_seconds=5.0,
                invocation_timeout_seconds=1.0,
            )

            # Older rows may exist in a full-suite database; drive the worker
            # until the target gets its first failed attempt.
            for _ in range(500):
                row = await _target_outbox(
                    factory,
                    tenant_id=tenant_id,
                    run_id=started.run.run_id,
                )
                if row.attempt_count:
                    break
                assert await worker.dispatch_once()
            row = await _target_outbox(
                factory,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            assert row.attempt_count == 1
            assert row.delivered_at is None
            assert row.available_at > row.created_at

            # Make the retry due without sleeping; the Product event/outbox row
            # is still the recovery source after the synthetic provider failure.
            async with factory() as session:
                await session.execute(
                    update(ApplicationOutboxRow)
                    .where(
                        ApplicationOutboxRow.tenant_id == tenant_id,
                        ApplicationOutboxRow.run_id == started.run.run_id,
                        ApplicationOutboxRow.outbox_id == row.outbox_id,
                    )
                    .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
                )
                await session.commit()

            delivered = await _drain_until_delivered(
                worker,
                factory,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            assert delivered.attempt_count == 2
            assert delivered.delivered_at is not None
            assert [
                call["operational_event_id"]
                for call in runtime.calls
                if call["operational_event_id"] == event_id
            ] == [event_id, event_id]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_read_tool_persists_safe_observation_event_for_realtime_ui():
    async def scenario() -> None:
        tenant_id = f"TENANT-7A-OBS-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        fixture = Scenario1FixtureSources()
        start = Scenario1RunStartService(
            lambda: SqlAlchemyRunStartUnitOfWork(factory)
        )
        read = Scenario1ReadToolService(
            read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
            cmdb=fixture,
            monitoring=fixture,
            itsm=fixture,
            kb=fixture,
            ttl_policy=EvidenceTtlPolicy(
                site_health=timedelta(minutes=5),
                access_link_diagnostic=timedelta(minutes=2),
            ),
        )
        try:
            started = await start.start(
                tenant_id=tenant_id,
                bootstrap=fixture.bootstrap(),
            )
            context = ToolCallContext(
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            result = await read.get_device(
                context,
                GetDeviceRequest(AFFECTED_DEVICE_ID),
            )
            assert result.ok is True

            async with factory() as session:
                observations = (
                    await session.execute(
                        select(ApplicationEventRow).where(
                            ApplicationEventRow.tenant_id == tenant_id,
                            ApplicationEventRow.run_id == started.run.run_id,
                            ApplicationEventRow.event_type
                            == ApplicationEventType.OBSERVATION_RECORDED.value,
                        )
                    )
                ).scalars().all()

            assert len(observations) == 1
            assert observations[0].payload["evidence_id"] == result.evidence.evidence_id
            assert observations[0].payload["source_type"] == "CMDB_SNAPSHOT"
            assert "reasoning" not in json.dumps(observations[0].payload).lower()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


class _FakeEvent:
    def __init__(
        self,
        *,
        author: str,
        invocation_id: str,
        text: str | None = None,
        calls: list[SimpleNamespace] | None = None,
        responses: list[SimpleNamespace] | None = None,
        long_running_tool_ids: list[str] | None = None,
        final: bool = False,
    ) -> None:
        self.author = author
        self.invocation_id = invocation_id
        self.content = (
            SimpleNamespace(
                parts=[SimpleNamespace(text=text, thought=False)]
            )
            if text is not None
            else None
        )
        self._calls = calls or []
        self._responses = responses or []
        self.long_running_tool_ids = long_running_tool_ids or []
        self.actions = None
        self._final = final

    def get_function_calls(self):
        return self._calls

    def get_function_responses(self):
        return self._responses

    def is_final_response(self):
        return self._final


def test_operational_event_redelivery_recovers_same_native_invocation():
    event_id = "EVENT-7A-1"
    invocation_id = "INV-7A-1"
    user = _FakeEvent(
        author="user",
        invocation_id=invocation_id,
        text=json.dumps(
            {
                "type": "operational_signal",
                "scenario": "scenario-1",
                "operational_event_id": event_id,
                "payload": {"signal": "fixture"},
            }
        ),
    )
    proposal = _FakeEvent(
        author="autonomous_l1_incident_agent",
        invocation_id=invocation_id,
        responses=[
            SimpleNamespace(
                name="propose_field_visit",
                response={
                    "ok": True,
                    "proposal": {
                        "proposal_id": "PROPOSAL-1",
                        "status": "PENDING_APPROVAL",
                    },
                },
            )
        ],
    )
    pause = _FakeEvent(
        author="autonomous_l1_incident_agent",
        invocation_id=invocation_id,
        calls=[
            SimpleNamespace(
                name=WAIT_FOR_HUMAN_DECISION_TOOL,
                id="CALL-WAIT-1",
                args={"proposal_id": "PROPOSAL-1"},
            )
        ],
        long_running_tool_ids=["CALL-WAIT-1"],
    )

    correlation = _find_operational_event_correlation(
        [user, proposal, pause],
        operational_event_id=event_id,
    )

    assert correlation is not None
    assert correlation.invocation_id == invocation_id
    assert correlation.settled is True
    assert correlation.pending_proposal_id == "PROPOSAL-1"
    assert correlation.paused_function_call_id == "CALL-WAIT-1"
