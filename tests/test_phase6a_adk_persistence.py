from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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


def _run_process_probe(mode: str, tenant_id: str, run_id: str) -> dict:
    _database_url()
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.phase6a_adk_persistence_probe",
            mode,
            tenant_id,
            run_id,
        ],
        cwd=root,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert lines, completed.stderr
    return json.loads(lines[-1])


def test_new_product_run_gets_stable_persistent_adk_session():
    tenant_id = f"TENANT-6A-{uuid4().hex[:10]}"

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["checkpoint"] == "6A"
        assert health.json()["adk_wired"] is False
        assert health.json()["adk_session_persistence_wired"] is True

        container = client.app.state.product_container
        assert container.adk_session_service is not None
        assert container.adk_session_service.db_engine is container.engine

        started = client.post(
            "/api/v1/scenario-1/runs",
            headers=_headers(tenant_id),
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]

    recovered = _run_process_probe("inspect", tenant_id, run_id)
    assert recovered["found"] is True
    assert recovered["session_id"] == run_id
    assert recovered["app_name"] == ADK_APP_NAME
    assert recovered["user_id"] == tenant_id
    assert recovered["state"] == {}
    assert recovered["events"] == []


def test_adk_runtime_event_and_state_survive_real_process_restart():
    tenant_id = f"TENANT-6A-RUNTIME-{uuid4().hex[:8]}"
    run_id = f"RUN-6A-RUNTIME-{uuid4().hex[:12]}"

    written = _run_process_probe("append", tenant_id, run_id)
    assert written["found"] is True
    assert written["session_id"] == run_id

    recovered = _run_process_probe("inspect", tenant_id, run_id)
    assert recovered["found"] is True
    assert recovered["session_id"] == run_id
    assert recovered["state"] == {
        "runtime_checkpoint": "persisted-across-process"
    }
    assert len(recovered["events"]) == 1
    assert recovered["events"][0]["author"] == "phase6a-process-probe"
    assert recovered["events"][0]["state_delta"] == {
        "runtime_checkpoint": "persisted-across-process"
    }


def test_ensure_run_session_is_idempotent_for_repeated_callers():
    async def scenario() -> None:
        tenant_id = f"TENANT-6A-ENSURE-{uuid4().hex[:8]}"
        run_id = f"RUN-6A-ENSURE-{uuid4().hex[:12]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        service = create_database_session_service(engine)
        try:
            await service.prepare_tables()
            first, second = await asyncio.gather(
                ensure_run_session(
                    service,
                    tenant_id=tenant_id,
                    run_id=run_id,
                ),
                ensure_run_session(
                    service,
                    tenant_id=tenant_id,
                    run_id=run_id,
                ),
            )
            assert first.id == run_id
            assert second.id == run_id

            sessions = await service.list_sessions(
                app_name=ADK_APP_NAME,
                user_id=tenant_id,
            )
            matching = [
                session
                for session in sessions.sessions
                if session.id == run_id
            ]
            assert len(matching) == 1
        finally:
            await engine.dispose()

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
