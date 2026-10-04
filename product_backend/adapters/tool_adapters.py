"""Thin model-facing adapters for the six Scenario 1 tool contracts.

Ownership, provider orchestration, TTL and evidence creation live in the
application/domain layer. This adapter delegates typed requests/results,
persists the Phase 4B tool-start audit boundary when configured, and prevents
unexpected exceptions from crossing the model boundary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypeVar

from product_backend.application.field_visit import FieldVisitProposalService
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.read_tools import Scenario1ReadToolService
from product_backend.contracts.serialization import to_tool_payload
from product_backend.contracts.tools import (
    GetDeviceRequest,
    GetDeviceResult,
    GetSiteHealthRequest,
    GetSiteHealthResult,
    ProposeFieldVisitRequest,
    ProposeFieldVisitResult,
    ProposeFieldVisitSuccess,
    RunDiagnosticRequest,
    RunDiagnosticResult,
    SearchIncidentsRequest,
    SearchIncidentsResult,
    SearchKbRequest,
    SearchKbResult,
    ToolCallContext,
    ToolFailure,
)
from product_backend.domain.errors import DomainError, ErrorCode


class Scenario1ToolAdapter(Protocol):
    async def get_device(
        self, context: ToolCallContext, request: GetDeviceRequest
    ) -> GetDeviceResult: ...

    async def get_site_health(
        self, context: ToolCallContext, request: GetSiteHealthRequest
    ) -> GetSiteHealthResult: ...

    async def run_diagnostic(
        self, context: ToolCallContext, request: RunDiagnosticRequest
    ) -> RunDiagnosticResult: ...

    async def search_incidents(
        self, context: ToolCallContext, request: SearchIncidentsRequest
    ) -> SearchIncidentsResult: ...

    async def search_kb(
        self, context: ToolCallContext, request: SearchKbRequest
    ) -> SearchKbResult: ...

    async def propose_field_visit(
        self, context: ToolCallContext, request: ProposeFieldVisitRequest
    ) -> ProposeFieldVisitResult: ...


def _unexpected_failure(reason: str) -> ToolFailure:
    return ToolFailure(
        ok=False,
        error=DomainError(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message="Tool operation could not be completed.",
            retryable=True,
            details=(("reason", reason),),
        ),
    )


T = TypeVar("T")


class DefaultScenario1ToolAdapter:
    """Thin typed boundary used by future Google ADK function wrappers."""

    def __init__(
        self,
        *,
        read_service: Scenario1ReadToolService,
        proposal_service: FieldVisitProposalService,
        lifecycle_service: ApplicationLifecycleService | None = None,
    ) -> None:
        self._read_service = read_service
        self._proposal_service = proposal_service
        self._lifecycle_service = lifecycle_service

    async def _record_started(
        self,
        *,
        tool_name: str,
        context: ToolCallContext,
        request: object,
    ) -> ToolFailure | None:
        if self._lifecycle_service is None:
            return None
        try:
            arguments = to_tool_payload(request)
            if not isinstance(arguments, dict):
                raise TypeError("tool request must serialize to an object")
            await self._lifecycle_service.record_tool_started(
                context,
                tool_name=tool_name,
                arguments=arguments,
            )
        except Exception:
            return _unexpected_failure("tool_audit_start_failed")
        return None

    async def _record_failed_finish(
        self,
        *,
        tool_name: str,
        context: ToolCallContext,
        result: ToolFailure,
    ) -> ToolFailure:
        if self._lifecycle_service is None:
            return result
        try:
            payload = to_tool_payload(result)
            if not isinstance(payload, dict):
                raise TypeError("tool result must serialize to an object")
            await self._lifecycle_service.record_tool_finished(
                context,
                tool_name=tool_name,
                result=payload,
            )
            return result
        except Exception:
            return _unexpected_failure("tool_audit_finish_failed")

    async def _invoke(
        self,
        *,
        tool_name: str,
        context: ToolCallContext,
        request: object,
        operation: Callable[[], Awaitable[T]],
        unexpected_reason: str,
    ) -> T | ToolFailure:
        start_failure = await self._record_started(
            tool_name=tool_name,
            context=context,
            request=request,
        )
        if start_failure is not None:
            return start_failure

        try:
            result = await operation()
        except Exception:
            failure = _unexpected_failure(unexpected_reason)
            return await self._record_failed_finish(
                tool_name=tool_name,
                context=context,
                result=failure,
            )

        if getattr(result, "ok", None) is False:
            return await self._record_failed_finish(
                tool_name=tool_name,
                context=context,
                result=result,
            )
        return result

    async def get_device(
        self,
        context: ToolCallContext,
        request: GetDeviceRequest,
    ) -> GetDeviceResult:
        return await self._invoke(
            tool_name="get_device",
            context=context,
            request=request,
            operation=lambda: self._read_service.get_device(context, request),
            unexpected_reason="get_device_unexpected_failure",
        )

    async def get_site_health(
        self,
        context: ToolCallContext,
        request: GetSiteHealthRequest,
    ) -> GetSiteHealthResult:
        return await self._invoke(
            tool_name="get_site_health",
            context=context,
            request=request,
            operation=lambda: self._read_service.get_site_health(context, request),
            unexpected_reason="get_site_health_unexpected_failure",
        )

    async def run_diagnostic(
        self,
        context: ToolCallContext,
        request: RunDiagnosticRequest,
    ) -> RunDiagnosticResult:
        return await self._invoke(
            tool_name="run_diagnostic",
            context=context,
            request=request,
            operation=lambda: self._read_service.run_diagnostic(context, request),
            unexpected_reason="run_diagnostic_unexpected_failure",
        )

    async def search_incidents(
        self,
        context: ToolCallContext,
        request: SearchIncidentsRequest,
    ) -> SearchIncidentsResult:
        return await self._invoke(
            tool_name="search_incidents",
            context=context,
            request=request,
            operation=lambda: self._read_service.search_incidents(context, request),
            unexpected_reason="search_incidents_unexpected_failure",
        )

    async def search_kb(
        self,
        context: ToolCallContext,
        request: SearchKbRequest,
    ) -> SearchKbResult:
        return await self._invoke(
            tool_name="search_kb",
            context=context,
            request=request,
            operation=lambda: self._read_service.search_kb(context, request),
            unexpected_reason="search_kb_unexpected_failure",
        )

    async def propose_field_visit(
        self,
        context: ToolCallContext,
        request: ProposeFieldVisitRequest,
    ) -> ProposeFieldVisitResult:
        async def operation() -> ProposeFieldVisitResult:
            result = await self._proposal_service.create(context, request)
            if not result.ok:
                return ToolFailure(ok=False, error=result.error)
            return ProposeFieldVisitSuccess(ok=True, proposal=result.proposal)

        return await self._invoke(
            tool_name="propose_field_visit",
            context=context,
            request=request,
            operation=operation,
            unexpected_reason="proposal_service_unexpected_failure",
        )


__all__ = [
    "DefaultScenario1ToolAdapter",
    "Scenario1ToolAdapter",
]
