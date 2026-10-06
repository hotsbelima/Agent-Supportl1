"""Native ADK wrappers for the seven Scenario 3 Product tools."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from google.adk.tools import ToolContext
from pydantic import Field

from product_backend.adapters.scenario3_tool_adapters import Scenario3ToolAdapter
from product_backend.contracts.scenario3_provider_tools import (
    GetExternalDependencyStatusRequest,
    GetServiceDependenciesRequest,
)
from product_backend.contracts.serialization import to_tool_payload
from product_backend.contracts.tools import (
    GetDeviceRequest,
    GetSiteHealthRequest,
    ProposeFieldVisitRequest,
    RunDiagnosticRequest,
    SearchKbRequest,
    ToolCallContext,
)
from product_backend.domain.enums import DiagnosisCode, DiagnosticType


AffectedDeviceId = Annotated[
    str,
    Field(
        description=(
            "Exact reported_device_id of the affected terminal from the "
            "operational signal. Never invent or substitute another identifier."
        )
    ),
]

AccessLinkTargetId = Annotated[
    str,
    Field(
        description=(
            "Exact attachment_id returned by the successful prior get_device "
            "result for the affected terminal."
        )
    ),
]

FieldVisitEvidenceIds = Annotated[
    list[str],
    Field(
        min_length=4,
        description=(
            "Evidence IDs copied exactly from successful prior Product tool "
            "results. They must include CMDB_SNAPSHOT, SITE_HEALTH, "
            "ACCESS_LINK_DIAGNOSTIC and an approved KB_ARTICLE."
        ),
    ),
]


def _product_context(tool_context: ToolContext) -> ToolCallContext:
    """Trusted tenant/run identity comes only from the native ADK context."""
    return ToolCallContext(
        tenant_id=tool_context.user_id,
        run_id=tool_context.session.id,
    )


def _payload(value: object) -> dict[str, Any]:
    data = to_tool_payload(value)
    if not isinstance(data, dict):
        raise TypeError("Scenario 3 Product tool result must serialize to an object")
    return data


class Scenario3AdkTools:
    """Exact Phase 8 Scenario 3 model-visible Product tool surface."""

    def __init__(self, adapter: Scenario3ToolAdapter) -> None:
        self._adapter = adapter

    async def get_service_dependencies(
        self,
        service_key: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read dependencies for the persisted Scenario 3 business service."""
        result = await self._adapter.get_service_dependencies(
            _product_context(tool_context),
            GetServiceDependenciesRequest(service_key=service_key),
        )
        return _payload(result)

    async def get_external_dependency_status(
        self,
        dependency_id: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read authoritative status for a dependency established by mapping."""
        result = await self._adapter.get_external_dependency_status(
            _product_context(tool_context),
            GetExternalDependencyStatusRequest(dependency_id=dependency_id),
        )
        return _payload(result)

    async def get_device(
        self,
        device_id: AffectedDeviceId,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read CMDB topology for the affected reported device."""
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
        """Read current local site health and persist Product Evidence."""
        result = await self._adapter.get_site_health(
            _product_context(tool_context),
            GetSiteHealthRequest(site_id=site_id),
        )
        return _payload(result)

    async def run_diagnostic(
        self,
        diagnostic_type: Literal["ACCESS_LINK"],
        target_id: AccessLinkTargetId,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Run the read-only access-link diagnostic for a CMDB attachment."""
        result = await self._adapter.run_diagnostic(
            _product_context(tool_context),
            RunDiagnosticRequest(
                diagnostic_type=DiagnosticType(diagnostic_type),
                target_id=target_id,
            ),
        )
        return _payload(result)

    async def search_kb(
        self,
        query: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Search approved KB guidance and persist returned Product Evidence."""
        result = await self._adapter.search_kb(
            _product_context(tool_context),
            SearchKbRequest(query=query),
        )
        return _payload(result)

    async def propose_field_visit(
        self,
        incident_id: str,
        device_id: AffectedDeviceId,
        diagnosis: Literal["LOCAL_ACCESS_LINK_FAILURE"],
        evidence_ids: FieldVisitEvidenceIds,
        rationale: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Create only a PENDING_APPROVAL Field Service proposal."""
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
        return [
            self.get_service_dependencies,
            self.get_external_dependency_status,
            self.get_device,
            self.get_site_health,
            self.run_diagnostic,
            self.search_kb,
            self.propose_field_visit,
        ]


__all__ = ["Scenario3AdkTools"]
