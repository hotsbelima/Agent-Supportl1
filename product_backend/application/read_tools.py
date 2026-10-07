"""Application service for Scenario 1 read tools.

This layer owns tenant/run/entity checks, provider orchestration, typed error
normalization, TTL policy and immutable evidence creation. Tool adapters remain
thin and model-facing.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from product_backend.application.lifecycle import append_uow_event
from product_backend.contracts.events import ApplicationEventType
from product_backend.contracts.tools import (
    GetDeviceRequest,
    GetDeviceResult,
    GetDeviceSuccess,
    GetSiteHealthRequest,
    GetSiteHealthResult,
    GetSiteHealthSuccess,
    RunDiagnosticRequest,
    RunDiagnosticResult,
    RunDiagnosticSuccess,
    SearchIncidentsRequest,
    SearchIncidentsResult,
    SearchIncidentsSuccess,
    SearchKbRequest,
    SearchKbResult,
    SearchKbSuccess,
    ToolCallContext,
    ToolFailure,
)
from product_backend.domain.enums import (
    DiagnosticType,
    EvidenceSourceType,
    IncidentSearchScope,
    OperationalState,
    RunStatus,
)
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.domain.models import Evidence
from product_backend.domain.read_model import (
    evidence_knows_device,
    evidence_knows_site,
    latest_topology_for_attachment,
    valid_access_link_observation,
    valid_cmdb_observation,
    valid_site_health_observation,
)
from product_backend.ports.repositories import ToolReadUnitOfWork
from product_backend.ports.source_systems import (
    CmdbPort,
    ItsmPort,
    KnowledgeBasePort,
    MonitoringPort,
)



Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
ReadUowFactory = Callable[[], ToolReadUnitOfWork]


@dataclass(frozen=True, slots=True)
class EvidenceTtlPolicy:
    """Freshness windows are application configuration, never model arguments."""

    site_health: timedelta
    access_link_diagnostic: timedelta

    def __post_init__(self) -> None:
        if self.site_health <= timedelta(0):
            raise ValueError("site_health TTL must be positive")
        if self.access_link_diagnostic <= timedelta(0):
            raise ValueError("access_link_diagnostic TTL must be positive")


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
) -> ToolFailure:
    return ToolFailure(
        ok=False,
        error=DomainError(
            code=code,
            message=message,
            retryable=retryable,
            details=(("reason", reason),),
        ),
    )


def _diagnostic_code(state: OperationalState) -> str:
    """Backward-compatible compact observation code for the tool result."""
    return f"LINK_{state.value}"


async def _record_tool_started(
    uow: object,
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
    # Persist before the provider call so the UI can show real in-flight work.
    await uow.commit()


async def _record_observation(
    uow: object,
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


class Scenario1ReadToolService:
    def __init__(
        self,
        *,
        read_uow_factory: ReadUowFactory,
        cmdb: CmdbPort,
        monitoring: MonitoringPort,
        itsm: ItsmPort,
        kb: KnowledgeBasePort,
        ttl_policy: EvidenceTtlPolicy,
        clock: Clock = _utc_now,
        id_factory: IdFactory = _id,
    ) -> None:
        self._read_uow_factory = read_uow_factory
        self._cmdb = cmdb
        self._monitoring = monitoring
        self._itsm = itsm
        self._kb = kb
        self._ttl = ttl_policy
        self._clock = clock
        self._id_factory = id_factory

    async def _require_active_run(
        self,
        uow: ToolReadUnitOfWork,
        context: ToolCallContext,
    ) -> ToolFailure | None:
        run = await uow.runs.get(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
        )
        if run is None:
            return _failure(
                ErrorCode.CONTEXT_MISMATCH,
                "Run context is not valid.",
                "run_not_found",
            )
        if run.status is not RunStatus.ACTIVE:
            return _failure(
                ErrorCode.INVALID_STATE_TRANSITION,
                "Read tools are not available in the current run state.",
                "run_not_active",
            )
        return None

    async def _known_device(
        self,
        uow: ToolReadUnitOfWork,
        context: ToolCallContext,
        device_id: str,
    ) -> bool:
        if await uow.incidents.find_by_device(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            device_id=device_id,
        ):
            return True

        evidence = await uow.evidence.find_by_entity_id(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            entity_id=device_id,
        )
        return evidence_knows_device(evidence, device_id)

    async def _known_site(
        self,
        uow: ToolReadUnitOfWork,
        context: ToolCallContext,
        site_id: str,
    ) -> bool:
        if await uow.incidents.find_by_site(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            site_id=site_id,
        ):
            return True

        evidence = await uow.evidence.find_by_entity_id(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            entity_id=site_id,
        )
        return evidence_knows_site(evidence, site_id)

    async def _latest_topology_for_attachment(
        self,
        uow: ToolReadUnitOfWork,
        context: ToolCallContext,
        attachment_id: str,
    ) -> DeviceTopology | None:
        evidence = await uow.evidence.find_by_entity_id(
            tenant_id=context.tenant_id,
            run_id=context.run_id,
            entity_id=attachment_id,
        )
        return latest_topology_for_attachment(evidence, attachment_id)

    async def get_device(
        self,
        context: ToolCallContext,
        request: GetDeviceRequest,
    ) -> GetDeviceResult:
        if not request.device_id.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Device ID is required.",
                "empty_device_id",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error:
                    return state_error
                if not await self._known_device(uow, context, request.device_id):
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Device is not known in the current run.",
                        "unknown_run_device",
                    )

                await _record_tool_started(uow, context=context, tool_name="get_device")
                topology = await self._cmdb.get_device(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    device_id=request.device_id,
                )
                if topology is None:
                    return _failure(
                        ErrorCode.DEVICE_NOT_FOUND,
                        "Device was not found.",
                        "device_not_found",
                    )
                site_is_known = await self._known_site(
                    uow,
                    context,
                    topology.site_id,
                )
                if not valid_cmdb_observation(
                    requested_device_id=request.device_id,
                    topology=topology,
                    site_is_known=site_is_known,
                ):
                    return _failure(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "CMDB returned invalid or out-of-context topology.",
                        "cmdb_topology_invalid",
                    )

                now = self._clock()
                evidence = Evidence(
                    evidence_id=self._id_factory("evidence"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    source_type=EvidenceSourceType.CMDB_SNAPSHOT,
                    captured_at=now,
                    entity_ids=(
                        topology.device_id,
                        topology.site_id,
                        topology.attachment_id,
                        topology.expected_switch_id,
                        topology.expected_port_id,
                    ),
                    payload=topology,
                )
                await uow.evidence.add(evidence)
                await _record_observation(
                    uow,
                    context=context,
                    evidence=evidence,
                )
                result = GetDeviceSuccess(
                    ok=True,
                    device_id=topology.device_id,
                    attachment_id=topology.attachment_id,
                    site_id=topology.site_id,
                    device_type=topology.device_type,
                    topology=topology,
                    evidence=evidence,
                )
                await uow.commit()
                return result
        except Exception:
            return _failure(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Device data is temporarily unavailable.",
                "get_device_failed",
                retryable=True,
            )

    async def get_site_health(
        self,
        context: ToolCallContext,
        request: GetSiteHealthRequest,
    ) -> GetSiteHealthResult:
        if not request.site_id.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Site ID is required.",
                "empty_site_id",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error:
                    return state_error
                if not await self._known_site(uow, context, request.site_id):
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Site is not known in the current run.",
                        "unknown_run_site",
                    )

                await _record_tool_started(uow, context=context, tool_name="get_site_health")
                snapshot = await self._monitoring.get_site_health(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    site_id=request.site_id,
                )
                if snapshot is None:
                    return _failure(
                        ErrorCode.SITE_NOT_FOUND,
                        "Site health was not found.",
                        "site_not_found",
                    )
                affected_device_is_known = await self._known_device(
                    uow,
                    context,
                    snapshot.affected_device_id,
                )
                if not valid_site_health_observation(
                    requested_site_id=request.site_id,
                    snapshot=snapshot,
                    affected_device_is_known=affected_device_is_known,
                ):
                    return _failure(
                        ErrorCode.SITE_HEALTH_UNAVAILABLE,
                        "Monitoring returned invalid or out-of-context site health.",
                        "site_health_invalid",
                    )

                now = self._clock()
                evidence = Evidence(
                    evidence_id=self._id_factory("evidence"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    source_type=EvidenceSourceType.SITE_HEALTH,
                    captured_at=now,
                    entity_ids=(
                        snapshot.site_id,
                        snapshot.peer_device_id,
                        snapshot.affected_device_id,
                    ),
                    payload=snapshot,
                    expires_at=now + self._ttl.site_health,
                )
                await uow.evidence.add(evidence)
                await _record_observation(
                    uow,
                    context=context,
                    evidence=evidence,
                )
                result = GetSiteHealthSuccess(
                    ok=True,
                    site_id=snapshot.site_id,
                    health=snapshot,
                    evidence=evidence,
                )
                await uow.commit()
                return result
        except Exception:
            return _failure(
                ErrorCode.SITE_HEALTH_UNAVAILABLE,
                "Site health is temporarily unavailable.",
                "get_site_health_failed",
                retryable=True,
            )

    async def run_diagnostic(
        self,
        context: ToolCallContext,
        request: RunDiagnosticRequest,
    ) -> RunDiagnosticResult:
        if request.diagnostic_type is not DiagnosticType.ACCESS_LINK:
            return _failure(
                ErrorCode.UNSUPPORTED_DIAGNOSTIC,
                "Diagnostic type is not supported.",
                "unsupported_diagnostic",
            )
        if not request.target_id.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Diagnostic target is required.",
                "empty_target_id",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error:
                    return state_error

                topology = await self._latest_topology_for_attachment(
                    uow,
                    context,
                    request.target_id,
                )
                if topology is None:
                    return _failure(
                        ErrorCode.ATTACHMENT_NOT_FOUND,
                        "Diagnostic target is not a known attachment in this run.",
                        "unknown_attachment_target",
                    )

                await _record_tool_started(uow, context=context, tool_name="run_diagnostic")
                snapshot = await self._monitoring.run_diagnostic(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    diagnostic_type=request.diagnostic_type,
                    target_id=request.target_id,
                )
                if snapshot is None:
                    return _failure(
                        ErrorCode.ATTACHMENT_NOT_FOUND,
                        "Diagnostic target was not found.",
                        "diagnostic_target_not_found",
                    )
                if not valid_access_link_observation(
                    requested_target_id=request.target_id,
                    topology=topology,
                    snapshot=snapshot,
                ):
                    return _failure(
                        ErrorCode.DIAGNOSTIC_UNAVAILABLE,
                        "Diagnostic returned topology inconsistent with CMDB.",
                        "diagnostic_topology_mismatch",
                    )

                now = self._clock()
                evidence = Evidence(
                    evidence_id=self._id_factory("evidence"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    source_type=EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
                    captured_at=now,
                    entity_ids=(
                        snapshot.attachment_id,
                        snapshot.switch_id,
                        snapshot.port_id,
                    ),
                    payload=snapshot,
                    expires_at=now + self._ttl.access_link_diagnostic,
                )
                await uow.evidence.add(evidence)
                await _record_observation(
                    uow,
                    context=context,
                    evidence=evidence,
                )
                result = RunDiagnosticSuccess(
                    ok=True,
                    diagnostic_type=request.diagnostic_type,
                    target_id=request.target_id,
                    attachment_id=snapshot.attachment_id,
                    diagnostic=_diagnostic_code(snapshot.operational_state),
                    observed_state=snapshot.operational_state.value,
                    snapshot=snapshot,
                    evidence=evidence,
                )
                await uow.commit()
                return result
        except Exception:
            return _failure(
                ErrorCode.DIAGNOSTIC_UNAVAILABLE,
                "Diagnostic is temporarily unavailable.",
                "run_diagnostic_failed",
                retryable=True,
            )

    async def search_incidents(
        self,
        context: ToolCallContext,
        request: SearchIncidentsRequest,
    ) -> SearchIncidentsResult:
        if request.scope not in (
            IncidentSearchScope.DEVICE,
            IncidentSearchScope.SITE,
        ):
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Incident search scope is invalid.",
                "invalid_search_scope",
            )
        if not request.entity_id.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "Incident search entity is required.",
                "empty_entity_id",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error:
                    return state_error

                known = (
                    await self._known_device(uow, context, request.entity_id)
                    if request.scope is IncidentSearchScope.DEVICE
                    else await self._known_site(uow, context, request.entity_id)
                )
                if not known:
                    return _failure(
                        ErrorCode.CONTEXT_MISMATCH,
                        "Search entity is not known in the current run.",
                        "unknown_run_entity",
                    )

                snapshot = await self._itsm.search_incidents(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    scope=request.scope,
                    entity_id=request.entity_id,
                )
                if (
                    snapshot.scope is not request.scope
                    or snapshot.entity_id != request.entity_id
                ):
                    return _failure(
                        ErrorCode.INCIDENT_SEARCH_UNAVAILABLE,
                        "ITSM returned an inconsistent search result.",
                        "incident_search_identity_mismatch",
                    )

                now = self._clock()
                evidence = Evidence(
                    evidence_id=self._id_factory("evidence"),
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    source_type=EvidenceSourceType.INCIDENT_SEARCH,
                    captured_at=now,
                    entity_ids=(request.entity_id, *snapshot.open_incident_ids),
                    payload=snapshot,
                )
                await uow.evidence.add(evidence)
                await _record_observation(
                    uow,
                    context=context,
                    evidence=evidence,
                )
                result = SearchIncidentsSuccess(
                    ok=True,
                    scope=request.scope,
                    entity_id=request.entity_id,
                    snapshot=snapshot,
                    evidence=evidence,
                )
                await uow.commit()
                return result
        except Exception:
            return _failure(
                ErrorCode.INCIDENT_SEARCH_UNAVAILABLE,
                "Incident search is temporarily unavailable.",
                "search_incidents_failed",
                retryable=True,
            )

    async def search_kb(
        self,
        context: ToolCallContext,
        request: SearchKbRequest,
    ) -> SearchKbResult:
        if not request.query.strip():
            return _failure(
                ErrorCode.INVALID_ARGUMENT,
                "KB query is required.",
                "empty_query",
            )
        try:
            async with self._read_uow_factory() as uow:
                state_error = await self._require_active_run(uow, context)
                if state_error:
                    return state_error

                articles = await self._kb.search(
                    tenant_id=context.tenant_id,
                    run_id=context.run_id,
                    query=request.query,
                )
                if any(not article.article_id.strip() for article in articles):
                    return _failure(
                        ErrorCode.KB_UNAVAILABLE,
                        "Knowledge base returned an invalid article.",
                        "kb_article_identity_missing",
                    )

                now = self._clock()
                evidence_items = tuple(
                    Evidence(
                        evidence_id=self._id_factory("evidence"),
                        tenant_id=context.tenant_id,
                        run_id=context.run_id,
                        source_type=EvidenceSourceType.KB_ARTICLE,
                        captured_at=now,
                        entity_ids=(article.article_id,),
                        payload=article,
                    )
                    for article in articles
                )
                for evidence in evidence_items:
                    await uow.evidence.add(evidence)
                    await _record_observation(
                        uow,
                        context=context,
                        evidence=evidence,
                    )
                result = SearchKbSuccess(
                    ok=True,
                    query=request.query,
                    articles=articles,
                    evidence=evidence_items,
                )
                await uow.commit()
                return result
        except Exception:
            return _failure(
                ErrorCode.KB_UNAVAILABLE,
                "Knowledge base is temporarily unavailable.",
                "search_kb_failed",
                retryable=True,
            )
