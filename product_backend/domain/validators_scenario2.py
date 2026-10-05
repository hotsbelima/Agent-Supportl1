"""Deterministic Scenario 2 evidence and approval validators.

These validators inspect Product-owned typed facts only. They do not parse model
rationale and do not infer correlation from event count/order.
"""

from __future__ import annotations

from datetime import datetime

from .enums import EvidenceSourceType, HealthState, ProposalStatus
from .errors import DomainError, ErrorCode
from .models import Evidence
from .scenario2 import (
    DependencyKind,
    ExternalDependencyStatusSnapshot,
    LocalServiceHealthSnapshot,
    MajorIncidentProposal,
    MajorIncidentSearchSnapshot,
    OperationalSignalEvidenceSnapshot,
    Scenario2ActionType,
    ServiceDependencyMappingSnapshot,
)


_REQUIRED_MAJOR_INCIDENT_EVIDENCE = frozenset(
    {
        EvidenceSourceType.OPERATIONAL_SIGNAL,
        EvidenceSourceType.LOCAL_SERVICE_HEALTH,
        EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING,
        EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS,
        EvidenceSourceType.MAJOR_INCIDENT_SEARCH,
    }
)

_DYNAMIC_SCENARIO2_EVIDENCE = frozenset(
    {
        EvidenceSourceType.OPERATIONAL_SIGNAL,
        EvidenceSourceType.LOCAL_SERVICE_HEALTH,
        EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS,
        EvidenceSourceType.MAJOR_INCIDENT_SEARCH,
    }
)

_EXPECTED_SCENARIO2_PAYLOAD_TYPES = {
    EvidenceSourceType.OPERATIONAL_SIGNAL: OperationalSignalEvidenceSnapshot,
    EvidenceSourceType.LOCAL_SERVICE_HEALTH: LocalServiceHealthSnapshot,
    EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING: ServiceDependencyMappingSnapshot,
    EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS: ExternalDependencyStatusSnapshot,
    EvidenceSourceType.MAJOR_INCIDENT_SEARCH: MajorIncidentSearchSnapshot,
}


def _invalid(reason: str, evidence_id: str | None = None) -> DomainError:
    details = (("reason", reason),)
    if evidence_id is not None:
        details += (("evidence_id", evidence_id),)
    return DomainError(
        code=ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE,
        message="Scenario 2 evidence is missing, stale, foreign, or inconsistent.",
        details=details,
    )


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _temporal_error(evidence: Evidence, now: datetime) -> str | None:
    if not _aware(now) or not _aware(evidence.captured_at):
        return "non_timezone_aware_timestamp"
    try:
        if evidence.captured_at > now:
            return "evidence_captured_in_future"
    except TypeError:
        return "incomparable_timestamp"

    if evidence.source_type in _DYNAMIC_SCENARIO2_EVIDENCE:
        if evidence.expires_at is None:
            return "dynamic_evidence_without_ttl"

    if evidence.expires_at is None:
        return None
    if not _aware(evidence.expires_at):
        return "non_timezone_aware_expiry"
    try:
        if evidence.expires_at <= evidence.captured_at:
            return "invalid_evidence_ttl_window"
        if evidence.expires_at <= now:
            return "expired_evidence"
    except TypeError:
        return "incomparable_timestamp"
    return None


def _validate_common(
    *,
    tenant_id: str,
    run_id: str,
    evidence_ids: tuple[str, ...],
    evidence: tuple[Evidence, ...],
    now: datetime,
) -> DomainError | None:
    if not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
        return _invalid("missing_or_duplicate_evidence_ids")

    by_id = {item.evidence_id: item for item in evidence}
    if len(by_id) != len(evidence) or set(by_id) != set(evidence_ids):
        return _invalid("evidence_ids_not_resolved_exactly")

    for item in evidence:
        if item.tenant_id != tenant_id or item.run_id != run_id:
            return _invalid("foreign_tenant_or_run", item.evidence_id)
        expected_type = _EXPECTED_SCENARIO2_PAYLOAD_TYPES.get(item.source_type)
        if expected_type is None:
            return _invalid("unsupported_scenario2_evidence_type", item.evidence_id)
        if not isinstance(item.payload, expected_type):
            return _invalid("source_payload_type_mismatch", item.evidence_id)
        temporal_error = _temporal_error(item, now)
        if temporal_error is not None:
            return _invalid(temporal_error, item.evidence_id)
    return None


def validate_major_incident_proposal_evidence(
    *,
    proposal: MajorIncidentProposal,
    evidence: tuple[Evidence, ...],
    now: datetime,
) -> DomainError | None:
    """Validate all deterministic facts required for CREATE_MAJOR_INCIDENT."""

    if proposal.action_type is not Scenario2ActionType.CREATE_MAJOR_INCIDENT:
        return _invalid("unsupported_scenario2_action")
    if proposal.status is not ProposalStatus.PENDING_APPROVAL:
        return _invalid("proposal_not_pending")
    if not proposal.correlation_key.strip():
        return _invalid("missing_correlation_key")
    if not proposal.service_key.strip():
        return _invalid("missing_service_key")
    if not proposal.dependency_id.strip() or not proposal.dependency_name.strip():
        return _invalid("missing_dependency_identity")
    if len(proposal.affected_site_ids) < 2:
        return _invalid("insufficient_cross_site_evidence")
    if len(set(proposal.affected_site_ids)) != len(proposal.affected_site_ids):
        return _invalid("duplicate_affected_site")

    common = _validate_common(
        tenant_id=proposal.tenant_id,
        run_id=proposal.run_id,
        evidence_ids=proposal.evidence_ids,
        evidence=evidence,
        now=now,
    )
    if common is not None:
        return common

    source_types = {item.source_type for item in evidence}
    if not _REQUIRED_MAJOR_INCIDENT_EVIDENCE.issubset(source_types):
        return _invalid("missing_required_evidence_class")

    affected_sites = set(proposal.affected_site_ids)

    signal_items = [
        item
        for item in evidence
        if item.source_type is EvidenceSourceType.OPERATIONAL_SIGNAL
        and isinstance(item.payload, OperationalSignalEvidenceSnapshot)
    ]
    signal_sites = set()
    for item in signal_items:
        payload = item.payload
        if payload.symptom_key != proposal.correlation_key:
            return _invalid("signal_correlation_mismatch", item.evidence_id)
        if payload.service_key != proposal.service_key:
            return _invalid("signal_service_mismatch", item.evidence_id)
        if payload.site_id not in affected_sites:
            return _invalid("signal_site_outside_proposal", item.evidence_id)
        if not {
            payload.signal_id,
            payload.site_id,
            payload.service_key,
            payload.symptom_key,
        }.issubset(set(item.entity_ids)):
            return _invalid("signal_provenance_not_supported", item.evidence_id)
        signal_sites.add(payload.site_id)

    if signal_sites != affected_sites:
        return _invalid("affected_sites_not_supported_by_signals")

    local_health_by_site: dict[str, LocalServiceHealthSnapshot] = {}
    for item in evidence:
        if (
            item.source_type is EvidenceSourceType.LOCAL_SERVICE_HEALTH
            and isinstance(item.payload, LocalServiceHealthSnapshot)
        ):
            payload = item.payload
            if payload.site_id not in affected_sites:
                continue
            if payload.service_key != proposal.service_key:
                continue
            if not {payload.site_id, payload.service_key}.issubset(
                set(item.entity_ids)
            ):
                return _invalid("local_health_provenance_not_supported", item.evidence_id)
            if (
                payload.network_health is not HealthState.HEALTHY
                or payload.local_service_health is not HealthState.HEALTHY
            ):
                return _invalid("local_site_not_healthy", item.evidence_id)
            local_health_by_site[payload.site_id] = payload

    if set(local_health_by_site) != affected_sites:
        return _invalid("missing_local_health_for_affected_site")

    mapping_supported = any(
        isinstance(item.payload, ServiceDependencyMappingSnapshot)
        and item.payload.service_key == proposal.service_key
        and item.payload.dependency_id == proposal.dependency_id
        and item.payload.dependency_name == proposal.dependency_name
        and item.payload.dependency_kind is DependencyKind.EXTERNAL_PROVIDER
        and {
            item.payload.service_key,
            item.payload.dependency_id,
        }.issubset(set(item.entity_ids))
        for item in evidence
        if item.source_type is EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING
    )
    if not mapping_supported:
        return _invalid("dependency_mapping_not_supported")

    degraded_supported = any(
        isinstance(item.payload, ExternalDependencyStatusSnapshot)
        and item.payload.dependency_id == proposal.dependency_id
        and item.payload.dependency_name == proposal.dependency_name
        and item.payload.status is HealthState.DEGRADED
        and item.payload.dependency_id in item.entity_ids
        for item in evidence
        if item.source_type is EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS
    )
    if not degraded_supported:
        return _invalid("external_dependency_not_degraded")

    duplicate_search_supported = any(
        isinstance(item.payload, MajorIncidentSearchSnapshot)
        and item.payload.service_key == proposal.service_key
        and item.payload.correlation_key == proposal.correlation_key
        and item.payload.dependency_id == proposal.dependency_id
        and not item.payload.open_major_incident_ids
        and {
            item.payload.service_key,
            item.payload.correlation_key,
            item.payload.dependency_id,
        }.issubset(set(item.entity_ids))
        for item in evidence
        if item.source_type is EvidenceSourceType.MAJOR_INCIDENT_SEARCH
    )
    if not duplicate_search_supported:
        return _invalid("matching_major_incident_exists_or_search_missing")

    return None


def validate_major_incident_approval_currentness(
    *,
    proposal: MajorIncidentProposal,
    proposal_evidence: tuple[Evidence, ...],
    current_local_health: tuple[LocalServiceHealthSnapshot, ...],
    current_dependency_status: ExternalDependencyStatusSnapshot | None,
    current_major_incident_search: MajorIncidentSearchSnapshot | None,
    now: datetime,
) -> DomainError | None:
    """Revalidate Scenario 2 Product truth immediately before execution."""

    evidence_error = validate_major_incident_proposal_evidence(
        proposal=proposal,
        evidence=proposal_evidence,
        now=now,
    )
    if evidence_error is not None:
        return evidence_error

    health_by_site = {
        item.site_id: item
        for item in current_local_health
        if item.service_key == proposal.service_key
    }
    if set(health_by_site) != set(proposal.affected_site_ids):
        return _invalid("current_local_health_incomplete")
    if any(
        item.network_health is not HealthState.HEALTHY
        or item.local_service_health is not HealthState.HEALTHY
        for item in health_by_site.values()
    ):
        return _invalid("current_local_site_not_healthy")

    if current_dependency_status is None:
        return _invalid("current_dependency_status_unavailable")
    if (
        current_dependency_status.dependency_id != proposal.dependency_id
        or current_dependency_status.dependency_name != proposal.dependency_name
    ):
        return _invalid("current_dependency_identity_changed")
    if current_dependency_status.status is not HealthState.DEGRADED:
        return _invalid("external_dependency_recovered")

    if current_major_incident_search is None:
        return _invalid("current_major_incident_search_unavailable")
    if (
        current_major_incident_search.service_key != proposal.service_key
        or current_major_incident_search.correlation_key != proposal.correlation_key
        or current_major_incident_search.dependency_id != proposal.dependency_id
    ):
        return _invalid("current_major_incident_search_mismatch")
    if current_major_incident_search.open_major_incident_ids:
        return _invalid("matching_major_incident_now_exists")

    return None


__all__ = [
    "validate_major_incident_approval_currentness",
    "validate_major_incident_proposal_evidence",
]
