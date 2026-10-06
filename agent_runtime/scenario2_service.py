"""Native Google ADK invocation boundary for Phase 7C Scenario 2.

This module owns no Product facts or business state.  It only correlates a
durable Product event identity with the native ADK Session/Event history so an
outbox redelivery can resume or replay one invocation instead of starting a
second independent conversation turn.
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

from .scenario2_agent import build_scenario2_agent
from .sessions import ADK_APP_NAME, ensure_run_session


@dataclass(frozen=True, slots=True)
class Scenario2AgentInvocationResult:
    """Stable native-ADK point reached for a single Product event."""

    session_id: str
    invocation_id: str | None
    final_answer: str | None
    recoverable: bool


@dataclass(frozen=True, slots=True)
class _Scenario2EventCorrelation:
    invocation_id: str
    settled: bool
    final_answer: str | None


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
    for event in events:
        if getattr(event, "invocation_id", None) != invocation_id:
            continue
        is_final = getattr(event, "is_final_response", None)
        if callable(is_final) and is_final():
            settled = True
            text = _safe_event_text(event)
            if text:
                final_answer = text
        actions = getattr(event, "actions", None)
        if actions is not None and getattr(actions, "end_of_agent", False):
            settled = True

    return _Scenario2EventCorrelation(
        invocation_id=invocation_id,
        settled=settled,
        final_answer=final_answer,
    )


class Scenario2AgentRuntime:
    """One native ADK Runner; Session/Event persistence stays in Google ADK."""

    def __init__(self, *, session_service: DatabaseSessionService) -> None:
        app = App(
            name=ADK_APP_NAME,
            root_agent=build_scenario2_agent(),
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

    async def invoke_operational_signal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        product_event_id: str,
        operational_fact: dict[str, Any],
    ) -> Scenario2AgentInvocationResult:
        """Deliver one Product event to its native ADK invocation exactly once.

        The user message carries the persisted Product event identity.  If a
        worker crashes after ADK has persisted a final event but before it marks
        the outbox row delivered, the next delivery returns the existing native
        invocation.  If the native invocation is incomplete, ADK resumes that
        exact invocation with ``new_message=None``.
        """
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
            )

        invocation_id = (
            correlation.invocation_id if correlation is not None else None
        )
        final_answer: str | None = None
        recoverable = False

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
            recoverable=bool(recoverable and invocation_id),
        )


__all__ = [
    "Scenario2AgentInvocationResult",
    "Scenario2AgentRuntime",
    "_find_scenario2_event_correlation",
]
