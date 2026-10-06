"""Thin Product boundary for the Scenario 3 model-visible tool surface.

Scenario 3 deliberately composes the narrow provider-read service from Phase
8C1 with the already validated device/Field-Service Product boundary.  It does
not expose Scenario 1 incident search or any Scenario 2 Major Incident tool.
"""

from __future__ import annotations

from typing import Protocol

from product_backend.adapters.tool_adapters import Scenario1ToolAdapter
from product_backend.application.scenario3_provider_reads import (
    Scenario3ProviderReadService,
)
from product_backend.contracts.scenario3_provider_tools import (
    GetExternalDependencyStatusRequest,
    GetExternalDependencyStatusResult,
    GetServiceDependenciesRequest,
    GetServiceDependenciesResult,
)
from product_backend.contracts.tools import (
    GetDeviceRequest,
    GetDeviceResult,
    GetSiteHealthRequest,
    GetSiteHealthResult,
    ProposeFieldVisitRequest,
    ProposeFieldVisitResult,
    RunDiagnosticRequest,
    RunDiagnosticResult,
    SearchKbRequest,
    SearchKbResult,
    ToolCallContext,
)


class Scenario3ToolAdapter(Protocol):
    async def get_service_dependencies(
        self,
        context: ToolCallContext,
        request: GetServiceDependenciesRequest,
    ) -> GetServiceDependenciesResult: ...

    async def get_external_dependency_status(
        self,
        context: ToolCallContext,
        request: GetExternalDependencyStatusRequest,
    ) -> GetExternalDependencyStatusResult: ...

    async def get_device(
        self,
        context: ToolCallContext,
        request: GetDeviceRequest,
    ) -> GetDeviceResult: ...

    async def get_site_health(
        self,
        context: ToolCallContext,
        request: GetSiteHealthRequest,
    ) -> GetSiteHealthResult: ...

    async def run_diagnostic(
        self,
        context: ToolCallContext,
        request: RunDiagnosticRequest,
    ) -> RunDiagnosticResult: ...

    async def search_kb(
        self,
        context: ToolCallContext,
        request: SearchKbRequest,
    ) -> SearchKbResult: ...

    async def propose_field_visit(
        self,
        context: ToolCallContext,
        request: ProposeFieldVisitRequest,
    ) -> ProposeFieldVisitResult: ...


class DefaultScenario3ToolAdapter:
    """Compose existing Product ownership boundaries without cloning them."""

    def __init__(
        self,
        *,
        provider_read_service: Scenario3ProviderReadService,
        local_adapter: Scenario1ToolAdapter,
    ) -> None:
        self._provider_read_service = provider_read_service
        self._local_adapter = local_adapter

    async def get_service_dependencies(
        self,
        context: ToolCallContext,
        request: GetServiceDependenciesRequest,
    ) -> GetServiceDependenciesResult:
        return await self._provider_read_service.get_service_dependencies(
            context,
            request,
        )

    async def get_external_dependency_status(
        self,
        context: ToolCallContext,
        request: GetExternalDependencyStatusRequest,
    ) -> GetExternalDependencyStatusResult:
        return await self._provider_read_service.get_external_dependency_status(
            context,
            request,
        )

    async def get_device(
        self,
        context: ToolCallContext,
        request: GetDeviceRequest,
    ) -> GetDeviceResult:
        return await self._local_adapter.get_device(context, request)

    async def get_site_health(
        self,
        context: ToolCallContext,
        request: GetSiteHealthRequest,
    ) -> GetSiteHealthResult:
        return await self._local_adapter.get_site_health(context, request)

    async def run_diagnostic(
        self,
        context: ToolCallContext,
        request: RunDiagnosticRequest,
    ) -> RunDiagnosticResult:
        return await self._local_adapter.run_diagnostic(context, request)

    async def search_kb(
        self,
        context: ToolCallContext,
        request: SearchKbRequest,
    ) -> SearchKbResult:
        return await self._local_adapter.search_kb(context, request)

    async def propose_field_visit(
        self,
        context: ToolCallContext,
        request: ProposeFieldVisitRequest,
    ) -> ProposeFieldVisitResult:
        return await self._local_adapter.propose_field_visit(context, request)


__all__ = [
    "DefaultScenario3ToolAdapter",
    "Scenario3ToolAdapter",
]
