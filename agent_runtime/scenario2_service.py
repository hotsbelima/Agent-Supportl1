"""Native Google ADK invocation boundary for Scenario 2.

Phase 7C established durable event -> persistent native Session continuity.
Phase 7D keeps that lifecycle and adds Product tools plus the shared native
long-running human-decision pause/resume point.
"""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import aclosing
import json
import logging
from typing import Any

from google.adk.apps import App
from google.adk.apps.app import ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from product_backend.adapters.scenario2_tool_adapters import Scenario2ToolAdapter

from .human_decision import WAIT_FOR_HUMAN_DECISION_TOOL
from .agent import MODEL
from .gemini_keys import (
    GeminiProviderCoordinator,
    ProviderId,
    diagnostic_invocation,
    update_diagnostic_context,
    model_for_provider,
)
from .scenario2_agent import build_scenario2_agent
from .retry import ProductRetryableToolPlugin
from .service import (
    AgentResumeResult,
    _find_human_decision_correlation,
    _latest_final_answer,
)
from .sessions import ADK_APP_NAME, ensure_run_session, get_run_session

logger = logging.getLogger(__name__)


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
    invalid_native_wait: bool = False


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


def _scenario2_event_identity(event: Any) -> tuple[str, str] | None:
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
    if not isinstance(envelope, dict) or envelope.get("type") not in {
        "scenario2_operational_signal",
        "scenario2_required_outcome_continuation",
    }:
        return None
    event_id = envelope.get("product_event_id")
    event_type = envelope.get("type")
    if not isinstance(event_id, str) or not event_id:
        return None
    return event_id, event_type


def _scenario2_product_event_id(event: Any) -> str | None:
    identity = _scenario2_event_identity(event)
    return identity[0] if identity is not None else None


SCENARIO2_READ_TOOLS = frozenset(
    {
        "get_local_service_health",
        "get_service_dependencies",
        "get_external_dependency_status",
        "search_major_incidents",
    }
)
MAX_IDENTICAL_READ_CALLS_PER_INVOCATION = 1
MAX_REQUIRED_OUTCOME_CONTINUATIONS = 2


def _read_call_fingerprint(call: Any) -> str | None:
    if getattr(call, "name", None) not in SCENARIO2_READ_TOOLS:
        return None
    return json.dumps(
        {
            "name": call.name,
            "args": dict(getattr(call, "args", None) or {}),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _scenario2_read_call_counts(
    events: list[Any],
    *,
    invocation_id: str | None,
) -> dict[str, int]:
    if not invocation_id:
        return {}
    counts: dict[str, int] = {}
    for event in events:
        if getattr(event, "invocation_id", None) != invocation_id:
            continue
        get_calls = getattr(event, "get_function_calls", None)
        for call in (get_calls() if callable(get_calls) else []):
            fingerprint = _read_call_fingerprint(call)
            if fingerprint is None:
                continue
            counts[fingerprint] = counts.get(fingerprint, 0) + 1
    return counts


def _required_outcome_continuation_count(
    events: list[Any],
    *,
    product_event_id: str,
) -> int:
    return sum(
        1
        for event in events
        if (identity := _scenario2_event_identity(event)) is not None
        and identity == (product_event_id, "scenario2_required_outcome_continuation")
    )


def _pending_major_incident_proposal_id(event: Any) -> str | None:
    """Extract only a successful PENDING_APPROVAL proposal tool response."""
    get_responses = getattr(event, "get_function_responses", None)
    if not callable(get_responses):
        return None
    for response in get_responses():
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
    strict_native_wait: bool = True,
) -> _Scenario2EventCorrelation | None:
    """Find the one native invocation associated with a Product event ID."""
    matches = [
        (event.invocation_id, identity[1])
        for event in events
        if (identity := _scenario2_event_identity(event)) is not None
        and identity[0] == product_event_id
        and getattr(event, "invocation_id", None)
    ]
    if not matches:
        return None
    original_invocation_ids = {
        invocation_id
        for invocation_id, event_type in matches
        if event_type == "scenario2_operational_signal"
    }
    if len(original_invocation_ids) > 1:
        raise RuntimeError(
            "Product event is correlated to multiple native ADK invocations"
        )
    # Required-outcome continuations may legitimately create later invocations;
    # the latest correlated invocation owns recovery.
    invocation_id = matches[-1][0]

    settled = False
    final_answer: str | None = None
    pending_proposal_id: str | None = None
    paused_function_call_id: str | None = None
    proposal_created_without_wait = False
    invalid_native_wait = False
    correlated_ids = {item[0] for item in matches}
    # A correction invocation must retain a real proposal created by an earlier
    # invocation for this same Product event. Never trust a model-supplied ID.
    for prior in events:
        if getattr(prior, "invocation_id", None) in correlated_ids:
            prior_id = _pending_major_incident_proposal_id(prior)
            if prior_id is not None:
                if pending_proposal_id is not None and pending_proposal_id != prior_id:
                    raise RuntimeError("Scenario 2 invocation created multiple pending proposals")
                pending_proposal_id = prior_id
                proposal_created_without_wait = True

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
                if isinstance(proposal_id, str) and proposal_id:
                    if pending_proposal_id is None:
                        if strict_native_wait:
                            raise RuntimeError(
                                "Scenario 2 native wait has no successful Product proposal"
                            )
                        invalid_native_wait = True
                        continue
                    if pending_proposal_id != proposal_id:
                        if strict_native_wait:
                            raise RuntimeError(
                                "Scenario 2 native wait does not match Product proposal"
                            )
                        invalid_native_wait = True
                        continue
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

    return _Scenario2EventCorrelation(
        invocation_id=invocation_id,
        settled=settled,
        final_answer=final_answer,
        pending_proposal_id=pending_proposal_id,
        paused_function_call_id=paused_function_call_id,
        proposal_created_without_wait=proposal_created_without_wait,
        invalid_native_wait=invalid_native_wait,
    )


class Scenario2AgentRuntime:
    """One native ADK Runner; Product state remains outside the runtime."""

    def __init__(
        self,
        *,
        adapter: Scenario2ToolAdapter,
        session_service: DatabaseSessionService,
        provider_coordinator: GeminiProviderCoordinator | None = None,
    ) -> None:
        self._providers = provider_coordinator or GeminiProviderCoordinator()

        def make_runner(provider: ProviderId | None) -> Runner:
            root_agent = (
                build_scenario2_agent(
                    adapter,
                    model=model_for_provider(self._providers, provider, MODEL),
                )
                if provider is not None
                else build_scenario2_agent(adapter)
            )
            app = App(
                name=ADK_APP_NAME,
                root_agent=root_agent,
                plugins=[
                    ProductRetryableToolPlugin(
                        max_retries=2,
                        throw_exception_if_retry_exceeded=False,
                    )
                ],
                resumability_config=ResumabilityConfig(is_resumable=True),
            )
            return Runner(
                app=app,
                session_service=session_service,
                auto_create_session=False,
            )

        self._runners: dict[ProviderId | None, Runner] = (
            {provider: make_runner(provider) for provider in self._providers.configured_providers}
            if self._providers.configured
            else {None: make_runner(None)}
        )
        self._session_service = session_service

    @property
    def model(self) -> str:
        return MODEL

    @property
    def gemini_configured(self) -> bool:
        return self._providers.configured

    @property
    def resumability_wired(self) -> bool:
        config = next(iter(self._runners.values())).resumability_config
        return bool(config is not None and config.is_resumable)

    async def close(self) -> None:
        for runner in self._runners.values():
            await runner.close()

    async def _run_events(self, **kwargs: Any):
        """Run against one provider-pinned model for this native ADK invocation."""
        if not self._providers.configured:
            async with aclosing(self._runners[None].run_async(**kwargs)) as events:
                async for event in events:
                    yield event
            return
        async with self._providers.bind_invocation() as provider:
            update_diagnostic_context(provider=provider, invocation_id=kwargs.get("invocation_id"))
            async with aclosing(self._runners[provider].run_async(**kwargs)) as events:
                async for event in events:
                    update_diagnostic_context(invocation_id=event.invocation_id)
                    yield event

    @diagnostic_invocation
    async def invoke_operational_signal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        product_event_id: str,
        operational_fact: dict[str, Any],
        require_proposal_hitl: bool = False,
        force_required_outcome_continuation: bool = False,
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
            strict_native_wait=False,
        )
        continuation_count = _required_outcome_continuation_count(
            list(session.events),
            product_event_id=product_event_id,
        )
        repeated_read_loop = bool(
            correlation is not None
            and any(
                count > MAX_IDENTICAL_READ_CALLS_PER_INVOCATION
                for count in _scenario2_read_call_counts(
                    list(session.events),
                    invocation_id=correlation.invocation_id,
                ).values()
            )
        )
        continuation_required = bool(
            require_proposal_hitl
            and correlation is not None
            and (correlation.pending_proposal_id is None or correlation.invalid_native_wait)
            and correlation.paused_function_call_id is None
            and (
                correlation.settled
                or correlation.invalid_native_wait
                or repeated_read_loop
                or (
                    force_required_outcome_continuation
                    and continuation_count < MAX_REQUIRED_OUTCOME_CONTINUATIONS
                )
            )
        )
        if correlation is not None and correlation.settled and not continuation_required:
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
            None
            if continuation_required
            else (correlation.invocation_id if correlation is not None else None)
        )
        final_answer: str | None = None
        recoverable = False
        pending_proposal_id: str | None = (
            correlation.pending_proposal_id if correlation is not None else None
        )
        paused_function_call_id: str | None = None
        proposal_created_without_wait = pending_proposal_id is not None
        read_call_counts = _scenario2_read_call_counts(
            list(session.events),
            invocation_id=invocation_id,
        )

        if correlation is None or continuation_required:
            envelope = (
                {
                    "type": "scenario2_required_outcome_continuation",
                    "product_event_id": product_event_id,
                    "pending_proposal_id": pending_proposal_id,
                    "instruction": (
                        "The prior invocation ended without the mandatory Major "
                        "Incident proposal/HITL outcome. Reuse Product evidence "
                        "already present in session history while it is still fresh. "
                        "Refresh only evidence that has expired; do not repeat any "
                        "still-fresh read tool. Then complete "
                        "propose_major_incident and await_human_decision now. "
                        "A rejected proposal tool result is NOT a proposal. "
                        "Correct the reported Product error; never invent an ID or "
                        "wait after ok=false. If pending_proposal_id is supplied, "
                        "reuse that successful proposal and only request its human decision."
                    ),
                }
                if continuation_required
                else {
                    "type": "scenario2_operational_signal",
                    "product_event_id": product_event_id,
                    "payload": operational_fact,
                }
            )
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
            stream = self._run_events(
                user_id=tenant_id,
                session_id=run_id,
                new_message=message,
            )
        else:
            stream = self._run_events(
                user_id=tenant_id,
                session_id=run_id,
                invocation_id=correlation.invocation_id,
                new_message=None,
            )

        async with aclosing(stream):
            async for event in stream:
                if invocation_id is None and event.invocation_id:
                    invocation_id = event.invocation_id

                get_calls = getattr(event, "get_function_calls", None)
                for call in (get_calls() if callable(get_calls) else []):
                    logger.info(
                        "Scenario 2 tool call run_id=%s invocation_id=%s tool=%s call_id=%s",
                        run_id, invocation_id, call.name, call.id,
                    )
                    update_diagnostic_context(last_tool=call.name)
                    fingerprint = _read_call_fingerprint(call)
                    if fingerprint is None:
                        continue
                    read_call_counts[fingerprint] = read_call_counts.get(fingerprint, 0) + 1
                    if read_call_counts[fingerprint] > MAX_IDENTICAL_READ_CALLS_PER_INVOCATION:
                        raise RuntimeError(
                            "Scenario 2 repeated identical read-tool loop detected"
                        )

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

    @diagnostic_invocation
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
        async for event in self._run_events(
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
