from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from product_api.app import ProductApiContainer, create_app
from product_api.scenario1_fixture import (
    AFFECTED_DEVICE_ID,
    ATTACHMENT_ID,
    INCIDENT_ID,
    SITE_ID,
    Scenario1FixtureSources,
)
from product_backend.application.field_visit import FieldVisitProposalService
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.contracts.tools import ProposeFieldVisitRequest, ToolCallContext
from product_backend.domain.enums import (
    ActionType,
    DiagnosisCode,
    DiagnosticType,
    EvidenceSourceType,
)
from product_backend.domain.models import Evidence, KbArticle
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.run_state import SqlAlchemyRunStateQuery
from product_backend.persistence.tables import (
    ApprovalRow,
    ExecutedActionRow,
    FieldServiceWorkOrderRow,
)
from product_backend.persistence.uow import (
    SqlAlchemyLifecycleUnitOfWork,
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    return normalize_database_url(value)


def _headers(tenant_id: str = "TENANT-8OCT") -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def _new_db():
    engine = create_engine(DatabaseSettings(url=_database_url()))
    return engine, create_session_factory(engine)


def _start(client: TestClient, tenant_id: str = "TENANT-8OCT") -> dict:
    response = client.post(
        "/api/v1/scenario-1/runs",
        headers=_headers(tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _seed_pending_proposal(
    *,
    tenant_id: str,
    run_id: str,
) -> str:
    engine, factory = _new_db()
    fixture = Scenario1FixtureSources()
    now = datetime.now(UTC)
    try:
        topology = await fixture.get_device(
            tenant_id=tenant_id,
            run_id=run_id,
            device_id=AFFECTED_DEVICE_ID,
        )
        health = await fixture.get_site_health(
            tenant_id=tenant_id,
            run_id=run_id,
            site_id=SITE_ID,
        )
        diagnostic = await fixture.run_diagnostic(
            tenant_id=tenant_id,
            run_id=run_id,
            diagnostic_type=DiagnosticType.ACCESS_LINK,
            target_id=ATTACHMENT_ID,
        )
        assert topology is not None
        assert health is not None
        assert diagnostic is not None

        kb = KbArticle(
            article_id="KB-S1-FIELD-VISIT",
            title="Approved local physical-path inspection",
            approved=True,
            diagnosis_codes=(DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,),
            allowed_actions=(ActionType.ONSITE_FIELD_VISIT,),
        )

        evidence = (
            Evidence(
                evidence_id=f"E-CMDB-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.CMDB_SNAPSHOT,
                captured_at=now,
                entity_ids=(
                    topology.device_id,
                    topology.site_id,
                    topology.attachment_id,
                    topology.expected_switch_id,
                    topology.expected_port_id,
                ),
                payload=topology,
            ),
            Evidence(
                evidence_id=f"E-SITE-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.SITE_HEALTH,
                captured_at=now,
                entity_ids=(
                    health.site_id,
                    health.peer_device_id,
                    health.affected_device_id,
                ),
                payload=health,
                expires_at=now + timedelta(minutes=30),
            ),
            Evidence(
                evidence_id=f"E-DIAG-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
                captured_at=now,
                entity_ids=(
                    diagnostic.attachment_id,
                    diagnostic.switch_id,
                    diagnostic.port_id,
                ),
                payload=diagnostic,
                expires_at=now + timedelta(minutes=30),
            ),
            Evidence(
                evidence_id=f"E-KB-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.KB_ARTICLE,
                captured_at=now,
                entity_ids=(kb.article_id,),
                payload=kb,
            ),
        )

        async with SqlAlchemyToolReadUnitOfWork(factory) as uow:
            for item in evidence:
                await uow.evidence.add(item)
            await uow.commit()

        service = FieldVisitProposalService(
            lambda: SqlAlchemyProposalCreationUnitOfWork(factory),
            clock=lambda: datetime.now(UTC),
            id_factory=lambda prefix: f"{prefix.upper()}-{uuid4().hex}",
        )
        result = await service.create(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            ProposeFieldVisitRequest(
                incident_id=INCIDENT_ID,
                device_id=AFFECTED_DEVICE_ID,
                diagnosis=DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
                evidence_ids=tuple(item.evidence_id for item in evidence),
                rationale="Evidence supports an onsite physical-path inspection.",
            ),
        )
        assert result.ok is True
        return result.proposal.proposal_id
    finally:
        await engine.dispose()


async def _execution_counts(
    *,
    tenant_id: str,
    run_id: str,
) -> tuple[int, int, int]:
    engine, factory = _new_db()
    try:
        async with factory() as session:
            approvals = await session.scalar(
                select(func.count())
                .select_from(ApprovalRow)
                .where(
                    ApprovalRow.tenant_id == tenant_id,
                    ApprovalRow.run_id == run_id,
                )
            )
            actions = await session.scalar(
                select(func.count())
                .select_from(ExecutedActionRow)
                .where(
                    ExecutedActionRow.tenant_id == tenant_id,
                    ExecutedActionRow.run_id == run_id,
                )
            )
            work_orders = await session.scalar(
                select(func.count())
                .select_from(FieldServiceWorkOrderRow)
                .where(
                    FieldServiceWorkOrderRow.tenant_id == tenant_id,
                    FieldServiceWorkOrderRow.run_id == run_id,
                )
            )
        return (
            int(approvals or 0),
            int(actions or 0),
            int(work_orders or 0),
        )
    finally:
        await engine.dispose()


def test_start_is_persistent_and_does_not_require_gemini(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["database_reachable"] is True
        assert health.json()["adk_wired"] is True
        assert health.json()["gemini_configured"] is False
        assert health.json()["sse_wired"] is True

        state = _start(client)
        run_id = state["run"]["run_id"]

        assert state["run"]["tenant_id"] == "TENANT-8OCT"
        assert state["run"]["scenario_id"] == "scenario-1"
        assert state["run"]["status"] == "ACTIVE"
        assert state["latest_event_seq"] == 3
        assert len(state["incidents"]) == 1
        assert state["incidents"][0]["incident_id"] == INCIDENT_ID
        assert state["incidents"][0]["site_id"] == SITE_ID
        assert state["incidents"][0]["reported_device_id"] == AFFECTED_DEVICE_ID
        assert state["incidents"][0]["status"] == "OPEN"
        assert state["evidence"] == []
        assert state["proposals"] == []

        events = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=_headers(),
        )
        assert events.status_code == 200
        body = events.json()
        assert [item["seq"] for item in body["events"]] == [1, 2, 3]
        assert [item["event_type"] for item in body["events"]] == [
            "simulation.started",
            "external.signal",
            "run.status_changed",
        ]
        assert body["events"][0]["payload"] == {
            "scenario_id": "scenario-1",
            "status": "CREATED",
        }
        assert body["events"][1]["payload"]["details"]["incident_id"] == INCIDENT_ID
        assert body["events"][2]["payload"] == {
            "previous_status": "CREATED",
            "status": "ACTIVE",
            "cause": "simulation_started",
        }
        assert body["next_cursor"] == 3


def test_run_survives_new_app_and_database_engine():
    tenant_id = f"TENANT-RESTART-{uuid4().hex[:8]}"

    with TestClient(create_app()) as first:
        state = _start(first, tenant_id)
        run_id = state["run"]["run_id"]

    with TestClient(create_app()) as restarted:
        response = restarted.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["run"]["run_id"] == run_id
        assert body["run"]["status"] == "ACTIVE"
        assert body["latest_event_seq"] == 3


def test_tenant_isolation_validation_and_timeline_cursor():
    tenant_id = f"TENANT-A-{uuid4().hex[:8]}"
    other_tenant = f"TENANT-B-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        state = _start(client, tenant_id)
        run_id = state["run"]["run_id"]

        wrong_tenant = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(other_tenant),
        )
        assert wrong_tenant.status_code == 404
        assert wrong_tenant.json()["error"]["code"] == "RUN_NOT_FOUND"

        wrong_events = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=_headers(other_tenant),
        )
        assert wrong_events.status_code == 404
        assert wrong_events.json()["error"]["code"] == "RUN_NOT_FOUND"

        missing_header = client.get(f"/api/v1/runs/{run_id}")
        assert missing_header.status_code == 422
        assert missing_header.json() == {
            "error": {
                "code": "INVALID_ARGUMENT",
                "message": "Request validation failed.",
                "retryable": False,
                "details": {},
            }
        }

        invalid_tenant = client.get(
            f"/api/v1/runs/{run_id}",
            headers={"X-Tenant-ID": "bad tenant"},
        )
        assert invalid_tenant.status_code == 400
        assert invalid_tenant.json()["error"]["code"] == "INVALID_TENANT_CONTEXT"

        page = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=_headers(tenant_id),
            params={"after_seq": 1, "limit": 1},
        )
        assert page.status_code == 200
        assert [item["seq"] for item in page.json()["events"]] == [2]
        assert page.json()["next_cursor"] == 2

        empty = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=_headers(tenant_id),
            params={"after_seq": 3},
        )
        assert empty.status_code == 200
        assert empty.json()["events"] == []
        assert empty.json()["next_cursor"] == 3


def test_current_state_snapshot_blocks_concurrent_run_mutation_until_complete():
    tenant_id = f"TENANT-SNAPSHOT-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        state = _start(client, tenant_id)
        run_id = state["run"]["run_id"]

    async def scenario() -> None:
        engine, factory = _new_db()
        first_query_completed = asyncio.Event()
        release_reader = asyncio.Event()

        class PausingSession:
            def __init__(self):
                self._session = factory()
                self._execute_count = 0

            async def __aenter__(self):
                await self._session.__aenter__()
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return await self._session.__aexit__(exc_type, exc, tb)

            async def execute(self, statement):
                result = await self._session.execute(statement)
                self._execute_count += 1
                if self._execute_count == 1:
                    first_query_completed.set()
                    await release_reader.wait()
                return result

            async def scalar(self, statement):
                return await self._session.scalar(statement)

        def pausing_factory():
            return PausingSession()

        try:
            query = SqlAlchemyRunStateQuery(pausing_factory)
            lifecycle = ApplicationLifecycleService(
                lambda: SqlAlchemyLifecycleUnitOfWork(factory)
            )
            context = ToolCallContext(tenant_id=tenant_id, run_id=run_id)

            reader = asyncio.create_task(
                query.get(tenant_id=tenant_id, run_id=run_id)
            )
            await asyncio.wait_for(first_query_completed.wait(), timeout=2)

            writer = asyncio.create_task(
                lifecycle.record_external_signal(
                    context,
                    signal_type="test.concurrent",
                    details={"source": "phase4c-lock-test"},
                )
            )
            await asyncio.sleep(0.1)
            assert writer.done() is False

            release_reader.set()
            snapshot = await asyncio.wait_for(reader, timeout=2)
            assert snapshot is not None
            assert snapshot.latest_event_seq == 3

            event = await asyncio.wait_for(writer, timeout=2)
            assert event.seq == 4
        finally:
            release_reader.set()
            await engine.dispose()

    asyncio.run(scenario())


def test_approve_replay_conflict_and_cross_tenant_are_safe_and_idempotent():
    tenant_id = f"TENANT-APPROVE-{uuid4().hex[:8]}"
    other_tenant = f"TENANT-OTHER-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        state = _start(client, tenant_id)
        run_id = state["run"]["run_id"]
        proposal_id = asyncio.run(
            _seed_pending_proposal(
                tenant_id=tenant_id,
                run_id=run_id,
            )
        )

        wrong_tenant = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(other_tenant),
            json={"decided_by": "human-operator"},
        )
        assert wrong_tenant.status_code == 404
        assert wrong_tenant.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"

        second_state = _start(client, tenant_id)
        other_run_id = second_state["run"]["run_id"]
        wrong_run = client.post(
            f"/api/v1/runs/{other_run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert wrong_run.status_code == 404
        assert wrong_run.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"
        assert asyncio.run(
            _execution_counts(tenant_id=tenant_id, run_id=run_id)
        ) == (0, 0, 0)

        approved = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert approved.status_code == 200, approved.text
        first = approved.json()
        assert first["replayed"] is False
        assert first["approval"]["decision"] == "APPROVED"
        assert first["proposal"]["status"] == "EXECUTED"
        assert first["incident"]["status"] == "ESCALATED"
        assert first["executed_action"] is not None
        assert first["work_order"] is not None

        replayed = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert replayed.status_code == 200
        replay = replayed.json()
        assert replay["replayed"] is True
        assert replay["approval"]["approval_id"] == first["approval"]["approval_id"]
        assert replay["executed_action"]["action_id"] == first["executed_action"]["action_id"]
        assert replay["work_order"]["work_order_id"] == first["work_order"]["work_order_id"]

        conflict = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/reject",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "PROPOSAL_NOT_PENDING"

        assert asyncio.run(
            _execution_counts(tenant_id=tenant_id, run_id=run_id)
        ) == (1, 1, 1)

        persisted = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        assert persisted.status_code == 200
        body = persisted.json()
        assert body["run"]["status"] == "ACTIVE"
        assert body["incidents"][0]["status"] == "ESCALATED"
        assert len(body["approvals"]) == 1
        assert len(body["executed_actions"]) == 1
        assert len(body["work_orders"]) == 1


def test_approved_state_survives_new_app_and_engine():
    tenant_id = f"TENANT-APP-RESTART-{uuid4().hex[:8]}"

    with TestClient(create_app()) as first:
        state = _start(first, tenant_id)
        run_id = state["run"]["run_id"]
        proposal_id = asyncio.run(
            _seed_pending_proposal(
                tenant_id=tenant_id,
                run_id=run_id,
            )
        )
        approved = first.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert approved.status_code == 200, approved.text
        first_body = approved.json()

    with TestClient(create_app()) as restarted:
        response = restarted.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["run"]["status"] == "ACTIVE"
        assert body["incidents"][0]["status"] == "ESCALATED"
        assert len(body["evidence"]) == 4
        assert len(body["proposals"]) == 1
        assert len(body["approvals"]) == 1
        assert len(body["executed_actions"]) == 1
        assert len(body["work_orders"]) == 1
        assert body["proposals"][0]["proposal_id"] == proposal_id
        assert (
            body["approvals"][0]["approval_id"]
            == first_body["approval"]["approval_id"]
        )
        assert (
            body["executed_actions"][0]["action_id"]
            == first_body["executed_action"]["action_id"]
        )
        assert (
            body["work_orders"][0]["work_order_id"]
            == first_body["work_order"]["work_order_id"]
        )


def test_reject_keeps_incident_open_and_creates_no_execution():
    tenant_id = f"TENANT-REJECT-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        state = _start(client, tenant_id)
        run_id = state["run"]["run_id"]
        proposal_id = asyncio.run(
            _seed_pending_proposal(
                tenant_id=tenant_id,
                run_id=run_id,
            )
        )

        rejected = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/reject",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert rejected.status_code == 200, rejected.text
        body = rejected.json()
        assert body["replayed"] is False
        assert body["approval"]["decision"] == "REJECTED"
        assert body["proposal"]["status"] == "REJECTED"
        assert body["incident"]["status"] == "OPEN"
        assert body["executed_action"] is None
        assert body["work_order"] is None

        replayed = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/reject",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert replayed.status_code == 200
        assert replayed.json()["replayed"] is True

        assert asyncio.run(
            _execution_counts(tenant_id=tenant_id, run_id=run_id)
        ) == (1, 0, 0)


class _DatabaseFailureStateService:
    async def get(self, *, tenant_id: str, run_id: str):
        raise SQLAlchemyError(
            "postgresql://demo:SUPER_SECRET_PASSWORD@private-db/internal"
        )


class _UnexpectedStartService:
    async def start(self, *, tenant_id: str, bootstrap):
        raise RuntimeError("GOOGLE_API_KEY=VERY_SECRET_INTERNAL_VALUE")


def _fake_container(
    *,
    start_service: object | None = None,
    state_service: object | None = None,
) -> ProductApiContainer:
    return ProductApiContainer(
        start_service=start_service or object(),
        state_service=state_service or object(),
        lifecycle_service=object(),
        approval_service=object(),
        fixture=Scenario1FixtureSources(),
        engine=None,
    )


def test_database_exception_is_safe_typed_503_without_secret_leak():
    app = create_app(
        _fake_container(state_service=_DatabaseFailureStateService())
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            "/api/v1/runs/RUN-DB-FAIL",
            headers=_headers(),
        )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "DATABASE_UNAVAILABLE",
            "message": "Persistent product state is temporarily unavailable.",
            "retryable": True,
            "details": {},
        }
    }
    assert "SUPER_SECRET_PASSWORD" not in response.text
    assert "private-db" not in response.text


def test_unexpected_start_exception_is_safe_typed_500_without_secret_leak():
    app = create_app(
        _fake_container(start_service=_UnexpectedStartService())
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/scenario-1/runs",
            headers=_headers(),
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "Unexpected server error.",
            "retryable": True,
            "details": {},
        }
    }
    assert "VERY_SECRET_INTERNAL_VALUE" not in response.text
    assert "GOOGLE_API_KEY" not in response.text


def test_request_validation_is_generic_and_does_not_echo_input():
    secret_actor = "operator\nSHOULD_NOT_ECHO_SECRET"

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/runs/RUN-UNKNOWN/proposals/PROPOSAL-UNKNOWN/approve",
            headers=_headers(),
            json={"decided_by": secret_actor},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ARGUMENT"
    assert "SHOULD_NOT_ECHO_SECRET" not in response.text
