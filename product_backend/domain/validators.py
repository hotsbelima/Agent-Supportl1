"""Deterministic Scenario 1 evidence and approval revalidation.

Validators inspect typed domain data only. They never parse LLM rationale/facts.
"""
from __future__ import annotations

from datetime import datetime

from .enums import (
    ActionType,
    AdminState,
    ConfigurationState,
    DiagnosisCode,
    EvidenceSourceType,
    HealthState,
    IncidentStatus,
    OperationalState,
    PortSecurityState,
)
from .errors import DomainError, ErrorCode
from .models import (
    AccessLinkDiagnosticSnapshot,
    ActionProposal,
    DeviceTopology,
    Evidence,
    Incident,
    IncidentSearchSnapshot,
    KbArticle,
    SiteHealthSnapshot,
)

_REQUIRED_FIELD_VISIT_EVIDENCE = frozenset(
    {
        EvidenceSourceType.CMDB_SNAPSHOT,
        EvidenceSourceType.SITE_HEALTH,
        EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
        EvidenceSourceType.KB_ARTICLE,
    }
)
_DYNAMIC_EVIDENCE = frozenset(
    {
        EvidenceSourceType.SITE_HEALTH,
        EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
    }
)
_EXPECTED_PAYLOAD_TYPES = {
    EvidenceSourceType.CMDB_SNAPSHOT: DeviceTopology,
    EvidenceSourceType.SITE_HEALTH: SiteHealthSnapshot,
    EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC: AccessLinkDiagnosticSnapshot,
    EvidenceSourceType.INCIDENT_SEARCH: IncidentSearchSnapshot,
    EvidenceSourceType.KB_ARTICLE: KbArticle,
}


def _invalid_evidence(reason: str, evidence_id: str | None = None) -> DomainError:
    details = (("reason", reason),)
    if evidence_id:
        details += (("evidence_id", evidence_id),)
    return DomainError(
        code=ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE,
        message="Required evidence is missing, stale, foreign, or inconsistent.",
        details=details,
    )


def _expired(evidence: Evidence, now: datetime) -> bool:
    if evidence.expires_at is None:
        return False
    try:
        return evidence.expires_at <= now
    except TypeError:
        return True


def _validate_common_evidence_set(
    *,
    tenant_id: str,
    run_id: str,
    evidence_ids: tuple[str, ...],
    evidence: tuple[Evidence, ...],
    now: datetime,
) -> DomainError | None:
    if not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
        return _invalid_evidence("missing_or_duplicate_evidence_ids")

    by_id = {item.evidence_id: item for item in evidence}
    if len(by_id) != len(evidence) or set(by_id) != set(evidence_ids):
        return _invalid_evidence("evidence_ids_not_resolved_exactly")

    for item in evidence:
        if item.tenant_id != tenant_id or item.run_id != run_id:
            return _invalid_evidence("foreign_tenant_or_run", item.evidence_id)
        expected_type = _EXPECTED_PAYLOAD_TYPES.get(item.source_type)
        if expected_type is not None and not isinstance(item.payload, expected_type):
            return _invalid_evidence("source_payload_type_mismatch", item.evidence_id)
        if item.source_type in _DYNAMIC_EVIDENCE and item.expires_at is None:
            return _invalid_evidence("dynamic_evidence_without_ttl", item.evidence_id)
        if _expired(item, now):
            return _invalid_evidence("expired_evidence", item.evidence_id)
    return None


def validate_field_visit_evidence(
    *,
    tenant_id: str,
    run_id: str,
    incident: Incident,
    device_id: str,
    diagnosis: DiagnosisCode,
    action_type: ActionType,
    evidence_ids: tuple[str, ...],
    evidence: tuple[Evidence, ...],
    now: datetime,
) -> DomainError | None:
    """Validate the four evidence classes required for Scenario 1 proposal."""
    common = _validate_common_evidence_set(
        tenant_id=tenant_id,
        run_id=run_id,
        evidence_ids=evidence_ids,
        evidence=evidence,
        now=now,
    )
    if common:
        return common

    if incident.tenant_id != tenant_id or incident.run_id != run_id:
        return _invalid_evidence("incident_context_mismatch")
    if incident.reported_device_id != device_id:
        return _invalid_evidence("proposal_device_not_incident_device")
    if diagnosis is not DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE:
        return _invalid_evidence("unsupported_diagnosis")
    if action_type is not ActionType.ONSITE_FIELD_VISIT:
        return _invalid_evidence("unsupported_action")

    source_types = {item.source_type for item in evidence}
    if not _REQUIRED_FIELD_VISIT_EVIDENCE.issubset(source_types):
        return _invalid_evidence("missing_required_evidence_class")

    cmdb_candidates = [
        item.payload
        for item in evidence
        if item.source_type is EvidenceSourceType.CMDB_SNAPSHOT
        and isinstance(item.payload, DeviceTopology)
        and item.payload.device_id == device_id
        and item.payload.site_id == incident.site_id
        and bool(item.payload.attachment_id)
        and bool(item.payload.expected_switch_id)
        and bool(item.payload.expected_port_id)
    ]
    if not cmdb_candidates:
        return _invalid_evidence("cmdb_relationship_not_supported")

    site_supported = any(
        isinstance(item.payload, SiteHealthSnapshot)
        and item.payload.site_id == incident.site_id
        and item.payload.site_network is HealthState.HEALTHY
        and item.payload.payment_service is HealthState.HEALTHY
        and bool(item.payload.peer_device_id)
        and item.payload.peer_device_id != device_id
        and item.payload.peer_reachable
        and item.payload.affected_device_id == device_id
        and not item.payload.affected_device_reachable
        for item in evidence
        if item.source_type is EvidenceSourceType.SITE_HEALTH
    )
    if not site_supported:
        return _invalid_evidence("site_health_pattern_not_supported")

    diagnostic_supported = any(
        isinstance(item.payload, AccessLinkDiagnosticSnapshot)
        and any(
            item.payload.attachment_id == cmdb.attachment_id
            and item.payload.switch_id == cmdb.expected_switch_id
            and item.payload.port_id == cmdb.expected_port_id
            for cmdb in cmdb_candidates
        )
        and item.payload.switch_reachable
        and item.payload.admin_state is AdminState.UP
        and item.payload.operational_state is OperationalState.DOWN
        and item.payload.port_security is PortSecurityState.NORMAL
        and item.payload.configuration is ConfigurationState.EXPECTED
        for item in evidence
        if item.source_type is EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC
    )
    if not diagnostic_supported:
        return _invalid_evidence("access_link_pattern_not_supported")

    kb_supported = any(
        isinstance(item.payload, KbArticle)
        and item.payload.approved
        and diagnosis in item.payload.diagnosis_codes
        and action_type in item.payload.allowed_actions
        for item in evidence
        if item.source_type is EvidenceSourceType.KB_ARTICLE
    )
    if not kb_supported:
        return _invalid_evidence("approved_kb_does_not_authorize_action")

    return None


def validate_approval_currentness(
    *,
    proposal: ActionProposal,
    incident: Incident,
    current_topology: DeviceTopology | None,
    current_diagnostic: AccessLinkDiagnosticSnapshot | None,
) -> DomainError | None:
    """Revalidate the conditions required at human Approve using fresh backend reads."""
    if incident.tenant_id != proposal.tenant_id or incident.run_id != proposal.run_id:
        return _invalid_evidence("incident_context_mismatch")
    if incident.status is not IncidentStatus.OPEN:
        return _invalid_evidence("incident_not_open")
    if incident.reported_device_id != proposal.device_id:
        return _invalid_evidence("device_no_longer_belongs_to_incident")
    if current_topology is None:
        return _invalid_evidence("current_cmdb_topology_unavailable")
    if (
        current_topology.device_id != proposal.device_id
        or current_topology.site_id != incident.site_id
        or not current_topology.attachment_id
        or not current_topology.expected_switch_id
        or not current_topology.expected_port_id
    ):
        return _invalid_evidence("current_cmdb_relationship_changed")
    if current_diagnostic is None:
        return _invalid_evidence("current_access_link_diagnostic_unavailable")
    if not (
        current_diagnostic.attachment_id == current_topology.attachment_id
        and current_diagnostic.switch_id == current_topology.expected_switch_id
        and current_diagnostic.port_id == current_topology.expected_port_id
        and current_diagnostic.switch_reachable
        and current_diagnostic.admin_state is AdminState.UP
        and current_diagnostic.operational_state is OperationalState.DOWN
        and current_diagnostic.port_security is PortSecurityState.NORMAL
        and current_diagnostic.configuration is ConfigurationState.EXPECTED
    ):
        return _invalid_evidence("link_no_longer_matches_down_pattern")
    return None
