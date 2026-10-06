from __future__ import annotations

import asyncio
from datetime import timedelta
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from product_api.app import create_app
from product_api.dispatch import Scenario1DispatchWorker
from product_api.scenario3_fixture import (
    AFFECTED_DEVICE_ID,
    INCIDENT_ID,
    SCENARIO_ID,
    SERVICE_KEY,
    SITE_ID,
    SYMPTOM_KEY,
)
from product_api.scenario3_sources import (
    ACMEPAY_DEPENDENCY_ID,
    ACMEPAY_NAME,
    Scenario3ProviderSources,
)
from product_backend.application.run_state import RunStateService
from product_backend.application.scenario3_provider_reads import (
    Scenario3ProviderEvidenceTtlPolicy,
    Scenario3ProviderReadService,
)
from product_backend.contracts.events import AGENT_DISPATCH_TOPIC
from product_backend.contracts.scenario3_provider_tools import (
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
from product_backend.persistence.uow import (
    SqlAlchemyDispatchUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)


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


def _start_scenario3(client: TestClient, tenant_id: str) -> dict:
    response = client.post(
        "/api/v1/scenario-3/runs",
        headers=_headers(tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _load_outbox(*, tenant_id: str, run_id: str):
    engine, factory = _new_db()
    try:
        async with factory() as session:
            result = await session.execute(
                select(ApplicationOutboxRow).where(
                    ApplicationOutboxRow.tenant_id == tenant_id,
                    ApplicationOutboxRow.run_id == run_id,
                )
            )
            return tuple(result.scalars().all())
    finally:
        await engine.dispose()


class _RecordingScenario1Runtime:
    gemini_configured = True

    def __init__(self) -> None:
        self.invocation_count = 0

    async def invoke_operational_event(self, **kwargs):
        del kwargs
        self.invocation_count += 1
        return None


async def _dispatch_once_with_scenario1_worker(
    *,
    tenant_id: str,
    run_id: str,
) -> tuple[bool, int, tuple[ApplicationOutboxRow, ...]]:
    engine, factory = _new_db()
    runtime = _RecordingScenario1Runtime()
    try:
        worker = Scenario1DispatchWorker(
            uow_factory=lambda: SqlAlchemyDispatchUnitOfWork(factory),
            state_service=RunStateService(SqlAlchemyRunStateQuery(factory)),
            agent_runtime=runtime,
        )

        # Earlier focused tests intentionally leave their Scenario 3 envelopes
        # pending. Drain enough due generic-topic envelopes to ensure this exact
        # run is claimed without deleting or mutating unrelated Product truth.
        processed_any = False
        rows: tuple[ApplicationOutboxRow, ...] = ()
        for _ in range(10):
            processed = await worker.dispatch_once()
            processed_any = processed_any or processed
            async with factory() as session:
                result = await session.execute(
                    select(ApplicationOutboxRow).where(
                        ApplicationOutboxRow.tenant_id == tenant_id,
                        ApplicationOutboxRow.run_id == run_id,
                    )
                )
                rows = tuple(result.scalars().all())
            if rows and rows[0].attempt_count > 0:
                break
            if not processed:
                break

        return processed_any, runtime.invocation_count, rows
    finally:
        await engine.dispose()


async def _exercise_provider_reads(
    *,
    tenant_id: str,
    run_id: str,
) -> dict:
    engine, factory = _new_db()
    try:
        sources = Scenario3ProviderSources()
        service = Scenario3ProviderReadService(
            read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
            dependency_mapping=sources,
            dependency_status=sources,
            ttl_policy=Scenario3ProviderEvidenceTtlPolicy(
                external_dependency_status=timedelta(minutes=2),
            ),
        )
        context = ToolCallContext(tenant_id=tenant_id, run_id=run_id)

        unknown_service = await service.get_service_dependencies(
            context,
            GetServiceDependenciesRequest(service_key="unbound_service"),
        )
        assert unknown_service.ok is False
        assert unknown_service.error.code is ErrorCode.CONTEXT_MISMATCH

        status_before_mapping = await service.get_external_dependency_status(
            context,
            GetExternalDependencyStatusRequest(
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            ),
        )
        assert status_before_mapping.ok is False
        assert status_before_mapping.error.code is ErrorCode.CONTEXT_MISMATCH

        mapping = await service.get_service_dependencies(
            context,
            GetServiceDependenciesRequest(service_key=SERVICE_KEY),
        )
        assert mapping.ok is True
        assert len(mapping.mappings) == 1
        assert mapping.mappings[0].service_key == SERVICE_KEY
        assert mapping.mappings[0].dependency_id == ACMEPAY_DEPENDENCY_ID
        assert mapping.mappings[0].dependency_name == ACMEPAY_NAME
        assert len(mapping.evidence) == 1
        assert (
            mapping.evidence[0].source_type
            is EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING
        )

        unknown_dependency = await service.get_external_dependency_status(
            context,
            GetExternalDependencyStatusRequest(dependency_id="DEP-NOT-ESTABLISHED"),
        )
        assert unknown_dependency.ok is False
        assert unknown_dependency.error.code is ErrorCode.CONTEXT_MISMATCH

        status = await service.get_external_dependency_status(
            context,
            GetExternalDependencyStatusRequest(
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            ),
        )
        assert status.ok is True
        assert status.status.dependency_id == ACMEPAY_DEPENDENCY_ID
        assert status.status.dependency_name == ACMEPAY_NAME
        assert status.status.status is HealthState.HEALTHY
        assert status.status.status_detail == "operating_normally"
        assert (
            status.evidence.source_type
            is EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS
        )

        snapshot = await SqlAlchemyRunStateQuery(factory).get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        assert snapshot is not None
        return {
            "mapping_evidence_id": mapping.evidence[0].evidence_id,
            "status_evidence_id": status.evidence.evidence_id,
            "source_types": tuple(item.source_type for item in snapshot.evidence),
        }
    finally:
        await engine.dispose()


async def _assert_context_isolation(
    *,
    owner_tenant_id: str,
    owner_run_id: str,
    other_tenant_id: str,
    other_run_id: str,
    same_tenant_other_run_id: str,
) -> None:
    engine, factory = _new_db()
    try:
        sources = Scenario3ProviderSources()
        service = Scenario3ProviderReadService(
            read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
            dependency_mapping=sources,
            dependency_status=sources,
            ttl_policy=Scenario3ProviderEvidenceTtlPolicy(
                external_dependency_status=timedelta(minutes=2),
            ),
        )

        # Establish dependency Evidence only in the owner run.
        owner_context = ToolCallContext(
            tenant_id=owner_tenant_id,
            run_id=owner_run_id,
        )
        mapping = await service.get_service_dependencies(
            owner_context,
            GetServiceDependenciesRequest(service_key=SERVICE_KEY),
        )
        assert mapping.ok is True

        wrong_tenant = await service.get_service_dependencies(
            ToolCallContext(
                tenant_id=other_tenant_id,
                run_id=owner_run_id,
            ),
            GetServiceDependenciesRequest(service_key=SERVICE_KEY),
        )
        assert wrong_tenant.ok is False
        assert wrong_tenant.error.code is ErrorCode.CONTEXT_MISMATCH

        other_run_status = await service.get_external_dependency_status(
            ToolCallContext(
                tenant_id=other_tenant_id,
                run_id=other_run_id,
            ),
            GetExternalDependencyStatusRequest(
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            ),
        )
        assert other_run_status.ok is False
        assert other_run_status.error.code is ErrorCode.CONTEXT_MISMATCH

        same_tenant_other_run_status = await service.get_external_dependency_status(
            ToolCallContext(
                tenant_id=owner_tenant_id,
                run_id=same_tenant_other_run_id,
            ),
            GetExternalDependencyStatusRequest(
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            ),
        )
        assert same_tenant_other_run_status.ok is False
        assert (
            same_tenant_other_run_status.error.code
            is ErrorCode.CONTEXT_MISMATCH
        )
    finally:
        await engine.dispose()


def test_phase8c1_scenario3_start_persists_safe_context_and_generic_outbox(
    monkeypatch,
):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    tenant_id = f"TENANT-S3-START-{uuid4().hex[:10]}"

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["scenario3_phase8c1_provider_reads_wired"] is True

        state = _start_scenario3(client, tenant_id)
        run_id = state["run"]["run_id"]

        assert state["run"]["scenario_id"] == SCENARIO_ID
        assert state["run"]["status"] == "ACTIVE"
        assert len(state["incidents"]) == 1
        incident = state["incidents"][0]
        assert incident["incident_id"] == INCIDENT_ID
        assert incident["site_id"] == SITE_ID
        assert incident["reported_device_id"] == AFFECTED_DEVICE_ID
        assert incident["status"] == "OPEN"
        assert state["latest_event_seq"] == 3

        events_response = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=_headers(tenant_id),
        )
        assert events_response.status_code == 200
        events = events_response.json()["events"]
        assert [item["event_type"] for item in events] == [
            "simulation.started",
            "external.signal",
            "run.status_changed",
        ]
        signal = events[1]["payload"]
        assert signal["signal_type"] == "itsm.incident.created"
        details = signal["details"]
        assert details["service_key"] == SERVICE_KEY
        assert details["symptom_key"] == SYMPTOM_KEY
        assert details["incident_id"] == INCIDENT_ID
        assert details["site_id"] == SITE_ID
        assert details["reported_device_id"] == AFFECTED_DEVICE_ID

        serialized_signal = str(signal)
        for forbidden in (
            "AcmePay",
            ACMEPAY_DEPENDENCY_ID,
            "attachment_id",
            "switch_id",
            "port_id",
            "LOCAL_ACCESS_LINK_FAILURE",
            "ONSITE_FIELD_VISIT",
            "replan",
        ):
            assert forbidden not in serialized_signal

    outbox = asyncio.run(
        _load_outbox(tenant_id=tenant_id, run_id=run_id)
    )
    assert len(outbox) == 1
    assert outbox[0].topic == AGENT_DISPATCH_TOPIC
    assert outbox[0].delivered_at is None
    assert outbox[0].payload["signal"]["details"]["service_key"] == SERVICE_KEY
    assert outbox[0].payload["signal"]["details"]["symptom_key"] == SYMPTOM_KEY


def test_phase8c1_scenario1_worker_fails_closed_for_scenario3_envelope(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    tenant_id = f"TENANT-S3-DISPATCH-{uuid4().hex[:10]}"

    with TestClient(create_app()) as client:
        state = _start_scenario3(client, tenant_id)
        run_id = state["run"]["run_id"]

    processed, invocation_count, rows = asyncio.run(
        _dispatch_once_with_scenario1_worker(
            tenant_id=tenant_id,
            run_id=run_id,
        )
    )

    assert processed is True
    assert invocation_count == 0
    assert len(rows) == 1
    assert rows[0].topic == AGENT_DISPATCH_TOPIC
    assert rows[0].delivered_at is None
    assert rows[0].attempt_count >= 1


def test_phase8c1_provider_reads_are_grounded_and_persist_evidence(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    tenant_id = f"TENANT-S3-PROVIDER-{uuid4().hex[:10]}"

    with TestClient(create_app()) as client:
        state = _start_scenario3(client, tenant_id)
        run_id = state["run"]["run_id"]

    result = asyncio.run(
        _exercise_provider_reads(
            tenant_id=tenant_id,
            run_id=run_id,
        )
    )
    assert EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING in result["source_types"]
    assert EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS in result["source_types"]


def test_phase8c1_provider_context_is_tenant_and_run_isolated(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    owner_tenant_id = f"TENANT-S3-A-{uuid4().hex[:8]}"
    other_tenant_id = f"TENANT-S3-B-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        owner = _start_scenario3(client, owner_tenant_id)
        same_tenant_other = _start_scenario3(client, owner_tenant_id)
        other = _start_scenario3(client, other_tenant_id)

    asyncio.run(
        _assert_context_isolation(
            owner_tenant_id=owner_tenant_id,
            owner_run_id=owner["run"]["run_id"],
            other_tenant_id=other_tenant_id,
            other_run_id=other["run"]["run_id"],
            same_tenant_other_run_id=same_tenant_other["run"]["run_id"],
        )
    )


def test_phase8c1_scenario1_bootstrap_does_not_gain_service_fields(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    tenant_id = f"TENANT-S1-COMPAT-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        started = client.post(
            "/api/v1/scenario-1/runs",
            headers=_headers(tenant_id),
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]
        events = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=_headers(tenant_id),
        ).json()["events"]

    details = events[1]["payload"]["details"]
    assert "service_key" not in details
    assert "symptom_key" not in details
