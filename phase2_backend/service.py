"""Ephemeral native-ADK service for validating the Phase 2 deployment."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from phase1_adk_spike.agent import root_agent
from phase1_adk_spike.contracts import APP_NAME, INITIAL_EVENT, MODEL, USER_ID
from phase1_adk_spike.runner import _safe_trace_event, make_initial_message, utc_now
from phase1_adk_spike.runner import validate_tool_dependency


@dataclass
class ProbeRun:
    """Only process-local state: it is intentionally not a product persistence model."""

    run_id: str
    session_id: str
    started_at: str
    status: str = "running"
    finished_at: str | None = None
    trace: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    error: dict[str, str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "initial_input": INITIAL_EVENT,
            "versions": {
                "python": sys.version.split()[0],
                "adk": "2.10.0",
                "model": MODEL,
            },
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
            "trace": self.trace,
            "validation": validate_tool_dependency(self.tool_calls, self.tool_results),
            "error": self.error,
        }


class Phase2ProbeService:
    """Runs one ADK invocation at a time and exposes audit-safe run facts."""

    def __init__(self) -> None:
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=root_agent, app_name=APP_NAME, session_service=self._session_service
        )
        self._runs: dict[str, ProbeRun] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def api_key_available() -> bool:
        return bool(os.environ.get("GOOGLE_API_KEY"))

    async def start(self) -> ProbeRun:
        """Run the real model-selected dependency chain in one native session."""
        async with self._lock:
            run_id = f"phase2-{uuid.uuid4().hex[:12]}"
            session = await self._session_service.create_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=run_id
            )
            probe = ProbeRun(run_id=run_id, session_id=session.id, started_at=utc_now())
            self._runs[run_id] = probe
            await self._invoke(probe, make_initial_message())
            return probe

    async def follow_up(self, run_id: str, text: str) -> ProbeRun | None:
        """Send a second user event to the same session for the hosting check."""
        async with self._lock:
            probe = self._runs.get(run_id)
            if not probe:
                return None
            probe.status = "running"
            probe.finished_at = None
            await self._invoke(
                probe, types.Content(role="user", parts=[types.Part(text=text)])
            )
            return probe

    def get(self, run_id: str) -> ProbeRun | None:
        return self._runs.get(run_id)

    async def _invoke(self, probe: ProbeRun, message: types.Content) -> None:
        try:
            async for event in self._runner.run_async(
                user_id=USER_ID, session_id=probe.session_id, new_message=message
            ):
                for record in _safe_trace_event(event):
                    record["at"] = utc_now()
                    probe.trace.append(record)
                    if record["kind"] == "tool_call":
                        probe.tool_calls.append(
                            {"name": record["name"], "args": record["args"]}
                        )
                    elif record["kind"] == "tool_result":
                        probe.tool_results.append(
                            {"name": record["name"], "response": record["response"]}
                        )
            probe.status = "completed"
        except Exception as error:
            probe.status = "failed"
            probe.error = {"type": type(error).__name__, "message": str(error)}
        finally:
            probe.finished_at = utc_now()
