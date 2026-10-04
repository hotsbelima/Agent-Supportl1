"""Canonical Scenario 1 domain enums for the product backend.

These values are contracts, not presentation labels. UI text and external-system
mapping belong in adapters/application code.
"""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"


class ProposalStatus(StrEnum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    REJECTED = "REJECTED"
    STALE = "STALE"
    EXECUTED = "EXECUTED"


class ApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DiagnosisCode(StrEnum):
    LOCAL_ACCESS_LINK_FAILURE = "LOCAL_ACCESS_LINK_FAILURE"


class ActionType(StrEnum):
    ONSITE_FIELD_VISIT = "ONSITE_FIELD_VISIT"


class EvidenceSourceType(StrEnum):
    CMDB_SNAPSHOT = "CMDB_SNAPSHOT"
    SITE_HEALTH = "SITE_HEALTH"
    ACCESS_LINK_DIAGNOSTIC = "ACCESS_LINK_DIAGNOSTIC"
    INCIDENT_SEARCH = "INCIDENT_SEARCH"
    KB_ARTICLE = "KB_ARTICLE"


class DiagnosticType(StrEnum):
    ACCESS_LINK = "ACCESS_LINK"


class IncidentSearchScope(StrEnum):
    DEVICE = "DEVICE"
    SITE = "SITE"


class HealthState(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class AdminState(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class OperationalState(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class PortSecurityState(StrEnum):
    NORMAL = "NORMAL"
    VIOLATION = "VIOLATION"
    UNKNOWN = "UNKNOWN"


class ConfigurationState(StrEnum):
    EXPECTED = "EXPECTED"
    DRIFTED = "DRIFTED"
    UNKNOWN = "UNKNOWN"


class DeviceResolutionState(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"


class WorkOrderStatus(StrEnum):
    CREATED = "CREATED"
