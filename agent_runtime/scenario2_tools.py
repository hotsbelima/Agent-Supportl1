"""Native ADK wrappers for the five Scenario 2 Product tools."""

from __future__ import annotations

from typing import Annotated, Any

from google.adk.tools import ToolContext
from pydantic import Field

from product_backend.adapters.scenario2_tool_adapters import Scenario2ToolAdapter
from product_backend.contracts.scenario2_tools import (
    GetExternalDependencyStatusRequest,
    GetLocalServiceHealthRequest,
    GetServiceDependenciesRequest,
    ProposeMajorIncidentRequest,
    SearchMajorIncidentsRequest,
)
from product_backend.contracts.serialization import to_tool_payload
from product_backend.contracts.tools import ToolCallContext


AffectedSiteIds = Annotated[
    list[str],
    Field(
        min_length=2,
        description=(
            "At least two distinct affected site IDs copied from persisted "
            "operational signals in the current Scenario 2 run. Never invent sites."
        ),
    ),
]

MajorIncidentEvidenceIds = Annotated[
    list[str],
    Field(
        min_length=7,
        description=(
            "Evidence IDs copied exactly from successful Product facts/tool results. "
            "The set must support operational signals from every affected site, "
            "fresh local service health for every affected site, the service-to-"
            "dependency mapping, fresh external dependency status and a fresh "
            "matching Major Incident search. Never invent evidence IDs."
        ),
    ),
]


def _product_context(tool_context: ToolContext) -> ToolCallContext:
    return ToolCallContext(
        tenant_id=tool_context.user_id,
        run_id=tool_context.session.id,
    )


def _payload(value: object) -> dict[str, Any]:
    data = to_tool_payload(value)
    if not isinstance(data, dict):
        raise TypeError("Scenario 2 Product tool result must serialize to an object")
    return data


class Scenario2AdkTools:
    def __init__(self, adapter: Scenario2ToolAdapter) -> None:
        self._adapter = adapter

    async def get_local_service_health(
        self,
        site_id: str,
        service_key: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read current local network/payment-service health and persist Evidence."""
        result = await self._adapter.get_local_service_health(
            _product_context(tool_context),
            GetLocalServiceHealthRequest(
                site_id=site_id,
                service_key=service_key,
            ),
        )
        return _payload(result)

    async def get_service_dependencies(
        self,
        service_key: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Read provider-neutral dependency mappings for a known business service."""
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
        """Read current authoritative status for a dependency established by mapping."""
        result = await self._adapter.get_external_dependency_status(
            _product_context(tool_context),
            GetExternalDependencyStatusRequest(dependency_id=dependency_id),
        )
        return _payload(result)

    async def search_major_incidents(
        self,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Search for an equivalent open Major Incident before proposing a new one."""
        result = await self._adapter.search_major_incidents(
            _product_context(tool_context),
            SearchMajorIncidentsRequest(
                service_key=service_key,
                correlation_key=correlation_key,
                dependency_id=dependency_id,
            ),
        )
        return _payload(result)

    async def propose_major_incident(
        self,
        correlation_key: str,
        service_key: str,
        affected_site_ids: AffectedSiteIds,
        dependency_id: str,
        evidence_ids: MajorIncidentEvidenceIds,
        summary: str,
        rationale: str,
        tool_context: ToolContext,
    ) -> dict[str, Any]:
        """Create only a PENDING_APPROVAL Major Incident proposal.

        Call only after Product evidence establishes cross-site impact, healthy
        local service/network state, one common external dependency, degraded
        provider status and no equivalent open Major Incident.
        """
        result = await self._adapter.propose_major_incident(
            _product_context(tool_context),
            ProposeMajorIncidentRequest(
                correlation_key=correlation_key,
                service_key=service_key,
                affected_site_ids=tuple(affected_site_ids),
                dependency_id=dependency_id,
                evidence_ids=tuple(evidence_ids),
                summary=summary,
                rationale=rationale,
            ),
        )
        return _payload(result)

    def functions(self) -> list[object]:
        return [
            self.get_local_service_health,
            self.get_service_dependencies,
            self.get_external_dependency_status,
            self.search_major_incidents,
            self.propose_major_incident,
        ]


__all__ = [
    "Scenario2AdkTools",
]
