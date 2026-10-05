"""Live Phase 7A automatic dispatch acceptance.

This intentionally never calls /agent/invoke. The only user-facing trigger is
POST /api/v1/scenario-1/runs (Start simulation semantics). The Product backend
must persist the operational signal, durably dispatch it to the same ADK
Session, and reach an evidence-backed human-approval pause by itself.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from product_api.app import create_app
from product_backend.contracts.events import AGENT_DISPATCH_TOPIC
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
)
from product_backend.persistence.tables import ApplicationOutboxRow


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for Phase 7A live acceptance")
    return value


async def _dispatch_row(tenant_id: str, run_id: str) -> ApplicationOutboxRow:
    engine = create_engine(DatabaseSettings.from_env())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            result = await session.execute(
                select(ApplicationOutboxRow).where(
                    ApplicationOutboxRow.tenant_id == tenant_id,
                    ApplicationOutboxRow.run_id == run_id,
                    ApplicationOutboxRow.topic == AGENT_DISPATCH_TOPIC,
                )
            )
            return result.scalar_one()
    finally:
        await engine.dispose()


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def run_acceptance(*, timeout_seconds: float) -> None:
    _require_env("DATABASE_URL")
    _require_env("GOOGLE_API_KEY")
    tenant_id = f"TENANT-7A-LIVE-{uuid4().hex[:10]}"

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200, health.text
        health_body = health.json()
        assert health_body["checkpoint"] == "7A"
        assert health_body["gemini_configured"] is True
        assert health_body["adk_wired"] is True
        assert health_body["adk_session_persistence_wired"] is True
        assert health_body["adk_resumability_wired"] is True
        assert health_body["automatic_dispatch_wired"] is True

        # This is the entire demo trigger. Do NOT call /agent/invoke here.
        started = client.post(
            "/api/v1/scenario-1/runs",
            headers=_headers(tenant_id),
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]

        deadline = time.monotonic() + timeout_seconds
        state = started.json()
        while time.monotonic() < deadline:
            response = client.get(
                f"/api/v1/runs/{run_id}",
                headers=_headers(tenant_id),
            )
            assert response.status_code == 200, response.text
            state = response.json()
            if (
                state["run"]["status"] == "WAITING_APPROVAL"
                and state["proposals"]
                and state["proposals"][-1]["status"] == "PENDING_APPROVAL"
            ):
                break
            time.sleep(0.5)
        else:
            raise AssertionError(
                "automatic dispatch did not reach WAITING_APPROVAL before timeout"
            )

        proposal = state["proposals"][-1]
        proposal_id = proposal["proposal_id"]
        assert len(state["evidence"]) >= 4
        assert state["approvals"] == []
        assert state["executed_actions"] == []
        assert state["work_orders"] == []

        timeline = client.get(
            f"/api/v1/runs/{run_id}/events",
            headers=_headers(tenant_id),
            params={"after_seq": 0, "limit": 1000},
        )
        assert timeline.status_code == 200, timeline.text
        event_types = [item["event_type"] for item in timeline.json()["events"]]
        assert "external.signal" in event_types
        assert event_types.count("observation.recorded") >= 4
        assert "proposal.created" in event_types
        assert "run.status_changed" in event_types
        assert "tool.started" not in event_types
        assert "tool.finished" not in event_types

        outbox = asyncio.run(_dispatch_row(tenant_id, run_id))
        assert outbox.delivered_at is not None
        assert outbox.attempt_count >= 1

        approved = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "phase7a-live-operator"},
        )
        assert approved.status_code == 200, approved.text
        approved_body = approved.json()
        assert approved_body["proposal"]["status"] == "EXECUTED"
        assert approved_body["incident"]["status"] == "ESCALATED"
        assert approved_body["executed_action"] is not None
        assert approved_body["work_order"] is not None
        assert approved_body["agent_resume"] is not None
        assert approved_body["agent_resume"]["status"] in {
            "resumed",
            "already_resumed",
        }

        replay = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "phase7a-live-operator"},
        )
        assert replay.status_code == 200, replay.text
        replay_body = replay.json()
        assert replay_body["replayed"] is True
        assert (
            replay_body["executed_action"]["action_id"]
            == approved_body["executed_action"]["action_id"]
        )
        assert (
            replay_body["work_order"]["work_order_id"]
            == approved_body["work_order"]["work_order_id"]
        )

        final_state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        assert final_state.status_code == 200
        final_body = final_state.json()
        assert len(final_body["approvals"]) == 1
        assert len(final_body["executed_actions"]) == 1
        assert len(final_body["work_orders"]) == 1

        print(
            "PHASE7A_LIVE_PASS",
            {
                "run_id": run_id,
                "proposal_id": proposal_id,
                "event_count": len(timeline.json()["events"]),
                "evidence_count": len(state["evidence"]),
                "dispatch_attempts": outbox.attempt_count,
                "automatic_dispatch": True,
                "manual_agent_invoke_used": False,
                "work_order_id": approved_body["work_order"]["work_order_id"],
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive")
    run_acceptance(timeout_seconds=args.timeout_seconds)


if __name__ == "__main__":
    main()
