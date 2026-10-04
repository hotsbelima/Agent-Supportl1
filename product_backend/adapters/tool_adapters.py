"""Thin model-facing adapters for the six Scenario 1 tool contracts.

Ownership, provider orchestration, TTL and evidence creation live in the
application/domain layer. This adapter only delegates typed requests/results
and prevents unexpected exceptions from crossing the model boundary.
"""

from __future__ import annotations

from typing import Protocol

from product_backend.application.field_visit import FieldVisitProposalService
from product_backend.application.read_tools import Scenario1ReadToolService
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


class DefaultScenario1ToolAdapter:
    """Thin typed boundary used by future Google ADK function wrappers."""

    def __init__(
        self,
        *,
        read_service: Scenario1ReadToolService,
        proposal_service: FieldVisitProposalService,
    ) -> None:
        self._read_service = read_service
        self._proposal_service = proposal_service

    async def get_device(
        self,
        context: ToolCallContext,
        request: GetDeviceRequest,
    ) -> GetDeviceResult:
        try:
            return await self._read_service.get_device(context, request)
        except Exception:
            return _unexpected_failure("get_device_unexpected_failure")

    async def get_site_health(
        self,
        context: ToolCallContext,
        request: GetSiteHealthRequest,
    ) -> GetSiteHealthResult:
        try:
            return await self._read_service.get_site_health(context, request)
        except Exception:
            return _unexpected_failure("get_site_health_unexpected_failure")

    async def run_diagnostic(
        self,
        context: ToolCallContext,
        request: RunDiagnosticRequest,
    ) -> RunDiagnosticResult:
        try:
            return await self._read_service.run_diagnostic(context, request)
        except Exception:
            return _unexpected_failure("run_diagnostic_unexpected_failure")

    async def search_incidents(
        self,
        context: ToolCallContext,
        request: SearchIncidentsRequest,
    ) -> SearchIncidentsResult:
        try:
            return await self._read_service.search_incidents(context, request)
        except Exception:
            return _unexpected_failure("search_incidents_unexpected_failure")

    async def search_kb(
        self,
        context: ToolCallContext,
        request: SearchKbRequest,
    ) -> SearchKbResult:
        try:
            return await self._read_service.search_kb(context, request)
        except Exception:
            return _unexpected_failure("search_kb_unexpected_failure")

    async def propose_field_visit(
        self,
        context: ToolCallContext,
        request: ProposeFieldVisitRequest,
    ) -> ProposeFieldVisitResult:
        try:
            result = await self._proposal_service.create(context, request)
        except Exception:
            return _unexpected_failure("proposal_service_unexpected_failure")
        if not result.ok:
            return ToolFailure(ok=False, error=result.error)
        return ProposeFieldVisitSuccess(ok=True, proposal=result.proposal)


__all__ = [
    "DefaultScenario1ToolAdapter",
    "Scenario1ToolAdapter",
]
