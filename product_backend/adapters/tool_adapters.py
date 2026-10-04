"""ADK-facing adapter boundary for Scenario 1.

Phase 3A freezes signatures only. Concrete adapters that create evidence and
invoke domain validators are implemented/integrated in Phases 3B/3C.
"""

from __future__ import annotations

from typing import Protocol

from product_backend.contracts.tools import (
    GetDeviceRequest,
    GetDeviceResult,
    GetSiteHealthRequest,
    GetSiteHealthResult,
    ProposeFieldVisitRequest,
    ProposeFieldVisitResult,
    RunDiagnosticRequest,
    RunDiagnosticResult,
    SearchIncidentsRequest,
    SearchIncidentsResult,
    SearchKbRequest,
    SearchKbResult,
    ToolCallContext,
)


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
