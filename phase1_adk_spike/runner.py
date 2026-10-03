"""Run and audit real Google ADK + Gemini dependency-spike attempts.

Only model-visible function calls, function responses, and a final answer are
persisted. Deliberation/thought fields are deliberately omitted from traces.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from dotenv import load_dotenv

from .agent import root_agent
from .contracts import APP_NAME, ATTACHMENT_ID, INITIAL_EVENT, MODEL, USER_ID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACES_DIR = PROJECT_ROOT / "traces"
RESULTS_DIR = PROJECT_ROOT / "results"

def load_google_api_key(secret_file: Path) -> None:
    """Load a local .env file or a one-line managed secret without logging it."""
    # Normal development and most managed-secret mounts use dotenv syntax.
    load_dotenv(secret_file)
    if os.environ.get("GOOGLE_API_KEY"):
        return

    # Some secret-file UIs store the field content as a bare value. Accept only
    # a single non-comment, non-empty line in that fallback so a malformed
    # dotenv file cannot silently become an API key.
    try:
        meaningful_lines = [
            line.strip()
            for line in secret_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except OSError:
        return

    if len(meaningful_lines) == 1 and "=" not in meaningful_lines[0]:
        os.environ["GOOGLE_API_KEY"] = meaningful_lines[0]


# .env is local-only and ignored by Git. A pre-existing process environment
# value wins, so deployment can use its native secret management unchanged.
load_google_api_key(PROJECT_ROOT / ".env")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def make_initial_message() -> types.Content:
    """Create the only model-visible initial input; it has no attachment_id."""
    return types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(INITIAL_EVENT, ensure_ascii=False))],
    )


def validate_tool_dependency(
    tool_calls: list[dict[str, Any]], tool_results: list[dict[str, Any]]
) -> dict[str, Any]:
    """Check observed calls and the first observed result, not model text."""
    expected_names = ["get_device", "run_diagnostic"]
    observed_names = [call["name"] for call in tool_calls]
    first_two = tool_calls[:2]
    second_args = first_two[1]["args"] if len(first_two) > 1 else {}
    device_result = next(
        (
            item["response"]
            for item in tool_results
            if item["name"] == "get_device"
        ),
        {},
    )
    returned_attachment_id = device_result.get("attachment_id")

    return {
        "initial_input_has_attachment_id": "attachment_id" in INITIAL_EVENT,
        "observed_tool_names": observed_names,
        "exactly_two_tool_calls": len(tool_calls) == 2,
        "correct_tool_order": observed_names == expected_names,
        "first_tool_returned_attachment_id": returned_attachment_id,
        "second_call_used_returned_attachment_id": (
            returned_attachment_id == ATTACHMENT_ID
            and second_args.get("attachment_id") == returned_attachment_id
        ),
        "passed": (
            "attachment_id" not in INITIAL_EVENT
            and len(tool_calls) == 2
            and observed_names == expected_names
            and returned_attachment_id == ATTACHMENT_ID
            and second_args.get("attachment_id") == returned_attachment_id
        ),
    }


def _safe_trace_event(event: Any) -> list[dict[str, Any]]:
    """Convert ADK events into audit-safe facts; omit model thinking content."""
    records: list[dict[str, Any]] = []
    for call in event.get_function_calls():
        records.append(
            {
                "kind": "tool_call",
                "name": call.name,
                "args": dict(call.args or {}),
            }
        )
    for response in event.get_function_responses():
        records.append(
            {
                "kind": "tool_result",
                "name": response.name,
                "response": dict(response.response or {}),
            }
        )
    if event.is_final_response() and event.content:
        text_parts = [
            part.text
            for part in event.content.parts or []
            if part.text and not part.thought
        ]
        if text_parts:
            records.append({"kind": "final_answer", "text": "\n".join(text_parts)})
    return records


async def run_once(index: int) -> dict[str, Any]:
    """Run one complete agent invocation in one fresh native ADK session."""
    run_id = f"phase1-{index:02d}-{uuid.uuid4().hex[:8]}"
    trace: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=run_id
    )
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
    result: dict[str, Any] = {
        "run_id": run_id,
        "started_at": utc_now(),
        "versions": {"python": sys.version.split()[0], "adk": "2.10.0", "model": MODEL},
        "session_id": session.id,
        "initial_input": INITIAL_EVENT,
        "trace_file": str((TRACES_DIR / f"{run_id}.json").relative_to(PROJECT_ROOT)),
    }

    try:
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=make_initial_message(),
        ):
            for record in _safe_trace_event(event):
                record["at"] = utc_now()
                trace.append(record)
                if record["kind"] == "tool_call":
                    tool_calls.append({"name": record["name"], "args": record["args"]})
                if record["kind"] == "tool_result":
                    tool_results.append(
                        {"name": record["name"], "response": record["response"]}
                    )
        result["status"] = "completed"
    except Exception as error:  # A result file is more useful than losing a failed run.
        result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        trace.append(
            {
                "kind": "execution_error",
                "at": utc_now(),
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(limit=5),
            }
        )

    result["finished_at"] = utc_now()
    result["tool_calls"] = tool_calls
    result["tool_results"] = tool_results
    result["validation"] = validate_tool_dependency(tool_calls, tool_results)
    TRACES_DIR.mkdir(exist_ok=True)
    (TRACES_DIR / f"{run_id}.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


async def run_many(number_of_runs: int) -> int:
    if not os.environ.get("GOOGLE_API_KEY"):
        RESULTS_DIR.mkdir(exist_ok=True)
        report_path = RESULTS_DIR / (
            f"phase1-preflight-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        preflight = {
            "status": "not_run",
            "reason": "GOOGLE_API_KEY is not set; no Gemini request was sent",
            "requested_runs": number_of_runs,
            "versions": {"python": sys.version.split()[0], "adk": "2.10.0", "model": MODEL},
            "initial_input": INITIAL_EVENT,
        }
        report_path.write_text(
            json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({"report": str(report_path), **preflight}, ensure_ascii=False, indent=2))
        return 2

    results = [await run_once(index) for index in range(1, number_of_runs + 1)]
    RESULTS_DIR.mkdir(exist_ok=True)
    report_path = RESULTS_DIR / f"phase1-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    report_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"report": str(report_path), "runs": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["validation"]["passed"] for item in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Phase 1 ADK/Gemini spike.")
    parser.add_argument("--runs", type=int, default=3, help="Number of independent runs.")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    return asyncio.run(run_many(args.runs))


if __name__ == "__main__":
    raise SystemExit(main())
