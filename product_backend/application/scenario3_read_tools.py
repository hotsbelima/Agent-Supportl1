"""Scenario 3 provider-domain Product read service.

This service intentionally does not reuse Scenario2ReadToolService: Scenario 2
is live-validated and bound to Scenario 2 OperationalSignal persistence.
Scenario 3 grounds provider reads in the same run's persisted EXTERNAL_SIGNAL
and in same-run Product Evidence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from product_backend.application.lifecycle import append_uow_event
from product_backend.contracts.events import ApplicationEventType
from product_backend.contracts.scenario2_tools import (
    GetExternalDependencyStatusRequest,
    GetExternalDependencyStatusResult,
    GetExternalDependencyStatusSuccess,
    GetServiceDependenciesRequest,
    GetServiceDependenciesResult,
    GetServiceDependenciesSuccess,
    Scenario2ToolFailure,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import EvidenceSourceType, RunStatus
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.domain.models import Evidence
from product_backend.domain.scenario2 import ServiceDependencyMappingSnapshot
from product_backend.ports.events import ApplicationEventRepository
from product_backend.ports.repositories import EvidenceRepository, RunRepository
from product_backend.ports.scenario2_sources import (
    ExternalDependencyStatusPort,
    ServiceDependencyPort,
)


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]


class Scenario3ProviderReadUnitOfWork(Protocol):
    runs: RunRepository
    evidence: EvidenceRepository
    events: ApplicationEventRepository

    async def __aenter__(self) -> "Scenario3ProviderReadUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


ReadUowFactory = Callable[[], Scenario3ProviderReadUnitOfWork]


@dataclass(frozen=True, slots=True)
class Scenario3EvidenceTtlPolicy:
    external_dependency_status: timedelta

    def __post_init__(self) -> None:
        if self.external_dependency_status <= timedelta(0):
            raise ValueError("external_dependency_status TTL must be positive")


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
    # Provider request/result contracts are shared with the already existing
    # provider-neutral Scenario 2 contracts. Only the application service is
    # Scenario 3-specific.
    return Scenario2ToolFailure(
        ok=False,
        error=DomainError(
            code=code,
            message=message,
            retryable=retryable,
            details=(("reason", reason),),
        ),
    )


async def _record_observation(
    uow: Scenario3ProviderReadUnitOfWork,
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


class Scenario3ProviderReadService:
    """Ground provider reads in persisted Scenario 3 Product facts/Evidence."""

    def __init__(
        self,
        *,
        read_uow_factory: ReadUowFactory,
        dependency_mapping: ServiceDependencyPort,
        dependency_status: ExternalDependencyStatusPort,
        ttl_policy: Scenario3EvidenceTtlPolicy,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._read_uow_factory = read_uow_factory
        self._dependency_mapping = dependency_mapping
        self._dependency_status = dependency_status
        self._ttl = ttl_policy
        self._clock = clock
        self._id_factory = id_factory

    async def _require_active_run(
        self,
        uow: Scenario3ProviderReadUnitOfWork,
        context: ToolCallContext,
    ) -> Scenario2ToolFailure | None:
        run = await uow.runs.get(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
        )
        if run is None or run.scenario_id != "scenario-3":
            return _failure(
                ErrorCode.CONTEXT_MISMATCH,
                "Scenario 3 run context is not valid.",
                "run_not_found_or_wrong_scenario",
            )
        if run.status is not RunStatus.ACTIVE:
            return _failure(
                ErrorCode.INVALID_STATE_TRANSITION,
                "Scenario 3 provider reads are not available in the current run state.",
                "run_not_active",
            )
        return None

    async def _initial_service_context(
        self,
        uow: Scenario3ProviderReadUnitOfWork,
        context: ToolCallContext,
    ) -> tuple[str, str] | None:
        events = await uow.events.list_after(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            after_seq=0,
            limit=100,
        )
        for event in events:
            if event.event_type is not ApplicationEventType.EXTERNAL_SIGNAL:
                continue
            details = event.payload.get("details")
            if not isinstance(details, dict):
                continue
            service_key = details.get("service_key")
            symptom_key = details.get("symptom_key")
            if (
                isinstance(service_key, str)
                and service_key
                and isinstance(symptom_key, str)
                and symptom_key
            ):
                return service_key, symptom_key
        return None

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
                initial_context = await self._initial_service_context(uow, context)
                if (
                    initial_context is None
                    or request.service_key != initial_context[0]
                ):
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Service is not established by the current run's initial Product signal.",
                        "unknown_run_service",
                    )

                mappings = await self._dependency_mapping.get_service_dependencies(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    service_key=request.service_key,
                )
                now = self._clock()
                evidence_items: list[Evidence] = []
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
        uow: Scenario3ProviderReadUnitOfWork,
        context: ToolCallContext,
        *,
        dependency_id: str,
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
            )
        ]
        return matches[-1] if matches else None

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


__all__ = [
    "Scenario3EvidenceTtlPolicy",
    "Scenario3ProviderReadService",
    "Scenario3ProviderReadUnitOfWork",
]
