from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from agent_runtime.service import AgentResumeResult
from product_api.app import create_app
from product_api.scenario1_fixture import ATTACHMENT_ID
from product_backend.domain.enums import DiagnosticType, OperationalState
from scripts.phase4d_seed_proposal import seed as seed_pending_proposal


ACCEPTANCE_TOKEN = "phase6d-test-token"


class _RecordingRuntime:
    model = "phase6d-recording"
    gemini_configured = True
    resumability_wired = True

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def resume_human_decision(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
        decision_payload: dict[str, Any],
    ) -> AgentResumeResult:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "proposal_id": proposal_id,
                "decision_payload": decision_payload,
            }
        )
        return AgentResumeResult(
            invocation_id="INV-PHASE6D-STALE",
            function_call_id="CALL-PHASE6D-STALE",
            final_answer=(
                "The proposal became stale after revalidation; "
                "no field visit was executed."
            ),
            already_resumed=False,
        )

    async def close(self) -> None:
        return None


def _headers(
    tenant_id: str,
    *,
    token: str | None = None,
) -> dict[str, str]:
    headers = {"X-Tenant-ID": tenant_id}
    if token is not None:
        headers["X-Acceptance-Token"] = token
    return headers


def _start(client: TestClient, tenant_id: str) -> str:
    response = client.post(
        "/api/v1/scenario-1/runs",
        headers=_headers(tenant_id),
    )
    assert response.status_code == 201, response.text
    return response.json()["run"]["run_id"]


def _start_and_seed(client: TestClient, tenant_id: str) -> tuple[str, str]:
    run_id = _start(client, tenant_id)
    seeded = asyncio.run(
        seed_pending_proposal(
            tenant_id=tenant_id,
            run_id=run_id,
        )
    )
    return run_id, str(seeded["proposal_id"])


def _hook_url(run_id: str) -> str:
    return f"/__acceptance/phase6d/runs/{run_id}/access-link-state"


def test_phase6d_acceptance_hook_is_hidden_and_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PHASE6D_ACCEPTANCE_HOOKS", raising=False)
    monkeypatch.delenv("PHASE6D_ACCEPTANCE_TOKEN", raising=False)
    tenant_id = f"TENANT-6D-DISABLED-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id = _start(client, tenant_id)
        response = client.post(
            _hook_url(run_id),
            headers=_headers(tenant_id, token=ACCEPTANCE_TOKEN),
            json={"operational_state": "UP"},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        assert _hook_url("{run_id}") not in openapi.json()["paths"]


def test_phase6d_acceptance_hook_rejects_wrong_token_without_mutation(
    monkeypatch,
):
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_HOOKS", "1")
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_TOKEN", ACCEPTANCE_TOKEN)
    tenant_id = f"TENANT-6D-TOKEN-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id, _ = _start_and_seed(client, tenant_id)
        container = client.app.state.product_container

        before = asyncio.run(
            container.fixture.run_diagnostic(
                tenant_id=tenant_id,
                run_id=run_id,
                diagnostic_type=DiagnosticType.ACCESS_LINK,
                target_id=ATTACHMENT_ID,
            )
        )
        assert before is not None
        assert before.operational_state is OperationalState.DOWN

        response = client.post(
            _hook_url(run_id),
            headers=_headers(tenant_id, token="wrong-token"),
            json={"operational_state": "UP"},
        )
        assert response.status_code == 404

        after = asyncio.run(
            container.fixture.run_diagnostic(
                tenant_id=tenant_id,
                run_id=run_id,
                diagnostic_type=DiagnosticType.ACCESS_LINK,
                target_id=ATTACHMENT_ID,
            )
        )
        assert after is not None
        assert after.operational_state is OperationalState.DOWN


def test_phase6d_hook_requires_waiting_approval_pending_proposal(monkeypatch):
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_HOOKS", "1")
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_TOKEN", ACCEPTANCE_TOKEN)
    tenant_id = f"TENANT-6D-PRECOND-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id = _start(client, tenant_id)
        response = client.post(
            _hook_url(run_id),
            headers=_headers(tenant_id, token=ACCEPTANCE_TOKEN),
            json={"operational_state": "UP"},
        )
        assert response.status_code == 409
        assert (
            response.json()["error"]["code"]
            == "ACCEPTANCE_PRECONDITION_FAILED"
        )


def test_phase6d_hook_drives_real_product_approve_into_stale_without_execution(
    monkeypatch,
):
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_HOOKS", "true")
    monkeypatch.setenv("PHASE6D_ACCEPTANCE_TOKEN", ACCEPTANCE_TOKEN)
    tenant_id = f"TENANT-6D-STALE-{uuid4().hex[:8]}"
    other_tenant_id = f"TENANT-6D-OTHER-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id, proposal_id = _start_and_seed(client, tenant_id)
        other_run_id = _start(client, other_tenant_id)
        container = client.app.state.product_container

        original_runtime = container.agent_runtime
        if original_runtime is not None:
            asyncio.run(original_runtime.close())
        runtime = _RecordingRuntime()
        container.agent_runtime = runtime

        changed = client.post(
            _hook_url(run_id),
            headers=_headers(tenant_id, token=ACCEPTANCE_TOKEN),
            json={"operational_state": "UP"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json() == {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "operational_state": "UP",
            "scope": "phase6d_acceptance_only",
        }

        target_state = asyncio.run(
            container.fixture.run_diagnostic(
                tenant_id=tenant_id,
                run_id=run_id,
                diagnostic_type=DiagnosticType.ACCESS_LINK,
                target_id=ATTACHMENT_ID,
            )
        )
        other_state = asyncio.run(
            container.fixture.run_diagnostic(
                tenant_id=other_tenant_id,
                run_id=other_run_id,
                diagnostic_type=DiagnosticType.ACCESS_LINK,
                target_id=ATTACHMENT_ID,
            )
        )
        assert target_state is not None
        assert target_state.operational_state is OperationalState.UP
        assert other_state is not None
        assert other_state.operational_state is OperationalState.DOWN

        approved = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "phase6d-human"},
        )
        assert approved.status_code == 200, approved.text
        body = approved.json()

        assert body["approval"]["decision"] == "APPROVED"
        assert body["proposal"]["status"] == "STALE"
        assert body["incident"]["status"] == "OPEN"
        assert body["executed_action"] is None
        assert body["work_order"] is None
        assert body["agent_resume"]["status"] == "resumed"

        assert len(runtime.calls) == 1
        payload = runtime.calls[0]["decision_payload"]
        assert payload["decision"] == "APPROVED"
        assert payload["proposal_status"] == "STALE"
        assert payload["executed_action"] is None
        assert payload["work_order"] is None
        assert payload["repair_confirmed"] is False

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        assert state.status_code == 200
        snapshot = state.json()
        assert snapshot["run"]["status"] == "ACTIVE"
        assert len(snapshot["approvals"]) == 1
        assert snapshot["proposals"][0]["status"] == "STALE"
        assert snapshot["executed_actions"] == []
        assert snapshot["work_orders"] == []
