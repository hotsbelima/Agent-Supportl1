from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from product_api.app import build_container_from_env, create_app
from product_api.dispatch import Scenario1DispatchWorker
from product_api.scenario3_fixture import (
    ACMEPAY_DEPENDENCY_ID,
    AFFECTED_DEVICE_ID,
    INCIDENT_ID,
    SCENARIO_ID,
    SERVICE_KEY,
    SITE_ID,
    SYMPTOM_KEY,
    Scenario3FixtureSources,
)
from product_backend.application.run_state import RunStateService
from product_backend.application.scenario3_read_tools import (
    Scenario3EvidenceTtlPolicy,
    Scenario3ProviderReadService,
)
from product_backend.contracts.events import (
    AGENT_DISPATCH_TOPIC,
    ApplicationOutboxRecord,
)
from product_backend.contracts.scenario2_tools import (
    GetExternalDependencyStatusRequest,
    GetServiceDependenciesRequest,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import EvidenceSourceType, HealthState
from product_backend.domain.errors import ErrorCode
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.run_state import SqlAlchemyRunStateQuery
from product_backend.persistence.tables import ApplicationOutboxRow
from product_backend.persistence.uow import SqlAlchemyToolReadUnitOfWork


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 8C1 persistence tests")
    return normalize_database_url(value)


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def _new_db():
    engine = create_engine(DatabaseSettings(url=_database_url()))
    return engine, create_session_factory(engine)


def _start_without_agent_workers(tenant_id: str) -> dict:
    container = build_container_from_env()
    container.dispatch_worker = None
    container.scenario2_dispatch_worker = None
    container.agent_runtime = None
    container.scenario2_agent_runtime = None
    try:
        with TestClient(create_app(container=container)) as client:
            response = client.post(
                "/api/v1/scenario-3/runs",
                headers=_headers(tenant_id),
            )
            assert response.status_code == 201, response.text
            state = response.json()
            events = client.get(
                f"/api/v1/runs/{state['run']['run_id']}/events",
                headers=_headers(tenant_id),
            )
            assert events.status_code == 200, events.text
            return {"state": state, "events": events.json()["events"]}
    finally:
        asyncio.run(container.close())


async def _outbox_for_run(*, tenant_id: str, run_id: str):
    engine, factory = _new_db()
    try:
        async with factory() as session:
            result = await session.execute(
                select(ApplicationOutboxRow).where(
                    ApplicationOutboxRow.tenant_id == tenant_id,
                    ApplicationOutboxRow.run_id == run_id,
                )
            )
            return result.scalars().all()
    finally:
        await engine.dispose()


def _provider_service(factory) -> Scenario3ProviderReadService:
    fixture = Scenario3FixtureSources()
    return Scenario3ProviderReadService(
        read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
        dependency_mapping=fixture,
        dependency_status=fixture,
        ttl_policy=Scenario3EvidenceTtlPolicy(
            external_dependency_status=timedelta(minutes=2),
        ),
    )


def test_phase8c1_start_persists_device_incident_safe_context_and_generic_outbox():
    tenant_id = f"TENANT-8C1-{uuid4().hex[:8]}"
    started = _start_without_agent_workers(tenant_id)
    state = started["state"]
    events = started["events"]
    run_id = state["run"]["run_id"]

    assert state["run"]["scenario_id"] == SCENARIO_ID
    assert state["run"]["status"] == "ACTIVE"
    assert len(state["incidents"]) == 1
    incident = state["incidents"][0]
    assert incident["incident_id"] == INCIDENT_ID
    assert incident["site_id"] == SITE_ID
    assert incident["reported_device_id"] == AFFECTED_DEVICE_ID

    assert [item["event_type"] for item in events] == [
        "simulation.started",
        "external.signal",
        "run.status_changed",
    ]
    signal = events[1]["payload"]
    assert signal["signal_type"] == "itsm.incident.created"
    assert signal["details"]["service_key"] == SERVICE_KEY
    assert signal["details"]["symptom_key"] == SYMPTOM_KEY

    forbidden = {
        "provider_status",
        "dependency_status",
        "dependency_id",
        "attachment_id",
        "switch_id",
        "port_id",
        "diagnosis",
        "action",
        "replan",
    }
    assert forbidden.isdisjoint(signal["details"])

    outbox = asyncio.run(
        _outbox_for_run(tenant_id=tenant_id, run_id=run_id)
    )
    assert len(outbox) == 1
    assert outbox[0].event_seq == 2
    assert outbox[0].topic == AGENT_DISPATCH_TOPIC
    assert outbox[0].payload["event_id"] == events[1]["event_id"]
    assert outbox[0].payload["signal"] == signal
    assert outbox[0].delivered_at is None


def test_phase8c1_provider_reads_are_grounded_in_same_run_product_facts_and_evidence():
    tenant_id = f"TENANT-8C1-A-{uuid4().hex[:8]}"
    other_tenant = f"TENANT-8C1-B-{uuid4().hex[:8]}"
    run_id = _start_without_agent_workers(tenant_id)["state"]["run"]["run_id"]
    other_run_id = _start_without_agent_workers(tenant_id)["state"]["run"]["run_id"]

    async def scenario() -> None:
        engine, factory = _new_db()
        try:
            service = _provider_service(factory)
            context = ToolCallContext(tenant_id=tenant_id, run_id=run_id)

            unknown_service = await service.get_service_dependencies(
                context,
                GetServiceDependenciesRequest(service_key="inventory"),
            )
            assert unknown_service.ok is False
            assert unknown_service.error.code is ErrorCode.CONTEXT_MISMATCH

            wrong_tenant = await service.get_service_dependencies(
                ToolCallContext(tenant_id=other_tenant, run_id=run_id),
                GetServiceDependenciesRequest(service_key=SERVICE_KEY),
            )
            assert wrong_tenant.ok is False
            assert wrong_tenant.error.code is ErrorCode.CONTEXT_MISMATCH

            before_mapping = await service.get_external_dependency_status(
                context,
                GetExternalDependencyStatusRequest(
                    dependency_id=ACMEPAY_DEPENDENCY_ID
                ),
            )
            assert before_mapping.ok is False
            assert before_mapping.error.code is ErrorCode.CONTEXT_MISMATCH

            mapping = await service.get_service_dependencies(
                context,
                GetServiceDependenciesRequest(service_key=SERVICE_KEY),
            )
            assert mapping.ok is True
            assert len(mapping.mappings) == 1
            assert mapping.mappings[0].dependency_id == ACMEPAY_DEPENDENCY_ID
            assert len(mapping.evidence) == 1
            assert (
                mapping.evidence[0].source_type
                is EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING
            )

            unknown_dependency = await service.get_external_dependency_status(
                context,
                GetExternalDependencyStatusRequest(
                    dependency_id="DEP-NOT-ESTABLISHED"
                ),
            )
            assert unknown_dependency.ok is False
            assert unknown_dependency.error.code is ErrorCode.CONTEXT_MISMATCH

            other_run_status = await service.get_external_dependency_status(
                ToolCallContext(tenant_id=tenant_id, run_id=other_run_id),
                GetExternalDependencyStatusRequest(
                    dependency_id=ACMEPAY_DEPENDENCY_ID
                ),
            )
            assert other_run_status.ok is False
            assert other_run_status.error.code is ErrorCode.CONTEXT_MISMATCH

            status = await service.get_external_dependency_status(
                context,
                GetExternalDependencyStatusRequest(
                    dependency_id=ACMEPAY_DEPENDENCY_ID
                ),
            )
            assert status.ok is True
            assert status.status.status is HealthState.HEALTHY
            assert status.status.status_detail == "operating_normally"
            assert (
                status.evidence.source_type
                is EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS
            )

            snapshot = await RunStateService(
                SqlAlchemyRunStateQuery(factory)
            ).get(tenant_id=tenant_id, run_id=run_id)
            assert snapshot is not None
            provider_evidence = [
                item
                for item in snapshot.evidence
                if item.source_type
                in {
                    EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING,
                    EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS,
                }
            ]
            assert [item.source_type for item in provider_evidence] == [
                EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING,
                EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS,
            ]
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_phase8c1_scenario1_bootstrap_keeps_historical_signal_shape():
    fixture = Scenario3FixtureSources()
    assert fixture.bootstrap().service_key == SERVICE_KEY
    assert fixture.bootstrap().symptom_key == SYMPTOM_KEY

    from product_api.scenario1_fixture import Scenario1FixtureSources

    historical = Scenario1FixtureSources().bootstrap()
    assert historical.service_key is None
    assert historical.symptom_key is None


class _GuardTestOutbox:
    def __init__(self, record: ApplicationOutboxRecord) -> None:
        self.record = record
        self.claimed = False
        self.rescheduled = 0
        self.delivered = 0

    async def claim_next(self, *, topic: str, lease_seconds: float):
        assert topic == AGENT_DISPATCH_TOPIC
        assert lease_seconds > 0
        if self.claimed:
            return None
        self.claimed = True
        return self.record

    async def reschedule(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
        delay_seconds: float,
    ):
        assert (tenant_id, run_id, outbox_id) == (
            self.record.tenant_id,
            self.record.run_id,
            self.record.outbox_id,
        )
        assert delay_seconds >= 0
        self.rescheduled += 1
        return self.record

    async def mark_delivered(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
    ):
        self.delivered += 1
        return self.record


class _GuardTestUow:
    def __init__(self, outbox: _GuardTestOutbox) -> None:
        self.outbox = outbox

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _WrongScenarioRuntime:
    gemini_configured = True

    def __init__(self) -> None:
        self.calls = 0

    async def invoke_operational_event(self, **kwargs):
        self.calls += 1
        raise AssertionError("Scenario 1 runtime must not receive Scenario 3")


class _Scenario3State:
    async def get(self, *, tenant_id: str, run_id: str):
        return SimpleNamespace(
            run=SimpleNamespace(scenario_id="scenario-3"),
            incidents=(),
        )


def test_phase8c1_scenario1_worker_defers_scenario3_envelope_until_8c2():
    now = datetime.now(UTC)
    record = ApplicationOutboxRecord(
        outbox_id="OUTBOX-8C1-GUARD",
        tenant_id="TENANT-8C1-GUARD",
        run_id="RUN-8C1-GUARD",
        event_seq=2,
        topic=AGENT_DISPATCH_TOPIC,
        payload={
            "event_id": "EVENT-8C1-GUARD",
            "signal": {
                "signal_type": "itsm.incident.created",
                "details": {
                    "service_key": SERVICE_KEY,
                    "symptom_key": SYMPTOM_KEY,
                },
            },
        },
        created_at=now,
        available_at=now,
        delivered_at=None,
        attempt_count=1,
    )
    outbox = _GuardTestOutbox(record)
    runtime = _WrongScenarioRuntime()
    worker = Scenario1DispatchWorker(
        uow_factory=lambda: _GuardTestUow(outbox),
        state_service=_Scenario3State(),
        agent_runtime=runtime,
    )

    processed = asyncio.run(worker.dispatch_once())

    assert processed is True
    assert runtime.calls == 0
    assert outbox.rescheduled == 1
    assert outbox.delivered == 0
