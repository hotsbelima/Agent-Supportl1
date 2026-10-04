"""Pure Scenario 1 read-model rules.

No repositories, providers, ADK, FastAPI or persistence are imported here.
Application services supply already scoped domain records and observations.
"""

from __future__ import annotations

from .enums import EvidenceSourceType, IncidentSearchScope
from .models import (
    AccessLinkDiagnosticSnapshot,
    DeviceTopology,
    Evidence,
    IncidentSearchSnapshot,
    SiteHealthSnapshot,
)


def evidence_knows_device(
    evidence: tuple[Evidence, ...],
    device_id: str,
) -> bool:
    for item in evidence:
        payload = item.payload
        if (
            item.source_type is EvidenceSourceType.CMDB_SNAPSHOT
            and isinstance(payload, DeviceTopology)
            and payload.device_id == device_id
        ):
            return True
        if (
            item.source_type is EvidenceSourceType.SITE_HEALTH
            and isinstance(payload, SiteHealthSnapshot)
            and device_id in (payload.peer_device_id, payload.affected_device_id)
        ):
            return True
        if (
            item.source_type is EvidenceSourceType.INCIDENT_SEARCH
            and isinstance(payload, IncidentSearchSnapshot)
            and payload.scope is IncidentSearchScope.DEVICE
            and payload.entity_id == device_id
        ):
            return True
    return False


def evidence_knows_site(
    evidence: tuple[Evidence, ...],
    site_id: str,
) -> bool:
    for item in evidence:
        payload = item.payload
        if (
            item.source_type is EvidenceSourceType.CMDB_SNAPSHOT
            and isinstance(payload, DeviceTopology)
            and payload.site_id == site_id
        ):
            return True
        if (
            item.source_type is EvidenceSourceType.SITE_HEALTH
            and isinstance(payload, SiteHealthSnapshot)
            and payload.site_id == site_id
        ):
            return True
        if (
            item.source_type is EvidenceSourceType.INCIDENT_SEARCH
            and isinstance(payload, IncidentSearchSnapshot)
            and payload.scope is IncidentSearchScope.SITE
            and payload.entity_id == site_id
        ):
            return True
    return False


def latest_topology_for_attachment(
    evidence: tuple[Evidence, ...],
    attachment_id: str,
) -> DeviceTopology | None:
    candidates = [
        item
        for item in evidence
        if item.source_type is EvidenceSourceType.CMDB_SNAPSHOT
        and isinstance(item.payload, DeviceTopology)
        and item.payload.attachment_id == attachment_id
    ]
    if not candidates:
        return None
    try:
        latest = max(candidates, key=lambda item: item.captured_at)
    except TypeError:
        return None
    return latest.payload


def valid_cmdb_observation(
    *,
    requested_device_id: str,
    topology: DeviceTopology,
    site_is_known: bool,
) -> bool:
    return (
        topology.device_id == requested_device_id
        and bool(topology.site_id.strip())
        and bool(topology.attachment_id.strip())
        and bool(topology.expected_switch_id.strip())
        and bool(topology.expected_port_id.strip())
        and site_is_known
    )


def valid_site_health_observation(
    *,
    requested_site_id: str,
    snapshot: SiteHealthSnapshot,
    affected_device_is_known: bool,
) -> bool:
    return (
        snapshot.site_id == requested_site_id
        and bool(snapshot.peer_device_id.strip())
        and bool(snapshot.affected_device_id.strip())
        and affected_device_is_known
    )


def valid_access_link_observation(
    *,
    requested_target_id: str,
    topology: DeviceTopology,
    snapshot: AccessLinkDiagnosticSnapshot,
) -> bool:
    return (
        snapshot.target_id == requested_target_id
        and snapshot.attachment_id == requested_target_id
        and snapshot.switch_id == topology.expected_switch_id
        and snapshot.port_id == topology.expected_port_id
    )
