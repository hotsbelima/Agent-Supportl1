from __future__ import annotations

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from product_api.app import create_app

from product_api.scenario2_fixture import (
    ACMEPAY_DEPENDENCY_ID,
    CANONICAL_SIGNAL_SEQUENCE,
    SERVICE_KEY,
    STALE_MATCHING_MAJOR_INCIDENT_ID,
)
from product_api.scenario2_simulator import Scenario2SimulatorService
from product_api.scenario2_sources import PersistedScenario2FixtureSources
from product_backend.application.results import OperationFailure
from product_backend.application.scenario2_ingestion import (
    Scenario2FixtureTransitionService,
    Scenario2RunStartService,
    Scenario2SignalIngestionService,
)
from product_backend.application.scenario2_state import Scenario2StateService
from product_backend.contracts.events import (
    ApplicationEventType,
    SCENARIO2_AGENT_DISPATCH_TOPIC,
)
from product_backend.contracts.scenario2_ingestion import Scenario2SignalInput
from product_backend.domain.enums import EvidenceSourceType, HealthState, RunStatus
from product_backend.domain.models import Run
from product_backend.persistence.events import (
    SqlAlchemyApplicationEventRepository,
    SqlAlchemyApplicationOutboxRepository,
)
from product_backend.persistence.repositories import SqlAlchemyRunRepository
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.scenario2_state import SqlAlchemyScenario2StateQuery
from product_backend.persistence.tables import (
    ActionProposalRow,
    ApplicationEventRow,
    ApplicationOutboxRow,
    EvidenceRow,
    FieldServiceWorkOrderRow,
    OperationalSignalRow,
    ServiceIncidentRow,
)
from product_backend.persistence.uow import (
    SqlAlchemyScenario2FixtureStateUnitOfWork,
    SqlAlchemyScenario2RunStartUnitOfWork,
    SqlAlchemyScenario2SignalIngestionUnitOfWork,
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 7C persistence tests")
    return normalize_database_url(value)


def _services(factory):
    state = Scenario2StateService(SqlAlchemyScenario2StateQuery(factory))
    ingestion = Scenario2SignalIngestionService(
        lambda: SqlAlchemyScenario2SignalIngestionUnitOfWork(factory)
    )
    return (
        Scenario2RunStartService(
            lambda: SqlAlchemyScenario2RunStartUnitOfWork(factory)
        ),
        ingestion,
        state,
        Scenario2SimulatorService(
            state_service=state,
            ingestion_service=ingestion,
        ),
        Scenario2FixtureTransitionService(
            lambda: SqlAlchemyScenario2FixtureStateUnitOfWork(factory)
        ),
        PersistedScenario2FixtureSources(state),
    )


async def _evidence_rows(factory, *, tenant_id: str, run_id: str):
    async with factory() as session:
        return (
            await session.execute(
                select(EvidenceRow)
                .where(
                    EvidenceRow.tenant_id == tenant_id,
                    EvidenceRow.run_id == run_id,
                )
                .order_by(EvidenceRow.captured_at, EvidenceRow.evidence_id)
            )
        ).scalars().all()


async def _outbox_rows(factory, *, tenant_id: str, run_id: str):
    async with factory() as session:
        return (
            await session.execute(
                select(ApplicationOutboxRow)
                .where(
                    ApplicationOutboxRow.tenant_id == tenant_id,
                    ApplicationOutboxRow.run_id == run_id,
                )
                .order_by(ApplicationOutboxRow.event_seq)
            )
        ).scalars().all()


def test_outbox_preserves_per_run_event_order_across_retry_lease():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-ORDER-{suffix}"
        run_a = f"RUN-7C-ORDER-A-{suffix}"
        run_b = f"RUN-7C-ORDER-B-{suffix}"
        topic = f"test.phase7c.ordered.{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                await session.begin()
                runs = SqlAlchemyRunRepository(session)
                events = SqlAlchemyApplicationEventRepository(session)
                outbox = SqlAlchemyApplicationOutboxRepository(session)
                now = datetime.now(UTC)
                await runs.add(
                    Run(
                        run_id=run_a,
                        tenant_id=tenant_id,
                        scenario_id="scenario-2",
                        status=RunStatus.ACTIVE,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.flush()
                event_a1 = await events.append(
                    tenant_id=tenant_id,
                    run_id=run_a,
                    event_type=ApplicationEventType.EXTERNAL_SIGNAL,
                    payload={"ordinal": 1},
                )
                event_a2 = await events.append(
                    tenant_id=tenant_id,
                    run_id=run_a,
                    event_type=ApplicationEventType.EXTERNAL_SIGNAL,
                    payload={"ordinal": 2},
                )
                await outbox.enqueue(
                    tenant_id=tenant_id,
                    run_id=run_a,
                    event_seq=event_a1.seq,
                    topic=topic,
                    payload={"ordinal": 1},
                )
                await outbox.enqueue(
                    tenant_id=tenant_id,
                    run_id=run_a,
                    event_seq=event_a2.seq,
                    topic=topic,
                    payload={"ordinal": 2},
                )
                await session.commit()

            async with factory() as session:
                await session.begin()
                outbox = SqlAlchemyApplicationOutboxRepository(session)
                claimed_a1 = await outbox.claim_next(
                    topic=topic,
                    lease_seconds=60,
                )
                assert claimed_a1 is not None
                assert claimed_a1.run_id == run_a
                assert claimed_a1.event_seq == event_a1.seq
                await session.commit()

            # Add another run after A1 is leased. Its head event must remain
            # independently claimable while A2 is blocked behind A1.
            async with factory() as session:
                await session.begin()
                runs = SqlAlchemyRunRepository(session)
                events = SqlAlchemyApplicationEventRepository(session)
                outbox = SqlAlchemyApplicationOutboxRepository(session)
                now = datetime.now(UTC)
                await runs.add(
                    Run(
                        run_id=run_b,
                        tenant_id=tenant_id,
                        scenario_id="scenario-2",
                        status=RunStatus.ACTIVE,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await session.flush()
                event_b1 = await events.append(
                    tenant_id=tenant_id,
                    run_id=run_b,
                    event_type=ApplicationEventType.EXTERNAL_SIGNAL,
                    payload={"ordinal": 1},
                )
                await outbox.enqueue(
                    tenant_id=tenant_id,
                    run_id=run_b,
                    event_seq=event_b1.seq,
                    topic=topic,
                    payload={"ordinal": 1},
                )
                await session.commit()

            async with factory() as session:
                await session.begin()
                outbox = SqlAlchemyApplicationOutboxRepository(session)
                claimed_b1 = await outbox.claim_next(
                    topic=topic,
                    lease_seconds=60,
                )
                assert claimed_b1 is not None
                assert claimed_b1.run_id == run_b
                assert claimed_b1.event_seq == event_b1.seq
                await outbox.mark_delivered(
                    tenant_id=tenant_id,
                    run_id=run_b,
                    outbox_id=claimed_b1.outbox_id,
                )
                await session.commit()

            # A1 is still leased and undelivered, therefore A2 must not overtake it.
            async with factory() as session:
                await session.begin()
                outbox = SqlAlchemyApplicationOutboxRepository(session)
                assert (
                    await outbox.claim_next(topic=topic, lease_seconds=60)
                    is None
                )
                await session.commit()

            async with factory() as session:
                await session.begin()
                outbox = SqlAlchemyApplicationOutboxRepository(session)
                await outbox.mark_delivered(
                    tenant_id=tenant_id,
                    run_id=run_a,
                    outbox_id=claimed_a1.outbox_id,
                )
                await session.commit()

            async with factory() as session:
                await session.begin()
                outbox = SqlAlchemyApplicationOutboxRepository(session)
                claimed_a2 = await outbox.claim_next(
                    topic=topic,
                    lease_seconds=60,
                )
                assert claimed_a2 is not None
                assert claimed_a2.run_id == run_a
                assert claimed_a2.event_seq == event_a2.seq
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_product_api_exposes_ingestion_with_durable_adk_consumer(
    monkeypatch,
):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    suffix = uuid4().hex[:10]
    tenant_id = f"TENANT-7C-API-{suffix}"
    headers = {"X-Tenant-ID": tenant_id}

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["scenario2_checkpoint"] == "7C-adk-dispatch"
        assert health.json()["scenario2_ingestion_wired"] is True
        assert health.json()["scenario2_dispatch_consumer_wired"] is True

        started = client.post(
            "/api/v1/scenario-2/runs",
            headers=headers,
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]
        assert started.json()["operational_signals"] == []
        assert "fixture_state" not in started.json()

        step = client.post(
            f"/api/v1/scenario-2/runs/{run_id}/simulator/next",
            headers=headers,
        )
        assert step.status_code == 200, step.text
        body = step.json()
        assert body["next_index"] == 1
        assert body["ingested"]["dispatch_queued"] is True
        assert body["ingested"]["evidence_id"]
        assert body["ingested"]["signal"]["received_at"].endswith(
            ("Z", "+00:00")
        )

        restored = client.get(
            f"/api/v1/scenario-2/runs/{run_id}",
            headers=headers,
        )
        assert restored.status_code == 200
        assert len(restored.json()["operational_signals"]) == 1
        assert "fixture_state" not in restored.json()

        # The running Scenario 1 worker must not consume the separate Scenario 2
        # topic. This row is the explicit handoff point to the later ADK worker.
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        queued = asyncio.run(
            _outbox_rows(factory, tenant_id=tenant_id, run_id=run_id)
        )
        asyncio.run(engine.dispose())
        assert len(queued) == 1
        assert queued[0].topic == SCENARIO2_AGENT_DISPATCH_TOPIC
        assert queued[0].delivered_at is None
        assert queued[0].attempt_count == 0

        timeline = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=headers,
            params={"after_seq": 0, "limit": 100},
        )
        assert timeline.status_code == 200
        assert [item["event_type"] for item in timeline.json()["events"]] == [
            "simulation.started",
            "external.signal",
        ]


def test_scenario2_start_is_product_only_and_persists_restart_safe_state():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-START-{suffix}"
        database_url = _database_url()
        engine = create_engine(DatabaseSettings(url=database_url))
        factory = create_session_factory(engine)
        start, _, state_service, _, _, _ = _services(factory)
        try:
            result = await start.start(tenant_id=tenant_id)
            assert not isinstance(result, OperationFailure)
            run_id = result.run.run_id
            assert result.run.scenario_id == "scenario-2"
            assert result.fixture_state.dependency_status is HealthState.DEGRADED

            snapshot = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert snapshot is not None
            assert snapshot.operational_signals == ()
            assert snapshot.service_incidents == ()
            assert snapshot.latest_event_seq == 1
            assert snapshot.fixture_state.dependency_status is HealthState.DEGRADED

            # Drop all SQLAlchemy process-local state and reconnect only
            # from DATABASE_URL, then prove Product state is still complete.
            await engine.dispose()
            engine = create_engine(DatabaseSettings(url=database_url))
            factory = create_session_factory(engine)
            restarted_state = Scenario2StateService(
                SqlAlchemyScenario2StateQuery(factory)
            )
            restored = await restarted_state.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert restored == snapshot

            outbox = await _outbox_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert outbox == []
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_each_signal_persists_fact_event_and_separate_dispatch_envelope():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-INGEST-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, state_service, _, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id
            template = CANONICAL_SIGNAL_SEQUENCE[0]

            result = await ingestion.ingest(
                tenant_id=tenant_id,
                run_id=run_id,
                signal_input=Scenario2SignalInput(
                    source=template.source,
                    site_id=template.site_id,
                    service_key=template.service_key,
                    symptom_key=template.symptom_key,
                    source_ref=template.source_ref,
                    safe_payload=dict(template.safe_payload),
                    signal_id_hint=template.signal_id,
                    incident_id_hint=template.incident_id,
                ),
            )
            assert not isinstance(result, OperationFailure)
            assert result.replayed is False
            assert result.event is not None
            assert result.dispatch is not None
            assert result.event.event_type is ApplicationEventType.EXTERNAL_SIGNAL
            assert result.dispatch.topic == SCENARIO2_AGENT_DISPATCH_TOPIC
            assert result.dispatch.delivered_at is None
            assert result.evidence.source_type is EvidenceSourceType.OPERATIONAL_SIGNAL
            assert result.evidence.payload.signal_id == result.signal.signal_id
            assert result.evidence.captured_at == result.signal.received_at
            assert result.evidence.expires_at is not None
            assert result.evidence.expires_at > result.evidence.captured_at
            assert result.signal.received_at.tzinfo is not None
            assert result.signal.received_at.astimezone(UTC).utcoffset().total_seconds() == 0

            snapshot = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert snapshot is not None
            assert len(snapshot.operational_signals) == 1
            assert len(snapshot.service_incidents) == 1
            assert snapshot.latest_event_seq == 2

            rows = await _outbox_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(rows) == 1
            assert rows[0].topic == SCENARIO2_AGENT_DISPATCH_TOPIC
            assert rows[0].event_seq == result.event.seq
            assert rows[0].payload["signal_id"] == result.signal.signal_id
            assert rows[0].payload["evidence_id"] == result.evidence.evidence_id

            evidence_rows = await _evidence_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(evidence_rows) == 1
            assert evidence_rows[0].evidence_id == result.evidence.evidence_id
            assert evidence_rows[0].source_type == EvidenceSourceType.OPERATIONAL_SIGNAL.value
            assert evidence_rows[0].payload["signal_id"] == result.signal.signal_id
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_each_new_signal_source_identity_creates_separate_service_incident():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-SITES-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, _, state_service, simulator, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id

            first = await simulator.next(tenant_id=tenant_id, run_id=run_id)
            second = await simulator.next(tenant_id=tenant_id, run_id=run_id)
            assert not isinstance(first, OperationFailure)
            assert not isinstance(second, OperationFailure)
            assert first.ingested is not None
            assert second.ingested is not None
            assert (
                first.ingested.service_incident.incident_id
                != second.ingested.service_incident.incident_id
            )

            after_two = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert after_two is not None
            assert len(after_two.operational_signals) == 2
            assert len(after_two.service_incidents) == 2
            assert (
                after_two.operational_signals[0].incident_id
                != after_two.operational_signals[1].incident_id
            )

            third = await simulator.next(tenant_id=tenant_id, run_id=run_id)
            assert not isinstance(third, OperationFailure)
            after_three = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert after_three is not None
            assert len(after_three.operational_signals) == 3
            assert len(after_three.service_incidents) == 3
            assert len(
                {
                    signal.incident_id
                    for signal in after_three.operational_signals
                }
            ) == 3
            assert third.complete is True
            signal_evidence = await _evidence_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(signal_evidence) == 3
            assert all(
                row.source_type == EvidenceSourceType.OPERATIONAL_SIGNAL.value
                for row in signal_evidence
            )

            # Product ingestion must not manufacture a Major Incident proposal.
            async with factory() as session:
                proposal_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ActionProposalRow)
                        .where(
                            ActionProposalRow.tenant_id == tenant_id,
                            ActionProposalRow.run_id == run_id,
                        )
                    )
                    or 0
                )
                work_order_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(FieldServiceWorkOrderRow)
                        .where(
                            FieldServiceWorkOrderRow.tenant_id == tenant_id,
                            FieldServiceWorkOrderRow.run_id == run_id,
                        )
                    )
                    or 0
                )
            assert proposal_count == 0
            assert work_order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_signal_replay_is_idempotent_and_conflicting_replay_is_rejected():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-REPLAY-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, state_service, _, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id
            template = CANONICAL_SIGNAL_SEQUENCE[0]
            input_value = Scenario2SignalInput(
                source=template.source,
                site_id=template.site_id,
                service_key=template.service_key,
                symptom_key=template.symptom_key,
                source_ref=template.source_ref,
                safe_payload=dict(template.safe_payload),
            )

            first = await ingestion.ingest(
                tenant_id=tenant_id,
                run_id=run_id,
                signal_input=input_value,
            )
            replay = await ingestion.ingest(
                tenant_id=tenant_id,
                run_id=run_id,
                signal_input=input_value,
            )
            assert not isinstance(first, OperationFailure)
            assert not isinstance(replay, OperationFailure)
            assert replay.replayed is True
            assert replay.event is None
            assert replay.dispatch is None
            assert replay.signal.signal_id == first.signal.signal_id
            assert replay.evidence.evidence_id == first.evidence.evidence_id

            conflict = await ingestion.ingest(
                tenant_id=tenant_id,
                run_id=run_id,
                signal_input=Scenario2SignalInput(
                    source=template.source,
                    site_id=template.site_id,
                    service_key=template.service_key,
                    symptom_key=template.symptom_key,
                    source_ref=template.source_ref,
                    safe_payload={"kind": "different-fact"},
                ),
            )
            assert isinstance(conflict, OperationFailure)
            assert dict(conflict.error.details)["reason"] == "conflicting_signal_replay"

            snapshot = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert snapshot is not None
            assert len(snapshot.operational_signals) == 1
            assert snapshot.latest_event_seq == 2
            outbox = await _outbox_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(outbox) == 1
            evidence_rows = await _evidence_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(evidence_rows) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_simulator_progress_survives_service_recreation_between_every_event():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-RESTART-{suffix}"
        database_url = _database_url()
        engine = create_engine(DatabaseSettings(url=database_url))
        factory = create_session_factory(engine)
        start, _, _, simulator, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id

            for expected_count in (1, 2, 3):
                step = await simulator.next(
                    tenant_id=tenant_id,
                    run_id=run_id,
                )
                assert not isinstance(step, OperationFailure)
                assert len(step.state.operational_signals) == expected_count

                # Simulate a process restart: dispose the engine and reconstruct
                # every Product service from PostgreSQL before the next event.
                await engine.dispose()
                engine = create_engine(DatabaseSettings(url=database_url))
                factory = create_session_factory(engine)
                _, _, _, simulator, _, _ = _services(factory)

            done = await simulator.next(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert not isinstance(done, OperationFailure)
            assert done.complete is True
            assert done.ingested is None
            assert done.next_index == 3

            outbox = await _outbox_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(outbox) == 3
            assert all(
                row.topic == SCENARIO2_AGENT_DISPATCH_TOPIC
                and row.delivered_at is None
                for row in outbox
            )
            evidence_rows = await _evidence_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(evidence_rows) == 3
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_manual_ingest_of_canonical_source_identity_advances_simulator():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-MIXED-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, _, simulator, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id
            first = CANONICAL_SIGNAL_SEQUENCE[0]

            manual = await ingestion.ingest(
                tenant_id=tenant_id,
                run_id=run_id,
                signal_input=Scenario2SignalInput(
                    source=first.source,
                    site_id=first.site_id,
                    service_key=first.service_key,
                    symptom_key=first.symptom_key,
                    source_ref=first.source_ref,
                    safe_payload=dict(first.safe_payload),
                ),
            )
            assert not isinstance(manual, OperationFailure)
            assert manual.signal.signal_id != first.signal_id

            step = await simulator.next(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert not isinstance(step, OperationFailure)
            assert step.ingested is not None
            assert step.ingested.signal.source_ref == CANONICAL_SIGNAL_SEQUENCE[1].source_ref
            assert len(step.state.operational_signals) == 2
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_simulator_rejects_conflicting_fact_that_reuses_canonical_source_identity():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-SPOOF-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, state_service, simulator, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id
            first = CANONICAL_SIGNAL_SEQUENCE[0]

            spoofed = await ingestion.ingest(
                tenant_id=tenant_id,
                run_id=run_id,
                signal_input=Scenario2SignalInput(
                    source=first.source,
                    site_id=CANONICAL_SIGNAL_SEQUENCE[2].site_id,
                    service_key=first.service_key,
                    symptom_key=first.symptom_key,
                    source_ref=first.source_ref,
                    safe_payload=dict(first.safe_payload),
                ),
            )
            assert not isinstance(spoofed, OperationFailure)

            step = await simulator.next(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert isinstance(step, OperationFailure)
            assert (
                dict(step.error.details)["reason"]
                == "canonical_signal_identity_conflict"
            )

            state = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert state is not None
            assert len(state.operational_signals) == 1
            outbox = await _outbox_rows(
                factory,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert len(outbox) == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_simulator_completion_handles_out_of_order_manual_canonical_fact():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-OUT-OF-ORDER-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, _, simulator, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id

            for index in (0, 2):
                template = CANONICAL_SIGNAL_SEQUENCE[index]
                result = await ingestion.ingest(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    signal_input=Scenario2SignalInput(
                        source=template.source,
                        site_id=template.site_id,
                        service_key=template.service_key,
                        symptom_key=template.symptom_key,
                        source_ref=template.source_ref,
                        safe_payload=dict(template.safe_payload),
                    ),
                )
                assert not isinstance(result, OperationFailure)

            step = await simulator.next(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert not isinstance(step, OperationFailure)
            assert step.ingested is not None
            assert (
                step.ingested.signal.source_ref
                == CANONICAL_SIGNAL_SEQUENCE[1].source_ref
            )
            assert step.complete is True
            assert step.next_index == 3
            assert len(step.state.operational_signals) == 3
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_controlled_fixture_transitions_are_persisted_and_source_visible_after_restart():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-FIXTURE-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, _, _, _, fixture, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            run_id = started.run.run_id

            healthy = await fixture.set_dependency_status(
                tenant_id=tenant_id,
                run_id=run_id,
                status=HealthState.HEALTHY,
            )
            assert not isinstance(healthy, OperationFailure)
            with_major = await fixture.set_matching_major_incident(
                tenant_id=tenant_id,
                run_id=run_id,
                major_incident_id=STALE_MATCHING_MAJOR_INCIDENT_ID,
            )
            assert not isinstance(with_major, OperationFailure)

            # Recreate the source adapter to model a process restart.
            _, _, _, _, _, sources = _services(factory)
            status = await sources.get_external_dependency_status(
                tenant_id=tenant_id,
                run_id=run_id,
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            )
            search = await sources.search_major_incidents(
                tenant_id=tenant_id,
                run_id=run_id,
                service_key=SERVICE_KEY,
                correlation_key="payment_gateway_timeout",
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            )
            assert status is not None
            assert status.status is HealthState.HEALTHY
            assert search.open_major_incident_ids == (
                STALE_MATCHING_MAJOR_INCIDENT_ID,
            )

            cleared = await fixture.set_matching_major_incident(
                tenant_id=tenant_id,
                run_id=run_id,
                major_incident_id="   ",
            )
            assert not isinstance(cleared, OperationFailure)
            _, _, _, _, _, sources = _services(factory)
            cleared_search = await sources.search_major_incidents(
                tenant_id=tenant_id,
                run_id=run_id,
                service_key=SERVICE_KEY,
                correlation_key="payment_gateway_timeout",
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            )
            assert cleared_search.open_major_incident_ids == ()

            async with factory() as session:
                await session.begin()
                runs = SqlAlchemyRunRepository(session)
                run = await runs.get(tenant_id=tenant_id, run_id=run_id)
                assert run is not None
                await runs.save(
                    replace(
                        run,
                        status=RunStatus.COMPLETED,
                        updated_at=datetime.now(UTC),
                    )
                )
                await session.commit()

            closed = await fixture.set_dependency_status(
                tenant_id=tenant_id,
                run_id=run_id,
                status=HealthState.DEGRADED,
            )
            assert isinstance(closed, OperationFailure)
            assert dict(closed.error.details)["reason"] == "run_closed"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_cross_tenant_state_is_not_visible():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-ISO-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, _, state_service, _, _, sources = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            foreign_tenant = f"OTHER-{tenant_id}"
            assert (
                await state_service.get(
                    tenant_id=foreign_tenant,
                    run_id=started.run.run_id,
                )
                is None
            )
            assert (
                await sources.get_local_service_health(
                    tenant_id=foreign_tenant,
                    run_id=started.run.run_id,
                    site_id=CANONICAL_SIGNAL_SEQUENCE[0].site_id,
                    service_key=SERVICE_KEY,
                )
                is None
            )
            with pytest.raises(RuntimeError, match="Product state is unavailable"):
                await sources.get_service_dependencies(
                    tenant_id=foreign_tenant,
                    run_id=started.run.run_id,
                    service_key=SERVICE_KEY,
                )
            with pytest.raises(RuntimeError, match="Product state is unavailable"):
                await sources.search_major_incidents(
                    tenant_id=foreign_tenant,
                    run_id=started.run.run_id,
                    service_key=SERVICE_KEY,
                    correlation_key="payment_gateway_timeout",
                    dependency_id=ACMEPAY_DEPENDENCY_ID,
                )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_unsafe_signal_payload_is_rejected_without_persistence():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-SAFE-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, _, _, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            template = CANONICAL_SIGNAL_SEQUENCE[0]
            result = await ingestion.ingest(
                tenant_id=tenant_id,
                run_id=started.run.run_id,
                signal_input=Scenario2SignalInput(
                    source=template.source,
                    site_id=template.site_id,
                    service_key=template.service_key,
                    symptom_key=template.symptom_key,
                    source_ref=template.source_ref,
                    safe_payload={"api_key": "must-not-persist"},
                ),
            )
            assert isinstance(result, OperationFailure)
            assert dict(result.error.details)["reason"] == "unsafe_signal_payload"

            async with factory() as session:
                count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(OperationalSignalRow)
                        .where(
                            OperationalSignalRow.tenant_id == tenant_id,
                            OperationalSignalRow.run_id == started.run.run_id,
                        )
                    )
                    or 0
                )
            assert count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())
