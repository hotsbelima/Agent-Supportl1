"""Native ADK Runner composition for live Scenario 1 invocations."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from product_backend.adapters.tool_adapters import Scenario1ToolAdapter

from .agent import build_scenario1_agent
from .retry import ProductRetryableToolPlugin
from .sessions import ADK_APP_NAME, ensure_run_session


@dataclass(frozen=True, slots=True)
class AgentInvocationResult:
    session_id: str
    invocation_id: str | None
    final_answer: str | None


class Scenario1AgentRuntime:
    """One ADK Agent + Runner using the persistent Phase 6A session service."""

    def __init__(
        self,
        *,
        adapter: Scenario1ToolAdapter,
        session_service: DatabaseSessionService,
    ) -> None:
        agent = build_scenario1_agent(adapter)
        app = App(
            name=ADK_APP_NAME,
            root_agent=agent,
            plugins=[
                ProductRetryableToolPlugin(
                    max_retries=2,
                    throw_exception_if_retry_exceeded=False,
                )
            ],
        )
        self._runner = Runner(
            app=app,
            session_service=session_service,
            auto_create_session=False,
        )
        self._session_service = session_service

    @property
    def model(self) -> str:
        return str(self._runner.agent.model)

    @property
    def gemini_configured(self) -> bool:
        return bool(os.environ.get("GOOGLE_API_KEY"))

    async def close(self) -> None:
        await self._runner.close()

    async def invoke(
        self,
        *,
        tenant_id: str,
        run_id: str,
        operational_signal: dict[str, Any],
    ) -> AgentInvocationResult:
        await ensure_run_session(
            self._session_service,
            tenant_id=tenant_id,
            run_id=run_id,
        )

        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=json.dumps(
                        {
                            "type": "operational_signal",
                            "scenario": "scenario-1",
                            "payload": operational_signal,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            ],
        )

        invocation_id: str | None = None
        final_answer: str | None = None

        async for event in self._runner.run_async(
            user_id=tenant_id,
            session_id=run_id,
            new_message=message,
        ):
            if invocation_id is None and event.invocation_id:
                invocation_id = event.invocation_id

            if event.is_final_response() and event.content:
                text_parts = [
                    part.text
                    for part in event.content.parts or []
                    if part.text and not part.thought
                ]
                if text_parts:
                    final_answer = "\n".join(text_parts)

        return AgentInvocationResult(
            session_id=run_id,
            invocation_id=invocation_id,
            final_answer=final_answer,
        )
