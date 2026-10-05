"""Native ADK function wrappers for the six Scenario 1 Product tools."""

from __future__ import annotations

from typing import Any, Literal

from google.adk.tools import ToolContext

from product_backend.adapters.tool_adapters import Scenario1ToolAdapter
from product_backend.contracts.serialization import to_tool_payload
from product_backend.contracts.tools import (
    GetDeviceRequest,
    GetSiteHealthRequest,
    ProposeFieldVisitRequest,
    RunDiagnosticRequest,
    SearchIncidentsRequest,
    SearchKbRequest,
    ToolCallContext,
)
from product_backend.domain.enums import (
    DiagnosisCode,
    DiagnosticType,
    IncidentSearchScope,
)


def _product_context(tool_context: ToolContext) -> ToolCallContext:
    """Derive trusted Product context from the native ADK invocation context."""
    return ToolCallContext(
        tenant_id=tool_context.user_id,
        run_id=tool_context.session.id,
    )


def _payload(value: object) -> dict[str, Any]:
    data = to_tool_payload(value)
    if not isinstance(data, dict):
        raise TypeError("Product tool result must serialize to an object")
    return data


class Scenario1AdkTools:
    """Thin ADK-visible wrappers around the existing Product tool boundary."""

    def __init__(self, adapter: Scenario1ToolAdapter) -> None:
        self._adapter = adapter

    async def get_device(
        self,
        device_id: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read CMDB topology for a device and persist the returned evidence."""
        result = await self._adapter.get_device(
            _product_context(tool_context),
            GetDeviceRequest(device_id=device_id),
        )
        return _payload(result)

    async def get_site_health(
        self,
        site_id: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read current site health and persist the returned evidence."""
        result = await self._adapter.get_site_health(
            _product_context(tool_context),
            GetSiteHealthRequest(site_id=site_id),
        )
        return _payload(result)

    async def run_diagnostic(
        self,
        diagnostic_type: Literal["ACCESS_LINK"],
        target_id: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Run a permitted read-only diagnostic against a known target."""
        result = await self._adapter.run_diagnostic(
            _product_context(tool_context),
            RunDiagnosticRequest(
                diagnostic_type=DiagnosticType(diagnostic_type),
                target_id=target_id,
            ),
        )
        return _payload(result)

    async def search_incidents(
        self,
        scope: Literal["DEVICE", "SITE"],
        entity_id: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Search related incidents for a known device or site."""
        result = await self._adapter.search_incidents(
            _product_context(tool_context),
            SearchIncidentsRequest(
                scope=IncidentSearchScope(scope),
                entity_id=entity_id,
            ),
        )
        return _payload(result)

    async def search_kb(
        self,
        query: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Search the knowledge base and persist evidence for returned articles."""
        result = await self._adapter.search_kb(
            _product_context(tool_context),
            SearchKbRequest(query=query),
        )
        return _payload(result)

    async def propose_field_visit(
        self,
        incident_id: str,
        device_id: str,
        diagnosis: Literal["LOCAL_ACCESS_LINK_FAILURE"],
        evidence_ids: list[str],
        rationale: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Create a constrained pending field-visit proposal for human approval."""
        result = await self._adapter.propose_field_visit(
            _product_context(tool_context),
            ProposeFieldVisitRequest(
                incident_id=incident_id,
                device_id=device_id,
                diagnosis=DiagnosisCode(diagnosis),
                evidence_ids=tuple(evidence_ids),
                rationale=rationale,
            ),
        )
        return _payload(result)

    def functions(self) -> list[object]:
        """Return exactly the six native callables registered with ADK."""
        return [
            self.get_device,
            self.get_site_health,
            self.run_diagnostic,
            self.search_incidents,
            self.search_kb,
            self.propose_field_visit,
        ]
