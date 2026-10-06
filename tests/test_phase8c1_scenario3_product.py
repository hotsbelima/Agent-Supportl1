from __future__ import annotations

import asyncio
from datetime import timedelta
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from product_api.app import build_container_from_env, create_app
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
from product_backend.contracts.events import AGENT_DISPATCH_TOPIC
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
