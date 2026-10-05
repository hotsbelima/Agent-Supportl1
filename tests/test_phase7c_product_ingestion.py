from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

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
from product_backend.domain.enums import HealthState
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


def test_scenario2_start_is_product_only_and_persists_restart_safe_state():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-START-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
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

            # Rebuild the read service to model a process restart.
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
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_same_site_second_signal_reuses_service_incident_and_third_site_creates_second():
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

            after_two = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert after_two is not None
            assert len(after_two.operational_signals) == 2
            assert len(after_two.service_incidents) == 1
            assert (
                after_two.operational_signals[0].incident_id
                == after_two.operational_signals[1].incident_id
            )

            third = await simulator.next(tenant_id=tenant_id, run_id=run_id)
            assert not isinstance(third, OperationFailure)
            after_three = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert after_three is not None
            assert len(after_three.operational_signals) == 3
            assert len(after_three.service_incidents) == 2
            assert third.complete is True

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
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_simulator_progress_survives_service_recreation_between_every_event():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-RESTART-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
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

                # Recreate all Product services before the next event.
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
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_cross_tenant_state_is_not_visible():
    async def scenario() -> None:
        suffix = uuid4().hex[:10]
        tenant_id = f"TENANT-7C-ISO-{suffix}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, _, state_service, _, _, _ = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            assert (
                await state_service.get(
                    tenant_id=f"OTHER-{tenant_id}",
                    run_id=started.run.run_id,
                )
                is None
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
