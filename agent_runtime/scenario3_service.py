"""Scenario 3 thin configuration over the shared device-Incident runtime."""

from __future__ import annotations

from google.adk.sessions import DatabaseSessionService

from product_backend.adapters.scenario3_tool_adapters import Scenario3ToolAdapter

from .scenario3_agent import build_scenario3_agent
from .gemini_keys import GeminiProviderCoordinator
from .service import DeviceIncidentAgentRuntime


class Scenario3AgentRuntime(DeviceIncidentAgentRuntime):
    """Scenario 3 uses the same persistent session/invocation mechanics as Scenario 1."""

    def __init__(
        self,
        *,
        adapter: Scenario3ToolAdapter,
        session_service: DatabaseSessionService,
        provider_coordinator: GeminiProviderCoordinator | None = None,
    ) -> None:
        super().__init__(
            adapter=adapter,
            session_service=session_service,
            scenario_id="scenario-3",
            agent_builder=build_scenario3_agent,
            require_proposal_hitl=True,
            provider_coordinator=provider_coordinator,
        )


__all__ = ["Scenario3AgentRuntime"]
