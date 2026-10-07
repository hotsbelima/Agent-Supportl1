"""Application service for Scenario 2 evidence-producing read tools."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from product_backend.application.lifecycle import append_uow_event
from product_backend.contracts.events import ApplicationEventType
from product_backend.contracts.scenario2_tools import (
    GetExternalDependencyStatusRequest,
    GetExternalDependencyStatusResult,
    GetExternalDependencyStatusSuccess,
    GetLocalServiceHealthRequest,
    GetLocalServiceHealthResult,
    GetLocalServiceHealthSuccess,
    GetServiceDependenciesRequest,
    GetServiceDependenciesResult,
    GetServiceDependenciesSuccess,
    Scenario2ToolFailure,
    SearchMajorIncidentsRequest,
    SearchMajorIncidentsResult,
    SearchMajorIncidentsSuccess,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import EvidenceSourceType, RunStatus
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.domain.models import Evidence
from product_backend.domain.scenario2 import ServiceDependencyMappingSnapshot
from product_backend.ports.scenario2 import Scenario2ToolReadUnitOfWork
from product_backend.ports.scenario2_sources import (
    ExternalDependencyStatusPort,
    LocalServiceHealthPort,
    MajorIncidentDirectoryPort,
    ServiceDependencyPort,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
ReadUowFactory = Callable[[], Scenario2ToolReadUnitOfWork]


@dataclass(frozen=True, slots=True)
class Scenario2EvidenceTtlPolicy:
    local_service_health: timedelta
    external_dependency_status: timedelta
    major_incident_search: timedelta

    def __post_init__(self) -> None:
        for name, value in (
            ("local_service_health", self.local_service_health),
            ("external_dependency_status", self.external_dependency_status),
            ("major_incident_search", self.major_incident_search),
        ):
            if value <= timedelta(0):
                raise ValueError(f"{name} TTL must be positive")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix.upper()}-{uuid4().hex}"


def _failure(
    code: ErrorCode,
    message: str,
    reason: str,
    *,
    retryable: bool = False,
) -> Scenario2ToolFailure:
    return Scenario2ToolFailure(
        ok=False,
        error=DomainError(
            code=code,
            message=message,
            retryable=retryable,
            details=(("reason", reason),),
        ),
    )


async def _record_tool_started(
    uow: Scenario2ToolReadUnitOfWork,
    *,
    context: ToolCallContext,
    tool_name: str,
) -> None:
    await append_uow_event(
        uow,
        context=context,
        event_type=ApplicationEventType.TOOL_STARTED,
        payload={"tool_name": tool_name},
    )
    await uow.commit()


async def _record_observation(
    uow: Scenario2ToolReadUnitOfWork,
    *,
    context: ToolCallContext,
    evidence: Evidence,
) -> None:
    await append_uow_event(
        uow,
        context=context,
        event_type=ApplicationEventType.OBSERVATION_RECORDED,
        payload={
            "evidence_id": evidence.evidence_id,
            "source_type": evidence.source_type.value,
            "captured_at": evidence.captured_at.isoformat(),
            "entity_ids": list(evidence.entity_ids),
            "expires_at": (
                evidence.expires_at.isoformat()
                if evidence.expires_at is not None
                else None
            ),
        },
    )


class Scenario2ReadToolService:
    """Own context checks, provider calls, TTL and immutable Evidence creation."""

    def __init__(
        self,
        *,
        read_uow_factory: ReadUowFactory,
        local_health: LocalServiceHealthPort,
        dependency_mapping: ServiceDependencyPort,
        dependency_status: ExternalDependencyStatusPort,
        major_incident_directory: MajorIncidentDirectoryPort,
        ttl_policy: Scenario2EvidenceTtlPolicy,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._read_uow_factory = read_uow_factory
        self._local_health = local_health
        self._dependency_mapping = dependency_mapping
        self._dependency_status = dependency_status
        self._major_incident_directory = major_incident_directory
        self._ttl = ttl_policy
        self._clock = clock
        self._id_factory = id_factory

    async def _require_active_run(
        self,
        uow: Scenario2ToolReadUnitOfWork,
        context: ToolCallContext,
    ) -> Scenario2ToolFailure | None:
        run = await uow.runs.get(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
        )
        if run is None or run.scenario_id != "scenario-2":
            return _failure(
                ErrorCode.CONTEXT_MISMATCH,
                "Scenario 2 run context is not valid.",
                "run_not_found_or_wrong_scenario",
            )
        if run.status is not RunStatus.ACTIVE:
            return _failure(
                ErrorCode.INVALID_STATE_TRANSITION,
                "Scenario 2 read tools are not available in the current run state.",
                "run_not_active",
            )
        return None

    async def _service_is_known(
        self,
        uow: Scenario2ToolReadUnitOfWork,
        context: ToolCallContext,
        service_key: str,
    ) -> bool:
        return any(
            item.service_key == service_key
            for item in await uow.signals.list_for_run(
                tenant_id=context.tenant_id,
                run_id=context.run_id,
            )
        )

    async def get_local_service_health(
        self,
        context: ToolCallContext,
        request: GetLocalServiceHealthRequest,
    ) -> GetLocalServiceHealthResult:
        if not request.site_id.strip() or not request.service_key.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Site and service identifiers are required.",
                "missing_site_or_service",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error is not None:
                    return state_error
                incident = await uow.service_incidents.get_for_site_service(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    site_id=request.site_id,
                    service_key=request.service_key,
                )
                if incident is None:
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Site/service pair is not known in the current run.",
                        "unknown_run_site_service",
                    )
                await _record_tool_started(uow, context=context, tool_name="get_local_service_health")
                snapshot = await self._local_health.get_local_service_health(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    site_id=request.site_id,
                    service_key=request.service_key,
                )
                if snapshot is None:
                    return _failure(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "Local service health is unavailable.",
                        "local_service_health_unavailable",
                        retryable=True,
                    )
                if (
                    snapshot.site_id != request.site_id
                    or snapshot.service_key != request.service_key
                ):
                    return _failure(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "Local service health returned mismatched context.",
                        "local_service_health_mismatch",
                        retryable=True,
                    )
                now = self._clock()
                evidence = Evidence(
                    evidence_id=self._id_factory("evidence"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    source_type=EvidenceSourceType.LOCAL_SERVICE_HEALTH,
                    captured_at=now,
                    entity_ids=(snapshot.site_id, snapshot.service_key),
                    payload=snapshot,
                    expires_at=now + self._ttl.local_service_health,
                )
                await uow.evidence.add(evidence)
                await _record_observation(uow, context=context, evidence=evidence)
                await uow.commit()
                return GetLocalServiceHealthSuccess(
                    ok=True,
                    site_id=request.site_id,
                    service_key=request.service_key,
                    health=snapshot,
                    evidence=evidence,
                )
        except Exception:
            return _failure(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Local service health could not be read.",
                "get_local_service_health_failed",
                retryable=True,
            )

    async def get_service_dependencies(
        self,
        context: ToolCallContext,
        request: GetServiceDependenciesRequest,
    ) -> GetServiceDependenciesResult:
        if not request.service_key.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Service identifier is required.",
                "missing_service_key",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error is not None:
                    return state_error
                if not await self._service_is_known(uow, context, request.service_key):
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Service is not known in the current run.",
                        "unknown_run_service",
                    )
                await _record_tool_started(uow, context=context, tool_name="get_service_dependencies")
                mappings = await self._dependency_mapping.get_service_dependencies(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    service_key=request.service_key,
                )
                evidence_items: list[Evidence] = []
                now = self._clock()
                for mapping in mappings:
                    if mapping.service_key != request.service_key:
                        return _failure(
                            ErrorCode.UPSTREAM_UNAVAILABLE,
                            "Dependency mapping returned mismatched service context.",
                            "dependency_mapping_mismatch",
                            retryable=True,
                        )
                    evidence = Evidence(
                        evidence_id=self._id_factory("evidence"),
                        tenant_id=context.tenant_id,
                        run_id=context.run_id,
                        source_type=EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING,
                        captured_at=now,
                        entity_ids=(mapping.service_key, mapping.dependency_id),
                        payload=mapping,
                    )
                    await uow.evidence.add(evidence)
                    await _record_observation(uow, context=context, evidence=evidence)
                    evidence_items.append(evidence)
                await uow.commit()
                return GetServiceDependenciesSuccess(
                    ok=True,
                    service_key=request.service_key,
                    mappings=tuple(mappings),
                    evidence=tuple(evidence_items),
                )
        except Exception:
            return _failure(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Service dependency mapping could not be read.",
                "get_service_dependencies_failed",
                retryable=True,
            )

    async def _known_dependency_mapping(
        self,
        uow: Scenario2ToolReadUnitOfWork,
        context: ToolCallContext,
        *,
        dependency_id: str,
        service_key: str | None = None,
    ) -> ServiceDependencyMappingSnapshot | None:
        evidence = await uow.evidence.find_by_entity_id(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            entity_id=dependency_id,
        )
        matches = [
            item.payload
            for item in evidence
            if (
                item.source_type is EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING
                and isinstance(item.payload, ServiceDependencyMappingSnapshot)
                and item.payload.dependency_id == dependency_id
                and (
                    service_key is None
                    or item.payload.service_key == service_key
                )
            )
        ]
        if not matches:
            return None
        return matches[-1]

    async def get_external_dependency_status(
        self,
        context: ToolCallContext,
        request: GetExternalDependencyStatusRequest,
    ) -> GetExternalDependencyStatusResult:
        if not request.dependency_id.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Dependency identifier is required.",
                "missing_dependency_id",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error is not None:
                    return state_error
                mapping = await self._known_dependency_mapping(
                    uow,
                    context,
                    dependency_id=request.dependency_id,
                )
                if mapping is None:
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Dependency is not established by Product evidence in this run.",
                        "unknown_run_dependency",
                    )
                await _record_tool_started(uow, context=context, tool_name="get_external_dependency_status")
                snapshot = (
                    await self._dependency_status.get_external_dependency_status(
                        tenant_id=context.tenant_id,
                        run_id=context.run_id,
                        dependency_id=request.dependency_id,
                    )
                )
                if snapshot is None:
                    return _failure(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "External dependency status is unavailable.",
                        "external_dependency_status_unavailable",
                        retryable=True,
                    )
                if (
                    snapshot.dependency_id != request.dependency_id
                    or snapshot.dependency_name != mapping.dependency_name
                ):
                    return _failure(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "External dependency status returned mismatched identity.",
                        "external_dependency_status_mismatch",
                        retryable=True,
                    )
                now = self._clock()
                evidence = Evidence(
                    evidence_id=self._id_factory("evidence"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    source_type=EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS,
                    captured_at=now,
                    entity_ids=(snapshot.dependency_id,),
                    payload=snapshot,
                    expires_at=now + self._ttl.external_dependency_status,
                )
                await uow.evidence.add(evidence)
                await _record_observation(uow, context=context, evidence=evidence)
                await uow.commit()
                return GetExternalDependencyStatusSuccess(
                    ok=True,
                    dependency_id=request.dependency_id,
                    status=snapshot,
                    evidence=evidence,
                )
        except Exception:
            return _failure(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "External dependency status could not be read.",
                "get_external_dependency_status_failed",
                retryable=True,
            )

    async def search_major_incidents(
        self,
        context: ToolCallContext,
        request: SearchMajorIncidentsRequest,
    ) -> SearchMajorIncidentsResult:
        if (
            not request.service_key.strip()
            or not request.correlation_key.strip()
            or not request.dependency_id.strip()
        ):
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Service, correlation and dependency identifiers are required.",
                "missing_major_incident_search_key",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error is not None:
                    return state_error
                signals = await uow.signals.list_for_run(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                )
                correlation_known = any(
                    item.service_key == request.service_key
                    and item.symptom_key == request.correlation_key
                    for item in signals
                )
                mapping = await self._known_dependency_mapping(
                    uow,
                    context,
                    dependency_id=request.dependency_id,
                    service_key=request.service_key,
                )
                if not correlation_known or mapping is None:
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Major Incident search key is not grounded in current run facts.",
                        "unestablished_major_incident_search_key",
                    )
                await _record_tool_started(uow, context=context, tool_name="search_major_incidents")
                snapshot = await self._major_incident_directory.search_major_incidents(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    service_key=request.service_key,
                    correlation_key=request.correlation_key,
                    dependency_id=request.dependency_id,
                )
                if (
                    snapshot.service_key != request.service_key
                    or snapshot.correlation_key != request.correlation_key
                    or snapshot.dependency_id != request.dependency_id
                ):
                    return _failure(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "Major Incident search returned mismatched context.",
                        "major_incident_search_mismatch",
                        retryable=True,
                    )
                now = self._clock()
                evidence = Evidence(
                    evidence_id=self._id_factory("evidence"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    source_type=EvidenceSourceType.MAJOR_INCIDENT_SEARCH,
                    captured_at=now,
                    entity_ids=(
                        snapshot.service_key,
                        snapshot.correlation_key,
                        snapshot.dependency_id,
                        *snapshot.open_major_incident_ids,
                    ),
                    payload=snapshot,
                    expires_at=now + self._ttl.major_incident_search,
                )
                await uow.evidence.add(evidence)
                await _record_observation(uow, context=context, evidence=evidence)
                await uow.commit()
                return SearchMajorIncidentsSuccess(
                    ok=True,
                    service_key=request.service_key,
                    correlation_key=request.correlation_key,
                    dependency_id=request.dependency_id,
                    snapshot=snapshot,
                    evidence=evidence,
                )
        except Exception:
            return _failure(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Major Incident directory could not be searched.",
                "search_major_incidents_failed",
                retryable=True,
            )


__all__ = [
    "Scenario2EvidenceTtlPolicy",
    "Scenario2ReadToolService",
]
