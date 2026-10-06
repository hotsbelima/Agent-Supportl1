"""Scenario 3 evidence-producing provider reads for Phase 8C1.

The service is deliberately narrower than Scenario2ReadToolService. It reads
only service dependency mapping and authoritative external dependency status.
The Product boundary owns context validation and Evidence persistence; provider
sources return observations only and never encode a replan decision.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from product_backend.application.lifecycle import append_uow_event
from product_backend.contracts.events import ApplicationEventType
from product_backend.contracts.scenario3_provider_tools import (
    GetExternalDependencyStatusRequest,
    GetExternalDependencyStatusResult,
    GetExternalDependencyStatusSuccess,
    GetServiceDependenciesRequest,
    GetServiceDependenciesResult,
    GetServiceDependenciesSuccess,
    Scenario3ProviderToolFailure,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import EvidenceSourceType, RunStatus
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.domain.models import Evidence
from product_backend.domain.scenario2 import ServiceDependencyMappingSnapshot
from product_backend.ports.scenario2_sources import (
    ExternalDependencyStatusPort,
    ServiceDependencyPort,
)
from product_backend.ports.scenario3 import Scenario3ProviderReadUnitOfWork


Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
ReadUowFactory = Callable[[], Scenario3ProviderReadUnitOfWork]


@dataclass(frozen=True, slots=True)
class Scenario3ProviderEvidenceTtlPolicy:
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
) -> Scenario3ProviderToolFailure:
    return Scenario3ProviderToolFailure(
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
    """Bind provider reads to persisted Scenario 3 Product facts."""

    def __init__(
        self,
        *,
        read_uow_factory: ReadUowFactory,
        dependency_mapping: ServiceDependencyPort,
        dependency_status: ExternalDependencyStatusPort,
        ttl_policy: Scenario3ProviderEvidenceTtlPolicy,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._read_uow_factory = read_uow_factory
        self._dependency_mapping = dependency_mapping
        self._dependency_status = dependency_status
        self._ttl = ttl_policy
        self._clock = clock
        self._id_factory = id_factory

    async def _require_active_scenario3_run(
        self,
        uow: Scenario3ProviderReadUnitOfWork,
        context: ToolCallContext,
    ) -> Scenario3ProviderToolFailure | None:
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

    async def _persisted_service_context(
        self,
        uow: Scenario3ProviderReadUnitOfWork,
        context: ToolCallContext,
    ) -> tuple[str, str] | None:
        events = await uow.events.list_after(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            after_seq=0,
            limit=10,
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
                and service_key.strip()
                and isinstance(symptom_key, str)
                and symptom_key.strip()
            ):
                return service_key.strip(), symptom_key.strip()
        return None

    async def get_service_dependencies(
        self,
        context: ToolCallContext,
        request: GetServiceDependenciesRequest,
    ) -> GetServiceDependenciesResult:
        requested_service = request.service_key.strip()
        if not requested_service:
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Service identifier is required.",
                "missing_service_key",
            )

        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_scenario3_run(uow, context)
                if state_error is not None:
                    return state_error

                persisted_context = await self._persisted_service_context(uow, context)
                if (
                    persisted_context is None
                    or persisted_context[0] != requested_service
                ):
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Service is not established by the current Scenario 3 run.",
                        "service_not_bound_to_run",
                    )

                mappings = await self._dependency_mapping.get_service_dependencies(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    service_key=requested_service,
                )

                now = self._clock()
                evidence_items: list[Evidence] = []
                for mapping in mappings:
                    if mapping.service_key != requested_service:
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
                    await _record_observation(
                        uow,
                        context=context,
                        evidence=evidence,
                    )
                    evidence_items.append(evidence)

                await uow.commit()
                return GetServiceDependenciesSuccess(
                    ok=True,
                    service_key=requested_service,
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
        service_key: str,
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
                and item.payload.service_key == service_key
            )
        ]
        return matches[-1] if matches else None

    async def get_external_dependency_status(
        self,
        context: ToolCallContext,
        request: GetExternalDependencyStatusRequest,
    ) -> GetExternalDependencyStatusResult:
        requested_dependency = request.dependency_id.strip()
        if not requested_dependency:
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Dependency identifier is required.",
                "missing_dependency_id",
            )

        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_scenario3_run(uow, context)
                if state_error is not None:
                    return state_error

                persisted_context = await self._persisted_service_context(uow, context)
                if persisted_context is None:
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Scenario 3 provider context is not established.",
                        "missing_persisted_service_context",
                    )
                service_key, _ = persisted_context

                mapping = await self._known_dependency_mapping(
                    uow,
                    context,
                    dependency_id=requested_dependency,
                    service_key=service_key,
                )
                if mapping is None:
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Dependency is not established by Product evidence in this run.",
                        "dependency_not_established",
                    )

                snapshot = (
                    await self._dependency_status.get_external_dependency_status(
                        tenant_id=context.tenant_id,
                        run_id=context.run_id,
                        dependency_id=requested_dependency,
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
                    snapshot.dependency_id != requested_dependency
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
                await _record_observation(
                    uow,
                    context=context,
                    evidence=evidence,
                )
                await uow.commit()
                return GetExternalDependencyStatusSuccess(
                    ok=True,
                    dependency_id=requested_dependency,
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
    "Scenario3ProviderEvidenceTtlPolicy",
    "Scenario3ProviderReadService",
]
