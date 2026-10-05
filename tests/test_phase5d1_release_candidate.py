from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from product_api.app import create_app
from scripts.phase4d_seed_proposal import seed


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 5D1 integration tests")
    return value


def _tenant() -> str:
    return f"TENANT-D1-{uuid4().hex[:8]}"


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def _start(client: TestClient, tenant_id: str) -> dict:
    response = client.post(
        "/api/v1/scenario-1/runs",
        headers=_headers(tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed(tenant_id: str, run_id: str) -> dict:
    _database_url()
    result = asyncio.run(seed(tenant_id=tenant_id, run_id=run_id))
    assert result["tenant_id"] == tenant_id
    assert result["run_id"] == run_id
    assert result["proposal_status"] == "PENDING_APPROVAL"
    assert result["evidence_count"] == 4
    return result


def test_controlled_seed_is_not_exposed_as_public_http_endpoint():
    with TestClient(create_app()) as client:
        paths = client.app.openapi()["paths"]
        internal_paths = {route.path for route in client.app.routes}

    lowered = "\n".join(paths).lower()
    assert "seed" not in lowered
    assert "test-proposal" not in lowered
    assert "fixture-proposal" not in lowered
    assert set(paths) == {
        "/health",
        "/api/v1/scenario-1/runs",
        "/api/v1/scenario-2/runs",
        "/api/v1/scenario-2/runs/{run_id}",
        "/api/v1/scenario-2/runs/{run_id}/signals",
        "/api/v1/scenario-2/runs/{run_id}/simulator/next",
        "/api/v1/runs/{run_id}",
        "/api/v1/runs/{run_id}/events",
        "/api/v1/runs/{run_id}/events/stream",
        "/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
        "/api/v1/runs/{run_id}/proposals/{proposal_id}/reject",
    }
    assert "/api/v1/runs/{run_id}/agent/invoke" not in paths
    assert "/api/v1/runs/{run_id}/agent/invoke" in internal_paths
    assert (
        "/api/v1/scenario-2/runs/{run_id}/acceptance/dependency-status"
        not in paths
    )
    assert (
        "/api/v1/scenario-2/runs/{run_id}/acceptance/dependency-status"
        in internal_paths
    )
    assert (
        "/api/v1/scenario-2/runs/{run_id}/acceptance/matching-major-incident"
        not in paths
    )
    assert (
        "/api/v1/scenario-2/runs/{run_id}/acceptance/matching-major-incident"
        in internal_paths
    )


def test_controlled_seed_creates_real_persisted_pending_proposal_and_events():
    tenant_id = _tenant()

    with TestClient(create_app()) as client:
        started = _start(client, tenant_id)
        run_id = started["run"]["run_id"]
        initial_seq = started["latest_event_seq"]

        seeded = _seed(tenant_id, run_id)

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        assert state.status_code == 200, state.text
        snapshot = state.json()

        assert snapshot["run"]["status"] == "WAITING_APPROVAL"
        assert len(snapshot["evidence"]) == 4
        assert len(snapshot["proposals"]) == 1
        proposal = snapshot["proposals"][0]
        assert proposal["proposal_id"] == seeded["proposal_id"]
        assert proposal["status"] == "PENDING_APPROVAL"
        assert proposal["diagnosis"] == "LOCAL_ACCESS_LINK_FAILURE"
        assert proposal["action_type"] == "ONSITE_FIELD_VISIT"
        assert len(proposal["evidence_ids"]) == 4
        assert snapshot["approvals"] == []
        assert snapshot["executed_actions"] == []
        assert snapshot["work_orders"] == []

        timeline = client.get(
            f"/api/v1/runs/{run_id}/events",
            params={"after_seq": initial_seq, "limit": 100},
            headers=_headers(tenant_id),
        )
        assert timeline.status_code == 200, timeline.text
        event_types = [
            event["event_type"]
            for event in timeline.json()["events"]
        ]
        assert event_types == [
            "proposal.created",
            "run.status_changed",
        ]


def test_seeded_proposal_approve_replay_is_exactly_once():
    tenant_id = _tenant()

    with TestClient(create_app()) as client:
        run_id = _start(client, tenant_id)["run"]["run_id"]
        proposal_id = _seed(tenant_id, run_id)["proposal_id"]

        first = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "phase5d1-verifier"},
        )
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert first_body["replayed"] is False
        assert first_body["proposal"]["status"] == "EXECUTED"
        assert first_body["incident"]["status"] == "ESCALATED"
        assert first_body["executed_action"] is not None
        assert first_body["work_order"] is not None

        replay = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "phase5d1-verifier"},
        )
        assert replay.status_code == 200, replay.text
        replay_body = replay.json()
        assert replay_body["replayed"] is True
        assert (
            replay_body["executed_action"]["action_id"]
            == first_body["executed_action"]["action_id"]
        )
        assert (
            replay_body["work_order"]["work_order_id"]
            == first_body["work_order"]["work_order_id"]
        )

        snapshot = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        ).json()
        assert snapshot["run"]["status"] == "ACTIVE"
        assert snapshot["incidents"][0]["status"] == "ESCALATED"
        assert len(snapshot["approvals"]) == 1
        assert len(snapshot["executed_actions"]) == 1
        assert len(snapshot["work_orders"]) == 1


def test_seeded_proposal_reject_is_zero_execution():
    tenant_id = _tenant()

    with TestClient(create_app()) as client:
        run_id = _start(client, tenant_id)["run"]["run_id"]
        proposal_id = _seed(tenant_id, run_id)["proposal_id"]

        rejected = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/reject",
            headers=_headers(tenant_id),
            json={"decided_by": "phase5d1-verifier"},
        )
        assert rejected.status_code == 200, rejected.text
        body = rejected.json()
        assert body["proposal"]["status"] == "REJECTED"
        assert body["incident"]["status"] == "OPEN"
        assert body["executed_action"] is None
        assert body["work_order"] is None

        snapshot = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        ).json()
        assert snapshot["run"]["status"] == "ACTIVE"
        assert snapshot["incidents"][0]["status"] == "OPEN"
        assert len(snapshot["approvals"]) == 1
        assert snapshot["executed_actions"] == []
        assert snapshot["work_orders"] == []
