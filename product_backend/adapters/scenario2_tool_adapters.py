"""Thin Product boundary for Scenario 2 model-visible tools."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Protocol, TypeVar

from product_backend.application.major_incident import MajorIncidentProposalService
from product_backend.application.scenario2_read_tools import Scenario2ReadToolService
from product_backend.contracts.scenario2_tools import (
    GetExternalDependencyStatusRequest,
    GetExternalDependencyStatusResult,
    GetLocalServiceHealthRequest,
    GetLocalServiceHealthResult,
    GetServiceDependenciesRequest,
    GetServiceDependenciesResult,
    ProposeMajorIncidentRequest,
    ProposeMajorIncidentResult,
    ProposeMajorIncidentSuccess,
    Scenario2ToolFailure,
    SearchMajorIncidentsRequest,
    SearchMajorIncidentsResult,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.errors import DomainError, ErrorCode


class Scenario2ToolAdapter(Protocol):
    async def get_local_service_health(
        self,
        context: ToolCallContext,
        request: GetLocalServiceHealthRequest,
    ) -> GetLocalServiceHealthResult: ...

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

    async def search_major_incidents(
        self,
        context: ToolCallContext,
        request: SearchMajorIncidentsRequest,
    ) -> SearchMajorIncidentsResult: ...

    async def propose_major_incident(
        self,
        context: ToolCallContext,
        request: ProposeMajorIncidentRequest,
    ) -> ProposeMajorIncidentResult: ...


def _unexpected_failure(reason: str) -> Scenario2ToolFailure:
    return Scenario2ToolFailure(
        ok=False,
        error=DomainError(
            code=ErrorCode.UPSTREAM_UNAVAILABLE,
            message="Scenario 2 tool operation could not be completed.",
            retryable=True,
            details=(("reason", reason),),
        ),
    )


T = TypeVar("T")
logger = logging.getLogger(__name__)


class DefaultScenario2ToolAdapter:
    def __init__(
        self,
        *,
        read_service: Scenario2ReadToolService,
        proposal_service: MajorIncidentProposalService,
    ) -> None:
        self._read_service = read_service
        self._proposal_service = proposal_service

    async def _invoke(
        self,
        *,
        operation: Callable[[], Awaitable[T]],
        unexpected_reason: str,
    ) -> T | Scenario2ToolFailure:
        try:
            return await operation()
        except Exception as error:
            logger.warning("Scenario 2 tool exception operation=%s error_type=%s",
                           unexpected_reason, type(error).__name__)
            return _unexpected_failure(unexpected_reason)

    async def get_local_service_health(
        self,
        context: ToolCallContext,
        request: GetLocalServiceHealthRequest,
    ) -> GetLocalServiceHealthResult:
        return await self._invoke(
            operation=lambda: self._read_service.get_local_service_health(
                context,
                request,
            ),
            unexpected_reason="get_local_service_health_unexpected_failure",
        )

    async def get_service_dependencies(
        self,
        context: ToolCallContext,
        request: GetServiceDependenciesRequest,
    ) -> GetServiceDependenciesResult:
        return await self._invoke(
            operation=lambda: self._read_service.get_service_dependencies(
                context,
                request,
            ),
            unexpected_reason="get_service_dependencies_unexpected_failure",
        )

    async def get_external_dependency_status(
        self,
        context: ToolCallContext,
        request: GetExternalDependencyStatusRequest,
    ) -> GetExternalDependencyStatusResult:
        return await self._invoke(
            operation=lambda: self._read_service.get_external_dependency_status(
                context,
                request,
            ),
            unexpected_reason="get_external_dependency_status_unexpected_failure",
        )

    async def search_major_incidents(
        self,
        context: ToolCallContext,
        request: SearchMajorIncidentsRequest,
    ) -> SearchMajorIncidentsResult:
        return await self._invoke(
            operation=lambda: self._read_service.search_major_incidents(
                context,
                request,
            ),
            unexpected_reason="search_major_incidents_unexpected_failure",
        )

    async def propose_major_incident(
        self,
        context: ToolCallContext,
        request: ProposeMajorIncidentRequest,
    ) -> ProposeMajorIncidentResult:
        async def operation() -> ProposeMajorIncidentResult:
            result = await self._proposal_service.create(context, request)
            logger.info(
                "Scenario 2 proposal result run_id=%s ok=%s error_code=%s reason=%s evidence_count=%s",
                context.run_id, result.ok,
                result.error.code if not result.ok else None,
                dict(result.error.details).get("reason") if not result.ok else None,
                len(request.evidence_ids),
            )
            if not result.ok:
                return Scenario2ToolFailure(ok=False, error=result.error)
            return ProposeMajorIncidentSuccess(ok=True, proposal=result.proposal)

        return await self._invoke(
            operation=operation,
            unexpected_reason="propose_major_incident_unexpected_failure",
        )


__all__ = [
    "DefaultScenario2ToolAdapter",
    "Scenario2ToolAdapter",
]
