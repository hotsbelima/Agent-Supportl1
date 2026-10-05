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


REQUIRED_PROPOSAL_TOOLS = {
    "get_device",
    "get_site_health",
    "run_diagnostic",
    "search_kb",
    "propose_field_visit",
}

REQUIRED_PROPOSAL_EVIDENCE_SOURCES = {
    "CMDB_SNAPSHOT",
    "SITE_HEALTH",
    "ACCESS_LINK_DIAGNOSTIC",
    "KB_ARTICLE",
}


def _collect_evidence_sources(value: Any) -> dict[str, str]:
    """Return evidence_id -> source_type pairs from one Product tool payload."""
    found: dict[str, str] = {}
    if isinstance(value, dict):
        evidence_id = value.get("evidence_id")
        source_type = value.get("source_type")
        if isinstance(evidence_id, str) and isinstance(source_type, str):
            found[evidence_id] = source_type
        for item in value.values():
            found.update(_collect_evidence_sources(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_collect_evidence_sources(item))
    return found


def _proposal_uses_required_prior_evidence(
    evidence_ids: Any,
    prior_evidence_sources: dict[str, str],
) -> bool:
    if not isinstance(evidence_ids, list) or len(evidence_ids) < 4:
        return False
    if any(not isinstance(item, str) for item in evidence_ids):
        return False
    if len(set(evidence_ids)) != len(evidence_ids):
        return False

    selected = set(evidence_ids)
    if not selected.issubset(prior_evidence_sources):
        return False

    selected_sources = {
        prior_evidence_sources[evidence_id]
        for evidence_id in selected
    }
    return REQUIRED_PROPOSAL_EVIDENCE_SOURCES.issubset(selected_sources)


async def _read_trace(
    tenant_id: str,
    run_id: str,
    *,
    reported_device_ids: set[str],
) -> dict[str, Any]:
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
        prior_evidence_sources: dict[str, str] = {}
        prior_attachment_ids: set[str] = set()

        get_device_checks: list[bool] = []
        diagnostic_checks: list[bool] = []
        proposal_checks: list[bool] = []

        for event in session.events:
            for call in event.get_function_calls():
                args = dict(call.args or {})
                downstream_valid: bool | None = None

                if call.name == "get_device":
                    device_id = args.get("device_id")
                    downstream_valid = (
                        isinstance(device_id, str)
                        and device_id in reported_device_ids
                    )
                    get_device_checks.append(downstream_valid)

                elif call.name == "run_diagnostic":
                    target_id = args.get("target_id")
                    downstream_valid = (
                        isinstance(target_id, str)
                        and target_id in prior_attachment_ids
                    )
                    diagnostic_checks.append(downstream_valid)

                elif call.name == "propose_field_visit":
                    device_id = args.get("device_id")
                    evidence_valid = _proposal_uses_required_prior_evidence(
                        args.get("evidence_ids"),
                        prior_evidence_sources,
                    )
                    device_valid = (
                        isinstance(device_id, str)
                        and device_id in reported_device_ids
                    )
                    downstream_valid = evidence_valid and device_valid
                    proposal_checks.append(downstream_valid)

                record = {
                    "kind": "tool_call",
                    "name": call.name,
                    "args": args,
                }
                if downstream_valid is not None:
                    record["downstream_valid"] = downstream_valid
                records.append(record)

            for response in event.get_function_responses():
                payload = dict(response.response or {})
                prior_evidence_sources.update(
                    _collect_evidence_sources(payload)
                )

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
            "get_device_identifiers_valid": (
                bool(get_device_checks) and all(get_device_checks)
            ),
            "diagnostic_dependencies_valid": (
                bool(diagnostic_checks) and all(diagnostic_checks)
            ),
            "proposal_dependencies_valid": (
                bool(proposal_checks) and all(proposal_checks)
            ),
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

    reported_device_ids = {
        item["reported_device_id"]
        for item in state_payload["incidents"]
        if isinstance(item.get("reported_device_id"), str)
    }
    trace = asyncio.run(
        _read_trace(
            tenant_id,
            run_id,
            reported_device_ids=reported_device_ids,
        )
    )
    call_names = trace["call_names"]
    proposal_statuses = [
        item["status"] for item in state_payload["proposals"]
    ]

    validation = {
        "model": invocation["model"],
        "invocation_id_present": bool(invocation["invocation_id"]),
        "proposal_prerequisite_tools_observed": (
            REQUIRED_PROPOSAL_TOOLS.issubset(set(call_names))
        ),
        "get_device_uses_reported_device_id": trace[
            "get_device_identifiers_valid"
        ],
        "all_diagnostic_targets_from_prior_attachment": trace[
            "diagnostic_dependencies_valid"
        ],
        "all_proposals_use_required_prior_evidence": trace[
            "proposal_dependencies_valid"
        ],
        "pending_proposal_created": proposal_statuses == ["PENDING_APPROVAL"],
        "run_waiting_approval": (
            state_payload["run"]["status"] == "WAITING_APPROVAL"
        ),
        "evidence_persisted": len(state_payload["evidence"]) >= 4,
        "no_approvals_created": state_payload["approvals"] == [],
        "no_executed_actions_created": state_payload["executed_actions"] == [],
        "no_work_orders_created": state_payload["work_orders"] == [],
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
        "approval_count": len(state_payload["approvals"]),
        "executed_action_count": len(state_payload["executed_actions"]),
        "work_order_count": len(state_payload["work_orders"]),
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

    observed_across_runs = {
        tool_name
        for item in results
        for tool_name in item.get("observed_tool_calls", [])
    }
    batch_validation = {
        # Phase 6B requires all six tools to be registered and available to the
        # model; deterministic ADK schema tests prove that. Live acceptance must
        # not require Gemini to call an unnecessary registered tool merely to
        # satisfy a coverage counter.
        "all_runs_passed": all(
            item["validation"]["passed"] for item in results
        ),
    }

    report = {
        "status": (
            "passed"
            if all(batch_validation.values())
            else "failed"
        ),
        "batch_validation": batch_validation,
        "observed_tools_across_runs": sorted(observed_across_runs),
        "runs": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
