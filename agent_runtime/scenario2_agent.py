"""Native ADK agent definition for Phase 7C Scenario 2 event continuity."""

from __future__ import annotations

from google.adk.agents import LlmAgent

from .agent import MODEL


SCENARIO2_AGENT_NAME = "scenario2_operational_correlation_agent"

# Phase 7C deliberately has no model-visible tools or mutation path.  The
# Product event is a wake-up fact only; Product PostgreSQL remains authoritative
# and the later Phase 7D tool surface will be added on top of this same native
# session lifecycle.
SCENARIO2_AGENT_INSTRUCTION = """You are the Scenario 2 operational-correlation agent.

Each user message represents exactly one newly persisted operational fact for
the same Product run. Treat the current message and prior conversation as
signals for investigation only. Do not create a Major Incident, work order,
device diagnosis, or any other Product business record in this phase.

Do not infer a cross-site outage from repeated signals at one site. A signal at
an independent site may justify considering a shared dependency, but it is not
proof. Product facts and typed tool evidence remain the source for later
correlation decisions.

Respond with a concise acknowledgement of the fact and any bounded next
investigation question. Do not invent identifiers, source data, or outcomes.
"""


def build_scenario2_agent() -> LlmAgent:
    """Build the narrow native ADK agent used only for 7C event continuity."""
    return LlmAgent(
        name=SCENARIO2_AGENT_NAME,
        model=MODEL,
        instruction=SCENARIO2_AGENT_INSTRUCTION,
        tools=[],
    )


__all__ = [
    "SCENARIO2_AGENT_INSTRUCTION",
    "SCENARIO2_AGENT_NAME",
    "build_scenario2_agent",
]
