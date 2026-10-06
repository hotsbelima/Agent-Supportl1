"""Native ADK long-running wait point for Phase 6C human decisions."""

from __future__ import annotations

from typing import Annotated

from google.adk.tools import LongRunningFunctionTool, ToolContext
from pydantic import Field


WAIT_FOR_HUMAN_DECISION_TOOL = "await_human_decision"


ProposalId = Annotated[
    str,
    Field(
        description=(
            "Exact proposal_id returned by the successful prior Product proposal "
            "tool (for example propose_field_visit or propose_major_incident). "
            "The Product proposal must already exist with status PENDING_APPROVAL "
            "before this wait point is requested."
        )
    ),
]


async def await_human_decision(
    proposal_id: ProposalId,
    tool_context: ToolContext,
) -> None:
    """Wait for the external Product Approve/Reject decision for a proposal.

    Call this exactly once immediately after the active scenario's Product
    proposal tool succeeds with PENDING_APPROVAL. The human decision is made
    through the Product API/UI,
    not by the model. ADK pauses this invocation at the long-running function
    call and later resumes the same invocation when the Product decision is
    supplied as the matching FunctionResponse.
    """
    # With native ADK resumability a LongRunningFunctionTool pauses on its
    # function-call event before this callable executes. Returning None keeps
    # the callable semantically safe if ADK ever invokes it outside that path.
    del proposal_id, tool_context
    return None


def build_human_decision_wait_tool() -> LongRunningFunctionTool:
    """Build the shared native ADK long-running Product approval wait tool."""
    return LongRunningFunctionTool(await_human_decision)


__all__ = [
    "WAIT_FOR_HUMAN_DECISION_TOOL",
    "await_human_decision",
    "build_human_decision_wait_tool",
]
