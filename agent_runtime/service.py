"""Native ADK Runner composition for live Scenario 1 invocations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any

from google.adk.apps import App
from google.adk.apps.app import ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from product_backend.adapters.tool_adapters import Scenario1ToolAdapter

from .agent import MODEL, build_scenario1_agent
from .gemini_keys import GeminiKeyPool, model_for_pool
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
    proposal_created_without_wait: bool


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


def _operational_event_identity(event: Any) -> tuple[str, str] | None:
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
    if not isinstance(payload, dict) or payload.get("type") not in {
        "operational_signal",
        "required_outcome_continuation",
    }:
        return None
    event_id = payload.get("operational_event_id")
    event_type = payload.get("type")
    if not isinstance(event_id, str) or not event_id:
        return None
    return event_id, event_type


def _operational_event_id(event: Any) -> str | None:
    identity = _operational_event_identity(event)
    return identity[0] if identity is not None else None


MAX_REQUIRED_OUTCOME_CONTINUATIONS = 2


def _required_outcome_continuation_count(
    events: list[Any],
    *,
    operational_event_id: str,
) -> int:
    return sum(
        1
        for event in events
        if (identity := _operational_event_identity(event)) is not None
        and identity == (operational_event_id, "required_outcome_continuation")
    )


def _successful_pending_proposal_ids(
    event: Any,
    *,
    tool_names: frozenset[str],
) -> tuple[str, ...]:
    """Extract successful PENDING_APPROVAL proposal IDs from Product tool responses."""
    get_responses = getattr(event, "get_function_responses", None)
    if not callable(get_responses):
        return ()

    proposal_ids: list[str] = []
    for response in get_responses():
        if response.name not in tool_names:
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
            proposal_ids.append(proposal_id)
    return tuple(proposal_ids)


def _pending_field_visit_proposal_id(event: Any) -> str | None:
    proposal_ids = _successful_pending_proposal_ids(
        event,
        tool_names=frozenset({"propose_field_visit"}),
    )
    if len(set(proposal_ids)) > 1:
        raise RuntimeError(
            "Device-Incident invocation returned multiple pending field-visit proposals"
        )
    return proposal_ids[-1] if proposal_ids else None


def _find_operational_event_correlation(
    events: list[Any],
    *,
    operational_event_id: str,
) -> _OperationalEventCorrelation | None:
    matches = [
        (event.invocation_id, identity[1])
        for event in events
        if (identity := _operational_event_identity(event)) is not None
        and identity[0] == operational_event_id
        and getattr(event, "invocation_id", None)
    ]
    if not matches:
        return None
    original_invocation_ids = {
        invocation_id
        for invocation_id, event_type in matches
        if event_type == "operational_signal"
    }
    if len(original_invocation_ids) > 1:
        raise RuntimeError(
            "Product operational event is correlated to multiple native invocations"
        )
    # Required-outcome continuations may legitimately create later invocations;
    # recovery follows the latest correlated invocation.
    invocation_id = matches[-1][0]

    settled = False
    final_answer: str | None = None
    pending_proposal_id: str | None = None
    paused_function_call_id: str | None = None
    proposal_created_without_wait = False

    for event in events:
        if getattr(event, "invocation_id", None) != invocation_id:
            continue

        created_proposal_id = _pending_field_visit_proposal_id(event)
        if created_proposal_id is not None:
            if (
                pending_proposal_id is not None
                and pending_proposal_id != created_proposal_id
            ):
                raise RuntimeError(
                    "Device-Incident invocation created multiple pending proposals"
                )
            pending_proposal_id = created_proposal_id
            proposal_created_without_wait = True

        long_running_ids = set(
            getattr(event, "long_running_tool_ids", None) or []
        )
        get_calls = getattr(event, "get_function_calls", None)
        for call in (get_calls() if callable(get_calls) else []):
            if (
                call.name == WAIT_FOR_HUMAN_DECISION_TOOL
                and call.id
                and call.id in long_running_ids
            ):
                args = dict(call.args or {})
                proposal_id = args.get("proposal_id")
                if not isinstance(proposal_id, str) or not proposal_id:
                    continue
                if pending_proposal_id is None:
                    raise RuntimeError(
                        "Device-Incident native wait has no successful Product proposal"
                    )
                if pending_proposal_id != proposal_id:
                    raise RuntimeError(
                        "Device-Incident native wait does not match Product proposal"
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
            and callable(getattr(event, "get_function_responses", None))
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

    return _OperationalEventCorrelation(
        invocation_id=invocation_id,
        settled=settled,
        final_answer=final_answer,
        pending_proposal_id=pending_proposal_id,
        paused_function_call_id=paused_function_call_id,
        proposal_created_without_wait=proposal_created_without_wait,
    )


def _find_human_decision_correlation(
    events: list[Any],
    *,
    session_id: str,
    proposal_id: str,
) -> _HumanDecisionCorrelation | None:
    """Resolve only a successful Product proposal -> exact native wait link.

    A wait call is eligible only when the same invocation previously observed a
    successful PENDING_APPROVAL response from the corresponding Product proposal
    tool. This supports both device-Incident field visits and the existing
    Scenario 2 Major Incident path without trusting a bare model-supplied ID.
    """
    created_by_invocation: dict[str, set[str]] = {}
    candidates: list[tuple[int, _HumanDecisionCorrelation]] = []
    proposal_tools = frozenset({"propose_field_visit", "propose_major_incident"})

    for index, event in enumerate(events):
        invocation_id = getattr(event, "invocation_id", None)
        if not invocation_id:
            continue

        created = created_by_invocation.setdefault(invocation_id, set())
        created.update(
            _successful_pending_proposal_ids(
                event,
                tool_names=proposal_tools,
            )
        )

        long_running_ids = set(
            getattr(event, "long_running_tool_ids", None) or []
        )
        get_calls = getattr(event, "get_function_calls", None)
        for call in (get_calls() if callable(get_calls) else []):
            if (
                call.name != WAIT_FOR_HUMAN_DECISION_TOOL
                or not call.id
                or call.id not in long_running_ids
            ):
                continue
            args = dict(call.args or {})
            if args.get("proposal_id") != proposal_id:
                continue
            if proposal_id not in created:
                continue
            candidates.append(
                (
                    index,
                    _HumanDecisionCorrelation(
                        proposal_id=proposal_id,
                        session_id=session_id,
                        invocation_id=invocation_id,
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
        get_responses = getattr(event, "get_function_responses", None)
        if not callable(get_responses):
            continue
        if any(
            response.name == WAIT_FOR_HUMAN_DECISION_TOOL
            and response.id == latest.function_call_id
            for response in get_responses()
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
        get_calls = getattr(event, "get_function_calls", None)
        get_responses = getattr(event, "get_function_responses", None)
        if (
            not (get_calls() if callable(get_calls) else [])
            and not (get_responses() if callable(get_responses) else [])
            and not set(getattr(event, "long_running_tool_ids", None) or [])
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


class DeviceIncidentAgentRuntime:
    """Shared resumable native runtime for Scenario 1 and Scenario 3."""

    def __init__(
        self,
        *,
        adapter: Any,
        session_service: DatabaseSessionService,
        scenario_id: str,
        agent_builder: Callable[..., Any],
        require_proposal_hitl: bool = False,
    ) -> None:
        if scenario_id not in {"scenario-1", "scenario-3"}:
            raise ValueError("unsupported device-Incident scenario_id")
        self._scenario_id = scenario_id
        self._require_proposal_hitl = require_proposal_hitl
        self._key_pool = GeminiKeyPool()
        app = App(
            name=ADK_APP_NAME,
            root_agent=agent_builder(
                adapter,
                model=model_for_pool(self._key_pool, MODEL),
            ),
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
        return self._key_pool.configured

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
        force_required_outcome_continuation: bool = False,
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
            continuation_count = _required_outcome_continuation_count(
                list(session.events),
                operational_event_id=operational_event_id,
            )
            continuation_required = bool(
                self._require_proposal_hitl
                and correlation is not None
                and correlation.pending_proposal_id is None
                and correlation.paused_function_call_id is None
                and (
                    correlation.settled
                    or (
                        force_required_outcome_continuation
                        and continuation_count < MAX_REQUIRED_OUTCOME_CONTINUATIONS
                    )
                )
            )
            if correlation is not None and correlation.settled and not continuation_required:
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
        else:
            continuation_required = False

        envelope = {
            "type": "operational_signal",
            "scenario": self._scenario_id,
            "payload": operational_signal,
        }
        if operational_event_id:
            envelope["operational_event_id"] = operational_event_id

        if continuation_required:
            envelope = {
                "type": "required_outcome_continuation",
                "scenario": self._scenario_id,
                "operational_event_id": operational_event_id,
                "instruction": (
                    "The prior invocation ended without the mandatory proposal/"
                    "HITL outcome. Reuse successful Product evidence already in "
                    "session history; do not repeat successful read tools. Complete "
                    "the required proposal and await_human_decision now."
                ),
            }

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
            None
            if continuation_required
            else (correlation.invocation_id if correlation is not None else None)
        )
        final_answer: str | None = None
        pending_proposal_id: str | None = (
            correlation.pending_proposal_id if correlation is not None else None
        )
        paused_function_call_id: str | None = None
        proposal_created_without_wait = (
            correlation.proposal_created_without_wait
            if correlation is not None
            else False
        )

        if correlation is not None and not continuation_required:
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

            created_proposal_id = _pending_field_visit_proposal_id(event)
            if created_proposal_id is not None:
                if (
                    pending_proposal_id is not None
                    and pending_proposal_id != created_proposal_id
                ):
                    raise RuntimeError(
                        "Device-Incident invocation created multiple pending proposals"
                    )
                pending_proposal_id = created_proposal_id
                proposal_created_without_wait = True

            long_running_ids = set(
                getattr(event, "long_running_tool_ids", None) or []
            )
            get_calls = getattr(event, "get_function_calls", None)
            for call in (get_calls() if callable(get_calls) else []):
                if (
                    call.name == WAIT_FOR_HUMAN_DECISION_TOOL
                    and call.id
                    and call.id in long_running_ids
                ):
                    args = dict(call.args or {})
                    proposal_id = args.get("proposal_id")
                    if not isinstance(proposal_id, str) or not proposal_id:
                        continue
                    if pending_proposal_id is None:
                        raise RuntimeError(
                            "Device-Incident native wait has no successful Product proposal"
                        )
                    if pending_proposal_id != proposal_id:
                        raise RuntimeError(
                            "Device-Incident native wait does not match Product proposal"
                        )
                    paused_function_call_id = call.id
                    proposal_created_without_wait = False
                    invocation_id = event.invocation_id or invocation_id

            if event.is_final_response():
                text = _safe_event_text(event)
                if text:
                    final_answer = text

        if proposal_created_without_wait:
            raise RuntimeError(
                "Pending field-visit proposal has no exact native wait correlation"
            )

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


class Scenario1AgentRuntime(DeviceIncidentAgentRuntime):
    """Historical Scenario 1 name backed by the shared device-Incident runtime."""

    def __init__(
        self,
        *,
        adapter: Scenario1ToolAdapter,
        session_service: DatabaseSessionService,
    ) -> None:
        super().__init__(
            adapter=adapter,
            session_service=session_service,
            scenario_id="scenario-1",
            agent_builder=build_scenario1_agent,
        )


__all__ = [
    "AgentInvocationResult",
    "AgentResumeResult",
    "DeviceIncidentAgentRuntime",
    "Scenario1AgentRuntime",
    "_find_human_decision_correlation",
    "_latest_final_answer",
]
