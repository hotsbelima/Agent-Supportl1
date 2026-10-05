"""Native ADK Runner composition for live Scenario 1 invocations."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from google.adk.apps import App
from google.adk.apps.app import ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from product_backend.adapters.tool_adapters import Scenario1ToolAdapter

from .agent import build_scenario1_agent
from .human_decision import WAIT_FOR_HUMAN_DECISION_TOOL
from .retry import ProductRetryableToolPlugin
from .sessions import ADK_APP_NAME, ensure_run_session, get_run_session


@dataclass(frozen=True, slots=True)
class AgentInvocationResult:
    session_id: str
    invocation_id: str | None
    final_answer: str | None
    awaiting_human_decision: bool = False
    pending_proposal_id: str | None = None
    paused_function_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResumeResult:
    invocation_id: str
    function_call_id: str
    final_answer: str | None
    already_resumed: bool = False


@dataclass(frozen=True, slots=True)
class _HumanDecisionCorrelation:
    proposal_id: str
    session_id: str
    invocation_id: str
    function_call_id: str
    resolved: bool


def _safe_event_text(event: object) -> str | None:
    content = getattr(event, "content", None)
    if content is None:
        return None
    text_parts = [
        part.text
        for part in content.parts or []
        if part.text and not part.thought
    ]
    if not text_parts:
        return None
    return "\n".join(text_parts)


def _latest_final_answer(
    events: list[object],
    *,
    invocation_id: str,
) -> str | None:
    final_answer: str | None = None
    for event in events:
        if getattr(event, "invocation_id", None) != invocation_id:
            continue
        is_final = getattr(event, "is_final_response", None)
        if not callable(is_final) or not is_final():
            continue
        text = _safe_event_text(event)
        if text:
            final_answer = text
    return final_answer


def _find_human_decision_correlation(
    events: list[object],
    *,
    session_id: str,
    proposal_id: str,
) -> _HumanDecisionCorrelation | None:
    """Resolve Product proposal -> native ADK invocation/function-call link.

    The correlation is already durable in the persistent ADK Session Event
    stream: await_human_decision carries proposal_id as its argument while the
    event carries invocation_id and the native function-call id. A later
    user-authored FunctionResponse with that same id proves resume delivery.
    """
    resolved_ids: set[str] = set()
    candidates: list[_HumanDecisionCorrelation] = []

    for event in events:
        for response in event.get_function_responses():
            if (
                getattr(event, "author", None) == "user"
                and response.name == WAIT_FOR_HUMAN_DECISION_TOOL
                and response.id
            ):
                resolved_ids.add(response.id)

        for call in event.get_function_calls():
            if (
                call.name != WAIT_FOR_HUMAN_DECISION_TOOL
                or not call.id
                or not getattr(event, "invocation_id", None)
            ):
                continue
            args = dict(call.args or {})
            if args.get("proposal_id") != proposal_id:
                continue
            candidates.append(
                _HumanDecisionCorrelation(
                    proposal_id=proposal_id,
                    session_id=session_id,
                    invocation_id=event.invocation_id,
                    function_call_id=call.id,
                    resolved=False,
                )
            )

    if not candidates:
        return None

    latest = candidates[-1]
    return _HumanDecisionCorrelation(
        proposal_id=latest.proposal_id,
        session_id=latest.session_id,
        invocation_id=latest.invocation_id,
        function_call_id=latest.function_call_id,
        resolved=latest.function_call_id in resolved_ids,
    )


class Scenario1AgentRuntime:
    """One resumable ADK Agent + Runner with persistent native sessions/events."""

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
            resumability_config=ResumabilityConfig(is_resumable=True),
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
        pending_proposal_id: str | None = None
        paused_function_call_id: str | None = None

        async for event in self._runner.run_async(
            user_id=tenant_id,
            session_id=run_id,
            new_message=message,
        ):
            if invocation_id is None and event.invocation_id:
                invocation_id = event.invocation_id

            long_running_ids = set(event.long_running_tool_ids or [])
            for call in event.get_function_calls():
                if (
                    call.name == WAIT_FOR_HUMAN_DECISION_TOOL
                    and call.id
                    and call.id in long_running_ids
                ):
                    args = dict(call.args or {})
                    proposal_id = args.get("proposal_id")
                    if isinstance(proposal_id, str) and proposal_id:
                        pending_proposal_id = proposal_id
                        paused_function_call_id = call.id
                        invocation_id = event.invocation_id or invocation_id

            if event.is_final_response():
                text = _safe_event_text(event)
                if text:
                    final_answer = text

        return AgentInvocationResult(
            session_id=run_id,
            invocation_id=invocation_id,
            final_answer=final_answer,
            awaiting_human_decision=paused_function_call_id is not None,
            pending_proposal_id=pending_proposal_id,
            paused_function_call_id=paused_function_call_id,
        )

    async def find_human_decision_correlation(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> _HumanDecisionCorrelation | None:
        session = await get_run_session(
            self._session_service,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if session is None:
            return None
        return _find_human_decision_correlation(
            list(session.events),
            session_id=run_id,
            proposal_id=proposal_id,
        )

    async def resume_human_decision(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
        decision_payload: dict[str, Any],
    ) -> AgentResumeResult:
        """Resume the exact persisted ADK invocation after Product commit.

        Delivery is safely retryable from the existing Approve/Reject endpoint:
        Product decision replay is idempotent, and a persisted user-authored ADK
        FunctionResponse proves that this function-call id was already resumed.
        """
        session = await get_run_session(
            self._session_service,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if session is None:
            raise RuntimeError("Persisted ADK session was not found.")

        correlation = _find_human_decision_correlation(
            list(session.events),
            session_id=run_id,
            proposal_id=proposal_id,
        )
        if correlation is None:
            raise RuntimeError(
                "Persisted ADK human-decision correlation was not found."
            )

        if correlation.resolved:
            return AgentResumeResult(
                invocation_id=correlation.invocation_id,
                function_call_id=correlation.function_call_id,
                final_answer=_latest_final_answer(
                    list(session.events),
                    invocation_id=correlation.invocation_id,
                ),
                already_resumed=True,
            )

        resume_message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=correlation.function_call_id,
                        name=WAIT_FOR_HUMAN_DECISION_TOOL,
                        response=decision_payload,
                    )
                )
            ],
        )

        final_answer: str | None = None
        async for event in self._runner.run_async(
            user_id=tenant_id,
            session_id=run_id,
            invocation_id=correlation.invocation_id,
            new_message=resume_message,
        ):
            if event.is_final_response():
                text = _safe_event_text(event)
                if text:
                    final_answer = text

        return AgentResumeResult(
            invocation_id=correlation.invocation_id,
            function_call_id=correlation.function_call_id,
            final_answer=final_answer,
            already_resumed=False,
        )
