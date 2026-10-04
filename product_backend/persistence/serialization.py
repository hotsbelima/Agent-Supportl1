"""Lossless JSONB mapping for typed Evidence payloads."""

from __future__ import annotations

from typing import Any

from product_backend.domain.enums import (
    ActionType,
    AdminState,
    ConfigurationState,
    DiagnosisCode,
    EvidenceSourceType,
    HealthState,
    IncidentSearchScope,
    OperationalState,
    PortSecurityState,
)
from product_backend.domain.models import (
    AccessLinkDiagnosticSnapshot,
    DeviceTopology,
    EvidencePayload,
    IncidentSearchSnapshot,
    KbArticle,
    SiteHealthSnapshot,
)


def serialize_evidence_payload(
    source_type: EvidenceSourceType,
    payload: EvidencePayload,
) -> dict[str, Any]:
    if source_type is EvidenceSourceType.CMDB_SNAPSHOT:
        if not isinstance(payload, DeviceTopology):
            raise ValueError("CMDB_SNAPSHOT requires DeviceTopology payload")
        return {
            "device_id": payload.device_id,
            "site_id": payload.site_id,
            "attachment_id": payload.attachment_id,
            "device_type": payload.device_type,
            "expected_switch_id": payload.expected_switch_id,
            "expected_port_id": payload.expected_port_id,
        }

    if source_type is EvidenceSourceType.SITE_HEALTH:
        if not isinstance(payload, SiteHealthSnapshot):
            raise ValueError("SITE_HEALTH requires SiteHealthSnapshot payload")
        return {
            "site_id": payload.site_id,
            "site_network": payload.site_network.value,
            "payment_service": payload.payment_service.value,
            "peer_device_id": payload.peer_device_id,
            "peer_reachable": payload.peer_reachable,
            "affected_device_id": payload.affected_device_id,
            "affected_device_reachable": payload.affected_device_reachable,
        }

    if source_type is EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC:
        if not isinstance(payload, AccessLinkDiagnosticSnapshot):
            raise ValueError(
                "ACCESS_LINK_DIAGNOSTIC requires AccessLinkDiagnosticSnapshot payload"
            )
        return {
            "target_id": payload.target_id,
            "attachment_id": payload.attachment_id,
            "switch_id": payload.switch_id,
            "port_id": payload.port_id,
            "switch_reachable": payload.switch_reachable,
            "admin_state": payload.admin_state.value,
            "operational_state": payload.operational_state.value,
            "port_security": payload.port_security.value,
            "configuration": payload.configuration.value,
        }

    if source_type is EvidenceSourceType.INCIDENT_SEARCH:
        if not isinstance(payload, IncidentSearchSnapshot):
            raise ValueError(
                "INCIDENT_SEARCH requires IncidentSearchSnapshot payload"
            )
        return {
            "scope": payload.scope.value,
            "entity_id": payload.entity_id,
            "open_incident_ids": list(payload.open_incident_ids),
        }

    if source_type is EvidenceSourceType.KB_ARTICLE:
        if not isinstance(payload, KbArticle):
            raise ValueError("KB_ARTICLE requires KbArticle payload")
        return {
            "article_id": payload.article_id,
            "title": payload.title,
            "approved": payload.approved,
            "diagnosis_codes": [value.value for value in payload.diagnosis_codes],
            "allowed_actions": [value.value for value in payload.allowed_actions],
        }

    raise ValueError(f"Unsupported evidence source type: {source_type.value}")


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _require_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise ValueError(f"{key} must be a boolean")
    return value


def _require_str_tuple(payload: dict[str, Any], key: str) -> tuple[str, ...]:
    value = payload[key]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be an array of strings")
    return tuple(value)


def deserialize_evidence_payload(
    source_type: EvidenceSourceType,
    payload: dict[str, Any],
) -> EvidencePayload:
    if source_type is EvidenceSourceType.CMDB_SNAPSHOT:
        return DeviceTopology(
            device_id=_require_str(payload, "device_id"),
            site_id=_require_str(payload, "site_id"),
            attachment_id=_require_str(payload, "attachment_id"),
            device_type=_require_str(payload, "device_type"),
            expected_switch_id=_require_str(payload, "expected_switch_id"),
            expected_port_id=_require_str(payload, "expected_port_id"),
        )

    if source_type is EvidenceSourceType.SITE_HEALTH:
        return SiteHealthSnapshot(
            site_id=str(payload["site_id"]),
            site_network=HealthState(_require_str(payload, "site_network")),
            payment_service=HealthState(_require_str(payload, "payment_service")),
            peer_device_id=_require_str(payload, "peer_device_id"),
            peer_reachable=_require_bool(payload, "peer_reachable"),
            affected_device_id=_require_str(payload, "affected_device_id"),
            affected_device_reachable=_require_bool(payload, "affected_device_reachable"),
        )

    if source_type is EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC:
        return AccessLinkDiagnosticSnapshot(
            target_id=_require_str(payload, "target_id"),
            attachment_id=str(payload["attachment_id"]),
            switch_id=_require_str(payload, "switch_id"),
            port_id=_require_str(payload, "port_id"),
            switch_reachable=_require_bool(payload, "switch_reachable"),
            admin_state=AdminState(_require_str(payload, "admin_state")),
            operational_state=OperationalState(_require_str(payload, "operational_state")),
            port_security=PortSecurityState(_require_str(payload, "port_security")),
            configuration=ConfigurationState(_require_str(payload, "configuration")),
        )

    if source_type is EvidenceSourceType.INCIDENT_SEARCH:
        return IncidentSearchSnapshot(
            scope=IncidentSearchScope(_require_str(payload, "scope")),
            entity_id=_require_str(payload, "entity_id"),
            open_incident_ids=_require_str_tuple(
                payload,
                "open_incident_ids",
            ),
        )

    if source_type is EvidenceSourceType.KB_ARTICLE:
        return KbArticle(
            article_id=_require_str(payload, "article_id"),
            title=_require_str(payload, "title"),
            approved=_require_bool(payload, "approved"),
            diagnosis_codes=tuple(
                DiagnosisCode(value)
                for value in _require_str_tuple(payload, "diagnosis_codes")
            ),
            allowed_actions=tuple(
                ActionType(value)
                for value in _require_str_tuple(payload, "allowed_actions")
            ),
        )

    raise ValueError(f"Unsupported evidence source type: {source_type.value}")
