"""Focused durable Scenario 2 Product-event -> native-ADK dispatch checks.

The worker is tested with a deterministic runtime double because these checks
exercise durable Product delivery. Native ADK's persisted Session mechanics are
checked against the real DatabaseSessionService in the restart test, while live
Gemini acceptance remains separately credential-gated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from agent_runtime.scenario2_service import _find_scenario2_event_correlation
from agent_runtime.sessions import create_database_session_service, get_run_session
from product_api.dispatch import Scenario2DispatchWorker
from product_api.scenario2_fixture import CANONICAL_SIGNAL_SEQUENCE
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.results import OperationFailure
from product_backend.application.scenario2_ingestion import (
    Scenario2RunStartService,
    Scenario2SignalIngestionService,
)
from product_backend.application.scenario2_state import Scenario2StateService
from product_backend.contracts.events import SCENARIO2_AGENT_DISPATCH_TOPIC
from product_backend.contracts.scenario2_ingestion import Scenario2SignalInput
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.scenario2_state import SqlAlchemyScenario2StateQuery
from product_backend.persistence.tables import (
    ActionProposalRow,
    ApplicationOutboxRow,
    FieldServiceWorkOrderRow,
)
from product_backend.persistence.uow import (
    SqlAlchemyDispatchUnitOfWork,
    SqlAlchemyLifecycleUnitOfWork,
    SqlAlchemyScenario2RunStartUnitOfWork,
    SqlAlchemyScenario2SignalIngestionUnitOfWork,
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 7C dispatch tests")
    return normalize_database_url(value)


@dataclass
class _RecordingScenario2Runtime:
    fail_once_event_id: str | None = None

    gemini_configured = True

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.invocation_by_event: dict[str, str] = {}
        self._failed = False

    async def invoke_operational_signal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        product_event_id: str,
        operational_fact: dict[str, object],
    ) -> SimpleNamespace:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "product_event_id": product_event_id,
                "operational_fact": operational_fact,
            }
        )
        if (
            product_event_id == self.fail_once_event_id
            and not self._failed
        ):
            self._failed = True
            raise RuntimeError("synthetic transient provider failure")
        invocation_id = self.invocation_by_event.setdefault(
            product_event_id,
            f"INV-{len(self.invocation_by_event) + 1}",
        )
        return SimpleNamespace(
            session_id=run_id,
            invocation_id=invocation_id,
            final_answer="persisted native result",
            recoverable=True,
        )


def _services(factory):
    return (
        Scenario2RunStartService(
            lambda: SqlAlchemyScenario2RunStartUnitOfWork(factory)
        ),
        Scenario2SignalIngestionService(
            lambda: SqlAlchemyScenario2SignalIngestionUnitOfWork(factory)
        ),
        Scenario2StateService(SqlAlchemyScenario2StateQuery(factory)),
        ApplicationLifecycleService(
            lambda: SqlAlchemyLifecycleUnitOfWork(factory)
        ),
    )


async def _enqueue_three(ingestion, *, tenant_id: str, run_id: str) -> list[str]:
    event_ids: list[str] = []
    for template in CANONICAL_SIGNAL_SEQUENCE:
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
        assert result.event is not None
        event_ids.append(result.event.event_id)
    return event_ids


async def _scenario2_rows(factory, *, tenant_id: str, run_id: str):
    async with factory() as session:
        result = await session.execute(
            select(ApplicationOutboxRow)
            .where(
                ApplicationOutboxRow.tenant_id == tenant_id,
                ApplicationOutboxRow.run_id == run_id,
                ApplicationOutboxRow.topic == SCENARIO2_AGENT_DISPATCH_TOPIC,
            )
            .order_by(ApplicationOutboxRow.event_seq)
        )
        return result.scalars().all()


def _worker(factory, state, lifecycle, runtime):
    return Scenario2DispatchWorker(
        uow_factory=lambda: SqlAlchemyDispatchUnitOfWork(factory),
        state_service=state,
        lifecycle_service=lifecycle,
        agent_runtime=runtime,  # type: ignore[arg-type]
        poll_interval_seconds=0.01,
        lease_seconds=5.0,
        invocation_timeout_seconds=1.0,
    )


def test_three_product_events_have_three_ordered_invocations_in_one_run():
    async def scenario() -> None:
        tenant_id = f"TENANT-7C-ADK-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, state, lifecycle = _services(factory)
        runtime = _RecordingScenario2Runtime()
        worker = _worker(factory, state, lifecycle, runtime)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            event_ids = await _enqueue_three(
                ingestion,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            for _ in event_ids:
                assert await worker.dispatch_once() is True

            rows = await _scenario2_rows(
                factory,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            assert [row.delivered_at is not None for row in rows] == [True] * 3
            assert [call["product_event_id"] for call in runtime.calls] == event_ids
            assert [call["run_id"] for call in runtime.calls] == [
                started.run.run_id
            ] * 3
            assert list(runtime.invocation_by_event) == event_ids
            assert len(set(runtime.invocation_by_event.values())) == 3

            # 7C owns no Major Incident or Scenario 1 work-order action.
            async with factory() as session:
                proposal_count = int(
                    await session.scalar(
                        select(func.count())
                        .select_from(ActionProposalRow)
                        .where(
                            ActionProposalRow.tenant_id == tenant_id,
                            ActionProposalRow.run_id == started.run.run_id,
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
                            FieldServiceWorkOrderRow.run_id == started.run.run_id,
                        )
                    )
                    or 0
                )
                assert proposal_count == 0
                assert work_order_count == 0
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_undelivered_first_event_blocks_later_event_and_redelivery_is_one_invocation():
    async def scenario() -> None:
        tenant_id = f"TENANT-7C-ORDER-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        start, ingestion, state, lifecycle = _services(factory)
        try:
            started = await start.start(tenant_id=tenant_id)
            assert not isinstance(started, OperationFailure)
            event_ids = await _enqueue_three(
                ingestion,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            runtime = _RecordingScenario2Runtime(fail_once_event_id=event_ids[0])
            worker = _worker(factory, state, lifecycle, runtime)

            assert await worker.dispatch_once() is True
            assert [call["product_event_id"] for call in runtime.calls] == [event_ids[0]]
            # The first row is rescheduled; head-of-line ordering makes event 2
            # ineligible even though it was enqueued and due.
            assert await worker.dispatch_once() is False
            assert [call["product_event_id"] for call in runtime.calls] == [event_ids[0]]

            rows = await _scenario2_rows(
                factory,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
            )
            async with factory() as session:
                await session.execute(
                    update(ApplicationOutboxRow)
                    .where(ApplicationOutboxRow.outbox_id == rows[0].outbox_id)
                    .values(available_at=datetime.now(UTC) - timedelta(seconds=1))
                )
                await session.commit()
            for _ in event_ids:
                if not await worker.dispatch_once():
                    break

            assert [call["product_event_id"] for call in runtime.calls] == [
                event_ids[0],
                event_ids[0],
                event_ids[1],
                event_ids[2],
            ]
            # The retry invokes the runtime again, but native-history identity
            # reconciliation means it still has one independent invocation.
            assert len(runtime.invocation_by_event) == 3
            assert runtime.invocation_by_event[event_ids[0]] == "INV-1"
        finally:
            await engine.dispose()

    asyncio.run(scenario())


class _FakeEvent:
    def __init__(
        self,
        *,
        author: str,
        invocation_id: str,
        text: str,
        final: bool = False,
    ):
        self.author = author
        self.invocation_id = invocation_id
        self.content = SimpleNamespace(
            parts=[SimpleNamespace(text=text, thought=False)]
        )
        self.actions = SimpleNamespace(end_of_agent=final)
        self._final = final

    def is_final_response(self) -> bool:
        return self._final


def test_native_history_correlation_recovers_the_same_invocation_id():
    event_id = "EVENT-7C-REDELIVERY"
    invocation_id = "INV-7C-ONE"
    user = _FakeEvent(
        author="user",
        invocation_id=invocation_id,
        text=json.dumps(
            {
                "type": "scenario2_operational_signal",
                "product_event_id": event_id,
                "payload": {},
            }
        ),
    )
    final = _FakeEvent(
        author="scenario2_operational_correlation_agent",
        invocation_id=invocation_id,
        text="acknowledged",
        final=True,
    )
    correlation = _find_scenario2_event_correlation(
        [user, final],
        product_event_id=event_id,
    )
    assert correlation is not None
    assert correlation.invocation_id == invocation_id
    assert correlation.settled is True


def test_native_history_rejects_multiple_invocations_for_one_product_event():
    event_id = "EVENT-7C-DUPLICATE"
    first = _FakeEvent(
        author="user",
        invocation_id="INV-7C-A",
        text=json.dumps(
            {
                "type": "scenario2_operational_signal",
                "product_event_id": event_id,
                "payload": {},
            }
        ),
    )
    second = _FakeEvent(
        author="user",
        invocation_id="INV-7C-B",
        text=json.dumps(
            {
                "type": "scenario2_operational_signal",
                "product_event_id": event_id,
                "payload": {},
            }
        ),
    )
    with pytest.raises(
        RuntimeError,
        match="multiple native ADK invocations",
    ):
        _find_scenario2_event_correlation(
            [first, second],
            product_event_id=event_id,
        )


def test_native_adk_session_survives_process_style_reconstruction_between_events():
    async def scenario() -> None:
        tenant_id = f"TENANT-7C-SESSION-{uuid4().hex[:10]}"
        run_id = f"RUN-7C-SESSION-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        service = create_database_session_service(engine)
        try:
            await service.prepare_tables()
            created = await service.create_session(
                app_name="autonomous-l1-incident-agent",
                user_id=tenant_id,
                session_id=run_id,
                state={},
            )
            assert created.id == run_id
        finally:
            await engine.dispose()

        replacement_engine = create_engine(DatabaseSettings(url=_database_url()))
        replacement_service = create_database_session_service(replacement_engine)
        try:
            restored = await get_run_session(
                replacement_service,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert restored is not None
            assert restored.id == run_id
            assert restored.user_id == tenant_id
        finally:
            await replacement_engine.dispose()

    asyncio.run(scenario())
