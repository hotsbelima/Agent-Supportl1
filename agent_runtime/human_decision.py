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
            "Exact proposal_id returned by the successful prior "
            "propose_field_visit call. The Product proposal must already exist "
            "with status PENDING_APPROVAL before this wait point is requested."
        )
    ),
]


async def await_human_decision(
    proposal_id: ProposalId,
    tool_context: ToolContext,
) -> None:
    """Wait for the external Product Approve/Reject decision for a proposal.

    Call this exactly once immediately after propose_field_visit succeeds with
    PENDING_APPROVAL. The human decision is made through the Product API/UI,
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
    """Build the native ADK long-running wait tool used only by Phase 6C."""
    return LongRunningFunctionTool(await_human_decision)


__all__ = [
    "WAIT_FOR_HUMAN_DECISION_TOOL",
    "await_human_decision",
    "build_human_decision_wait_tool",
]
