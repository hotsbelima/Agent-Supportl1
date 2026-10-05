"""Native ADK function wrappers for the six Scenario 1 Product tools."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from google.adk.tools import ToolContext
from pydantic import Field

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


AffectedDeviceId = Annotated[
    str,
    Field(
        description=(
            "Exact reported_device_id of the affected terminal from the "
            "operational signal. Do not pass a peer_device_id, attachment_id, "
            "switch_id, port_id, site_id, or any inferred identifier."
        )
    ),
]

AccessLinkTargetId = Annotated[
    str,
    Field(
        description=(
            "For ACCESS_LINK only: the exact attachment_id returned by a "
            "successful prior get_device call for the affected reported device. "
            "Never pass device_id, site_id, expected_switch_id, switch_id, "
            "expected_port_id, or port_id."
        )
    ),
]

FieldVisitEvidenceIds = Annotated[
    list[str],
    Field(
        min_length=4,
        description=(
            "Evidence IDs copied exactly from successful prior Product tool "
            "results. The selected IDs must include at least one CMDB_SNAPSHOT "
            "from get_device, one SITE_HEALTH from get_site_health, one "
            "ACCESS_LINK_DIAGNOSTIC from run_diagnostic, and one approved "
            "KB_ARTICLE from search_kb. INCIDENT_SEARCH does not substitute for "
            "any required class. Never invent evidence IDs."
        ),
    ),
]


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
        device_id: AffectedDeviceId,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read CMDB topology for the affected reported device.

        Use the incident's exact reported_device_id from the operational signal.
        A successful result returns the trusted attachment_id that may later be
        used as run_diagnostic.target_id, plus persisted CMDB evidence.
        """
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
        """Read current health for a known incident site and persist evidence."""
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
        """Run the read-only access-link diagnostic for a CMDB attachment.

        For ACCESS_LINK, target_id must be the exact attachment_id produced by a
        successful prior get_device result for the affected reported terminal.
        A port ID, switch ID, terminal/device ID, or site ID is invalid.
        """
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
        """Search related incidents for a device or site already known in this run."""
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
        """Search approved KB guidance and persist evidence for returned articles."""
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
        """Create a PENDING_APPROVAL field-visit proposal after evidence is complete.

        Call only after successful prior tools have produced all four Product
        evidence classes required for this diagnosis: CMDB_SNAPSHOT, SITE_HEALTH,
        ACCESS_LINK_DIAGNOSTIC and an approved KB_ARTICLE. Copy their real
        evidence_id values into evidence_ids; INCIDENT_SEARCH is supplementary
        and cannot replace a required class.
        """
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
