"""Product retry policy plugged into ADK's native retry/reflection lifecycle."""

from __future__ import annotations

from typing import Any

from google.adk.plugins import ReflectAndRetryToolPlugin
from google.adk.tools import BaseTool, ToolContext


class ProductRetryableToolPlugin(ReflectAndRetryToolPlugin):
    """Retry/reflection only for Product failures explicitly marked retryable."""

    async def extract_error_from_result(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: Any,
    ) -> dict[str, Any] | None:
        del tool, tool_args, tool_context

        if not isinstance(result, dict) or result.get("ok") is not False:
            return None

        error = result.get("error")
        if not isinstance(error, dict) or error.get("retryable") is not True:
            return None

        return {
            "code": str(error.get("code", "RETRYABLE_TOOL_FAILURE")),
            "message": str(error.get("message", "Retryable Product tool failure.")),
            "retryable": True,
            "details": error.get("details", {}),
        }
