from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from google.adk.events import Event

from agent_runtime.sessions import ADK_APP_NAME
from agent_runtime.sessions import create_database_session_service
from agent_runtime.sessions import ensure_run_session
from agent_runtime.sessions import get_run_session
from product_api.app import create_app
from product_backend.persistence.database import DatabaseSettings
from product_backend.persistence.database import create_engine
from product_backend.persistence.database import normalize_database_url
from product_backend.persistence.tables import Base


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    return normalize_database_url(value)


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def test_new_product_run_gets_stable_persistent_adk_session():
    tenant_id = f"TENANT-6A-{uuid4().hex[:10]}"

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["checkpoint"] == "6A"
        assert health.json()["adk_wired"] is False
        assert health.json()["adk_session_persistence_wired"] is True

        started = client.post(
            "/api/v1/scenario-1/runs",
            headers=_headers(tenant_id),
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]

    async def verify_after_app_restart() -> None:
        engine = create_engine(DatabaseSettings(url=_database_url()))
        service = create_database_session_service(engine)
        try:
            assert service.db_engine is engine
            await service.prepare_tables()
            session = await get_run_session(
                service,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            assert session.id == run_id
            assert session.app_name == ADK_APP_NAME
            assert session.user_id == tenant_id
            assert session.state == {}
            assert session.events == []
        finally:
            await engine.dispose()

    asyncio.run(verify_after_app_restart())


def test_adk_runtime_event_and_state_survive_new_engine_instance():
    async def scenario() -> None:
        tenant_id = f"TENANT-6A-RUNTIME-{uuid4().hex[:8]}"
        run_id = f"RUN-6A-RUNTIME-{uuid4().hex[:12]}"

        first_engine = create_engine(DatabaseSettings(url=_database_url()))
        first = create_database_session_service(first_engine)
        try:
            await first.prepare_tables()
            session = await ensure_run_session(
                first,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            await first.append_event(
                session,
                Event(
                    invocation_id=f"INV-6A-{uuid4().hex[:12]}",
                    author="phase6a-test",
                    state={"runtime_checkpoint": "persisted-by-adk"},
                ),
            )
        finally:
            await first_engine.dispose()

        second_engine = create_engine(DatabaseSettings(url=_database_url()))
        second = create_database_session_service(second_engine)
        try:
            await second.prepare_tables()
            recovered = await get_run_session(
                second,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert recovered is not None
            assert recovered.id == run_id
            assert recovered.state == {
                "runtime_checkpoint": "persisted-by-adk"
            }
            assert len(recovered.events) == 1
            assert recovered.events[0].author == "phase6a-test"
            assert (
                recovered.events[0].actions.state_delta["runtime_checkpoint"]
                == "persisted-by-adk"
            )
        finally:
            await second_engine.dispose()

    asyncio.run(scenario())


def test_product_metadata_does_not_claim_adk_runtime_tables():
    adk_owned_tables = {
        "adk_internal_metadata",
        "sessions",
        "events",
        "app_states",
        "user_states",
    }
    assert adk_owned_tables.isdisjoint(Base.metadata.tables)
