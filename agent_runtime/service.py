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
    response_delivered: bool
    completed: bool


@dataclass(frozen=True, slots=True)
class _OperationalEventCorrelation:
    invocation_id: str
    settled: bool
    final_answer: str | None
    pending_proposal_id: str | None
    paused_function_call_id: str | None


def _safe_event_text(event: Any) -> str | None:
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
    events: list[Any],
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


def _operational_event_id(event: Any) -> str | None:
    if getattr(event, "author", None) != "user":
        return None
    if not getattr(event, "invocation_id", None):
        return None
    text = _safe_event_text(event)
    if not text:
        return None
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("type") != "operational_signal":
        return None
    event_id = payload.get("operational_event_id")
    return event_id if isinstance(event_id, str) and event_id else None


def _find_operational_event_correlation(
    events: list[Any],
    *,
    operational_event_id: str,
) -> _OperationalEventCorrelation | None:
    invocation_id: str | None = None
    for event in events:
        if _operational_event_id(event) == operational_event_id:
            invocation_id = event.invocation_id

    if invocation_id is None:
        return None

    settled = False
    final_answer: str | None = None
    pending_proposal_id: str | None = None
    paused_function_call_id: str | None = None

    for event in events:
        if getattr(event, "invocation_id", None) != invocation_id:
            continue

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

    return _OperationalEventCorrelation(
        invocation_id=invocation_id,
        settled=settled,
        final_answer=final_answer,
        pending_proposal_id=pending_proposal_id,
        paused_function_call_id=paused_function_call_id,
    )


def _find_human_decision_correlation(
    events: list[Any],
    *,
    session_id: str,
    proposal_id: str,
) -> _HumanDecisionCorrelation | None:
    """Resolve Product proposal -> native ADK invocation/function-call link.

    Correlation lives in the persistent native ADK Session Event stream:
    proposal_id is an argument of await_human_decision, while invocation_id and
    function-call id are framework-owned event metadata. A matching user
    FunctionResponse proves decision delivery. Completion is separate: a
    provider failure may happen after the FunctionResponse was persisted.
    """
    candidates: list[tuple[int, _HumanDecisionCorrelation]] = []

    for index, event in enumerate(events):
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
                (
                    index,
                    _HumanDecisionCorrelation(
                        proposal_id=proposal_id,
                        session_id=session_id,
                        invocation_id=event.invocation_id,
                        function_call_id=call.id,
                        response_delivered=False,
                        completed=False,
                    ),
                )
            )

    if not candidates:
        return None

    _, latest = candidates[-1]
    response_index: int | None = None
    for index, event in enumerate(events):
        if getattr(event, "invocation_id", None) != latest.invocation_id:
            continue
        if getattr(event, "author", None) != "user":
            continue
        if any(
            response.name == WAIT_FOR_HUMAN_DECISION_TOOL
            and response.id == latest.function_call_id
            for response in event.get_function_responses()
        ):
            response_index = index

    if response_index is None:
        return latest

    completed = False
    for event in events[response_index + 1 :]:
        if getattr(event, "invocation_id", None) != latest.invocation_id:
            continue
        if getattr(event, "author", None) == "user":
            continue
        actions = getattr(event, "actions", None)
        if actions is not None and getattr(actions, "end_of_agent", False):
            completed = True
            break
        if (
            not event.get_function_calls()
            and not event.get_function_responses()
            and not set(event.long_running_tool_ids or [])
            and _safe_event_text(event)
        ):
            completed = True
            break

    return _HumanDecisionCorrelation(
        proposal_id=latest.proposal_id,
        session_id=latest.session_id,
        invocation_id=latest.invocation_id,
        function_call_id=latest.function_call_id,
        response_delivered=True,
        completed=completed,
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

    @property
    def resumability_wired(self) -> bool:
        config = self._runner.resumability_config
        return bool(config is not None and config.is_resumable)

    async def close(self) -> None:
        await self._runner.close()

    async def invoke(
        self,
        *,
        tenant_id: str,
        run_id: str,
        operational_signal: dict[str, Any],
    ) -> AgentInvocationResult:
        """Compatibility/debug invocation without a durable event identity."""
        return await self.invoke_operational_event(
            tenant_id=tenant_id,
            run_id=run_id,
            operational_event_id=None,
            operational_signal=operational_signal,
        )

    async def invoke_operational_event(
        self,
        *,
        tenant_id: str,
        run_id: str,
        operational_event_id: str | None,
        operational_signal: dict[str, Any],
    ) -> AgentInvocationResult:
        """Invoke or recover the same native ADK invocation for one Product event.

        The Product outbox may redeliver after a crash. The durable ADK Session
        history contains the Product event ID in the user message. If that event
        already reached a stable final response or native long-running
        human-decision pause, the result is replayed from ADK history. If the
        invocation exists but stopped mid-flight, native resumability continues
        the same invocation with new_message=None instead of creating a second
        independent runtime path.
        """
        session = await ensure_run_session(
            self._session_service,
            tenant_id=tenant_id,
            run_id=run_id,
        )

        correlation: _OperationalEventCorrelation | None = None
        if operational_event_id:
            correlation = _find_operational_event_correlation(
                list(session.events),
                operational_event_id=operational_event_id,
            )
            if correlation is not None and correlation.settled:
                return AgentInvocationResult(
                    session_id=run_id,
                    invocation_id=correlation.invocation_id,
                    final_answer=correlation.final_answer,
                    awaiting_human_decision=(
                        correlation.paused_function_call_id is not None
                    ),
                    pending_proposal_id=correlation.pending_proposal_id,
                    paused_function_call_id=correlation.paused_function_call_id,
                )

        envelope = {
            "type": "operational_signal",
            "scenario": "scenario-1",
            "payload": operational_signal,
        }
        if operational_event_id:
            envelope["operational_event_id"] = operational_event_id

        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    text=json.dumps(
                        envelope,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
            ],
        )

        invocation_id: str | None = (
            correlation.invocation_id if correlation is not None else None
        )
        final_answer: str | None = None
        pending_proposal_id: str | None = None
        paused_function_call_id: str | None = None

        if correlation is not None:
            stream = self._runner.run_async(
                user_id=tenant_id,
                session_id=run_id,
                invocation_id=correlation.invocation_id,
                new_message=None,
            )
        else:
            stream = self._runner.run_async(
                user_id=tenant_id,
                session_id=run_id,
                new_message=message,
            )

        async for event in stream:
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

        Delivery is safely retryable from the existing Approve/Reject endpoint.
        Product decision replay is idempotent. Native ADK event history
        distinguishes a not-yet-delivered decision, a delivered response whose
        invocation still needs continuation, and an already completed resume.
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
            # The business result was already injected into the durable ADK
            # event history, but the invocation did not complete (for example,
            # provider quota failed after session append). Native resumability
            # continues from persisted history without injecting it twice.
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
