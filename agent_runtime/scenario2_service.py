"""Native Google ADK invocation boundary for Scenario 2.

Phase 7C established durable event -> persistent native Session continuity.
Phase 7D keeps that lifecycle and adds Product tools plus the shared native
long-running human-decision pause/resume point.
"""

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

from product_backend.adapters.scenario2_tool_adapters import Scenario2ToolAdapter

from .human_decision import WAIT_FOR_HUMAN_DECISION_TOOL
from .scenario2_agent import build_scenario2_agent
from .retry import ProductRetryableToolPlugin
from .service import (
    AgentResumeResult,
    _find_human_decision_correlation,
    _latest_final_answer,
)
from .sessions import ADK_APP_NAME, ensure_run_session, get_run_session


@dataclass(frozen=True, slots=True)
class Scenario2AgentInvocationResult:
    """Stable native-ADK point reached for a single Product event."""

    session_id: str
    invocation_id: str | None
    final_answer: str | None
    recoverable: bool
    awaiting_human_decision: bool = False
    pending_proposal_id: str | None = None
    paused_function_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class _Scenario2EventCorrelation:
    invocation_id: str
    settled: bool
    final_answer: str | None
    pending_proposal_id: str | None
    paused_function_call_id: str | None
    proposal_created_without_wait: bool


def _safe_event_text(event: Any) -> str | None:
    """Read displayable text without projecting hidden model reasoning."""
    content = getattr(event, "content", None)
    if content is None:
        return None
    text_parts = [
        part.text
        for part in content.parts or []
        if part.text and not part.thought
    ]
    return "\n".join(text_parts) if text_parts else None


def _scenario2_product_event_id(event: Any) -> str | None:
    if getattr(event, "author", None) != "user":
        return None
    if not getattr(event, "invocation_id", None):
        return None
    text = _safe_event_text(event)
    if not text:
        return None
    try:
        envelope = json.loads(text)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(envelope, dict)
        or envelope.get("type") != "scenario2_operational_signal"
    ):
        return None
    event_id = envelope.get("product_event_id")
    return event_id if isinstance(event_id, str) and event_id else None


def _pending_major_incident_proposal_id(event: Any) -> str | None:
    """Extract only a successful PENDING_APPROVAL proposal tool response."""
    for response in event.get_function_responses():
        if response.name != "propose_major_incident":
            continue
        payload = response.response
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            continue
        proposal = payload.get("proposal")
        if not isinstance(proposal, dict):
            continue
        proposal_id = proposal.get("proposal_id")
        if (
            proposal.get("status") == "PENDING_APPROVAL"
            and isinstance(proposal_id, str)
            and proposal_id
        ):
            return proposal_id
    return None


def _find_scenario2_event_correlation(
    events: list[Any],
    *,
    product_event_id: str,
) -> _Scenario2EventCorrelation | None:
    """Find the one native invocation associated with a Product event ID."""
    invocation_ids = {
        event.invocation_id
        for event in events
        if _scenario2_product_event_id(event) == product_event_id
        and getattr(event, "invocation_id", None)
    }
    if not invocation_ids:
        return None
    if len(invocation_ids) != 1:
        raise RuntimeError(
            "Product event is correlated to multiple native ADK invocations"
        )
    invocation_id = next(iter(invocation_ids))

    settled = False
    final_answer: str | None = None
    pending_proposal_id: str | None = None
    paused_function_call_id: str | None = None
    proposal_created_without_wait = False

    for event in events:
        if getattr(event, "invocation_id", None) != invocation_id:
            continue

        created_proposal_id = _pending_major_incident_proposal_id(event)
        if created_proposal_id is not None:
            if (
                pending_proposal_id is not None
                and pending_proposal_id != created_proposal_id
            ):
                raise RuntimeError(
                    "Scenario 2 invocation created multiple pending proposals"
                )
            pending_proposal_id = created_proposal_id
            proposal_created_without_wait = True

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
                    if pending_proposal_id is None:
                        raise RuntimeError(
                            "Scenario 2 native wait has no successful Product proposal"
                        )
                    if pending_proposal_id != proposal_id:
                        raise RuntimeError(
                            "Scenario 2 native wait does not match Product proposal"
                        )
                    paused_function_call_id = call.id
                    proposal_created_without_wait = False
                    settled = True

        is_final = getattr(event, "is_final_response", None)
        if callable(is_final) and is_final():
            settled = True
            text = _safe_event_text(event)
            if text:
                final_answer = text

        actions = getattr(event, "actions", None)
        if actions is not None and getattr(actions, "end_of_agent", False):
            settled = True

    if paused_function_call_id is not None:
        response_delivered = any(
            getattr(event, "invocation_id", None) == invocation_id
            and getattr(event, "author", None) == "user"
            and any(
                response.name == WAIT_FOR_HUMAN_DECISION_TOOL
                and response.id == paused_function_call_id
                for response in event.get_function_responses()
            )
            for event in events
        )
        if response_delivered:
            paused_function_call_id = None

    if proposal_created_without_wait:
        settled = False

    return _Scenario2EventCorrelation(
        invocation_id=invocation_id,
        settled=settled,
        final_answer=final_answer,
        pending_proposal_id=pending_proposal_id,
        paused_function_call_id=paused_function_call_id,
        proposal_created_without_wait=proposal_created_without_wait,
    )


class Scenario2AgentRuntime:
    """One native ADK Runner; Product state remains outside the runtime."""

    def __init__(
        self,
        *,
        adapter: Scenario2ToolAdapter,
        session_service: DatabaseSessionService,
    ) -> None:
        app = App(
            name=ADK_APP_NAME,
            root_agent=build_scenario2_agent(adapter),
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

    @property
    def resumability_wired(self) -> bool:
        config = self._runner.resumability_config
        return bool(config is not None and config.is_resumable)

    async def close(self) -> None:
        await self._runner.close()

    async def invoke_operational_signal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        product_event_id: str,
        operational_fact: dict[str, Any],
    ) -> Scenario2AgentInvocationResult:
        """Deliver one Product event to one recoverable native ADK invocation."""
        session = await ensure_run_session(
            self._session_service,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        correlation = _find_scenario2_event_correlation(
            list(session.events),
            product_event_id=product_event_id,
        )
        if correlation is not None and correlation.settled:
            return Scenario2AgentInvocationResult(
                session_id=run_id,
                invocation_id=correlation.invocation_id,
                final_answer=correlation.final_answer,
                recoverable=True,
                awaiting_human_decision=(
                    correlation.paused_function_call_id is not None
                ),
                pending_proposal_id=correlation.pending_proposal_id,
                paused_function_call_id=correlation.paused_function_call_id,
            )

        invocation_id = (
            correlation.invocation_id if correlation is not None else None
        )
        final_answer: str | None = None
        recoverable = False
        pending_proposal_id: str | None = None
        paused_function_call_id: str | None = None
        proposal_created_without_wait = False

        if correlation is None:
            message = types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=json.dumps(
                            {
                                "type": "scenario2_operational_signal",
                                "product_event_id": product_event_id,
                                "payload": operational_fact,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                    )
                ],
            )
            stream = self._runner.run_async(
                user_id=tenant_id,
                session_id=run_id,
                new_message=message,
            )
        else:
            stream = self._runner.run_async(
                user_id=tenant_id,
                session_id=run_id,
                invocation_id=correlation.invocation_id,
                new_message=None,
            )

        async for event in stream:
            if invocation_id is None and event.invocation_id:
                invocation_id = event.invocation_id

            created_proposal_id = _pending_major_incident_proposal_id(event)
            if created_proposal_id is not None:
                if (
                    pending_proposal_id is not None
                    and pending_proposal_id != created_proposal_id
                ):
                    raise RuntimeError(
                        "Scenario 2 invocation created multiple pending proposals"
                    )
                pending_proposal_id = created_proposal_id
                proposal_created_without_wait = True

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
                        if pending_proposal_id is None:
                            raise RuntimeError(
                                "Scenario 2 native wait has no successful Product proposal"
                            )
                        if pending_proposal_id != proposal_id:
                            raise RuntimeError(
                                "Scenario 2 native wait does not match Product proposal"
                            )
                        paused_function_call_id = call.id
                        proposal_created_without_wait = False
                        invocation_id = event.invocation_id or invocation_id
                        recoverable = True

            if event.is_final_response():
                recoverable = True
                text = _safe_event_text(event)
                if text:
                    final_answer = text

            actions = getattr(event, "actions", None)
            if actions is not None and getattr(actions, "end_of_agent", False):
                recoverable = True

        return Scenario2AgentInvocationResult(
            session_id=run_id,
            invocation_id=invocation_id,
            final_answer=final_answer,
            recoverable=bool(
                recoverable
                and invocation_id
                and not proposal_created_without_wait
            ),
            awaiting_human_decision=paused_function_call_id is not None,
            pending_proposal_id=pending_proposal_id,
            paused_function_call_id=paused_function_call_id,
        )

    async def resume_human_decision(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
        decision_payload: dict[str, Any],
    ) -> AgentResumeResult:
        """Resume the exact native invocation after the Product decision commits."""
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

        if correlation.completed:
            return AgentResumeResult(
                invocation_id=correlation.invocation_id,
                function_call_id=correlation.function_call_id,
                final_answer=_latest_final_answer(
                    list(session.events),
                    invocation_id=correlation.invocation_id,
                ),
                already_resumed=True,
            )

        resume_message: types.Content | None
        if correlation.response_delivered:
            resume_message = None
        else:
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


__all__ = [
    "Scenario2AgentInvocationResult",
    "Scenario2AgentRuntime",
    "_find_scenario2_event_correlation",
    "_scenario2_product_event_id",
]
