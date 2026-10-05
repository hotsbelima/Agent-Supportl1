"""Live Phase 6B acceptance against real Gemini and PostgreSQL.

The script exercises the Product HTTP boundary, then reads persisted native ADK
events to validate actual model-selected tool calls. It never prints credentials,
raw prompts, hidden thoughts, or provider payloads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient

from agent_runtime.sessions import create_database_session_service, get_run_session
from product_api.app import create_app
from product_backend.persistence.database import DatabaseSettings, create_engine


REQUIRED_LIVE_TOOLS = {
    "get_device",
    "get_site_health",
    "run_diagnostic",
    "search_kb",
    "propose_field_visit",
}


def _collect_evidence_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        evidence_id = value.get("evidence_id")
        if isinstance(evidence_id, str):
            found.add(evidence_id)
        for item in value.values():
            found.update(_collect_evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_evidence_ids(item))
    return found


async def _read_trace(tenant_id: str, run_id: str) -> dict[str, Any]:
    engine = create_engine(DatabaseSettings.from_env())
    service = create_database_session_service(engine)
    try:
        session = await get_run_session(
            service,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if session is None:
            raise RuntimeError("Persisted ADK session was not found")

        records: list[dict[str, Any]] = []
        prior_evidence_ids: set[str] = set()
        prior_attachment_ids: set[str] = set()

        diagnostic_dependency = False
        proposal_dependency = False

        for event in session.events:
            for call in event.get_function_calls():
                args = dict(call.args or {})
                if call.name == "run_diagnostic":
                    target_id = args.get("target_id")
                    if (
                        isinstance(target_id, str)
                        and target_id in prior_attachment_ids
                    ):
                        diagnostic_dependency = True

                if call.name == "propose_field_visit":
                    evidence_ids = args.get("evidence_ids")
                    if (
                        isinstance(evidence_ids, list)
                        and len(evidence_ids) >= 4
                        and set(evidence_ids).issubset(prior_evidence_ids)
                    ):
                        proposal_dependency = True

                records.append(
                    {
                        "kind": "tool_call",
                        "name": call.name,
                        "args": args,
                    }
                )

            for response in event.get_function_responses():
                payload = dict(response.response or {})
                prior_evidence_ids.update(_collect_evidence_ids(payload))

                attachment_id = payload.get("attachment_id")
                if isinstance(attachment_id, str):
                    prior_attachment_ids.add(attachment_id)
                topology = payload.get("topology")
                if isinstance(topology, dict):
                    topology_attachment = topology.get("attachment_id")
                    if isinstance(topology_attachment, str):
                        prior_attachment_ids.add(topology_attachment)

                records.append(
                    {
                        "kind": "tool_result",
                        "name": response.name,
                        "ok": payload.get("ok"),
                    }
                )

        call_names = [
            item["name"]
            for item in records
            if item["kind"] == "tool_call"
        ]
        return {
            "call_names": call_names,
            "records": records,
            "diagnostic_dependency": diagnostic_dependency,
            "proposal_dependency": proposal_dependency,
        }
    finally:
        await engine.dispose()


def _one_live_run(index: int) -> dict[str, Any]:
    tenant_id = f"TENANT-6B-LIVE-{index}-{uuid4().hex[:8]}"
    headers = {"X-Tenant-ID": tenant_id}

    with TestClient(create_app()) as client:
        health = client.get("/health")
        if health.status_code != 200:
            raise RuntimeError(f"health failed: HTTP {health.status_code}")

        started = client.post(
            "/api/v1/scenario-1/runs",
            headers=headers,
        )
        if started.status_code != 201:
            raise RuntimeError(
                f"run start failed: HTTP {started.status_code} {started.text}"
            )
        run_id = started.json()["run"]["run_id"]

        invoked = client.post(
            f"/api/v1/runs/{run_id}/agent/invoke",
            headers=headers,
        )
        if invoked.status_code != 200:
            raise RuntimeError(
                f"agent invoke failed: HTTP {invoked.status_code} {invoked.text}"
            )

        invocation = invoked.json()
        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=headers,
        )
        if state.status_code != 200:
            raise RuntimeError(
                f"state fetch failed: HTTP {state.status_code} {state.text}"
            )
        state_payload = state.json()

    trace = asyncio.run(_read_trace(tenant_id, run_id))
    call_names = trace["call_names"]
    proposal_statuses = [
        item["status"] for item in state_payload["proposals"]
    ]

    validation = {
        "model": invocation["model"],
        "invocation_id_present": bool(invocation["invocation_id"]),
        "required_live_tools_observed": REQUIRED_LIVE_TOOLS.issubset(
            set(call_names)
        ),
        "diagnostic_target_from_prior_tool_result": trace[
            "diagnostic_dependency"
        ],
        "proposal_evidence_from_prior_tool_results": trace[
            "proposal_dependency"
        ],
        "pending_proposal_created": proposal_statuses == ["PENDING_APPROVAL"],
        "run_waiting_approval": (
            state_payload["run"]["status"] == "WAITING_APPROVAL"
        ),
        "evidence_persisted": len(state_payload["evidence"]) >= 4,
        "final_answer_present": bool(invocation["final_answer"]),
    }
    validation["passed"] = all(
        value
        for key, value in validation.items()
        if key not in {"model", "passed"}
    ) and invocation["model"] == "gemini-3.5-flash-lite"

    return {
        "run_id": run_id,
        "session_id": invocation["session_id"],
        "observed_tool_calls": call_names,
        "run_status": state_payload["run"]["status"],
        "proposal_statuses": proposal_statuses,
        "evidence_count": len(state_payload["evidence"]),
        "validation": validation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if not os.environ.get("DATABASE_URL"):
        print(json.dumps({"status": "not_run", "reason": "DATABASE_URL missing"}))
        return 2
    if not os.environ.get("GOOGLE_API_KEY"):
        print(
            json.dumps(
                {"status": "not_run", "reason": "GOOGLE_API_KEY missing"}
            )
        )
        return 3

    results: list[dict[str, Any]] = []
    for index in range(1, args.runs + 1):
        try:
            results.append(_one_live_run(index))
        except Exception as exc:
            results.append(
                {
                    "run": index,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "validation": {"passed": False},
                }
            )

    report = {
        "status": "passed"
        if all(item["validation"]["passed"] for item in results)
        else "failed",
        "runs": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
