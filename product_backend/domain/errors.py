"""Typed, safe error taxonomy for Scenario 1 boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
    # Input/context
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"

    # CMDB / topology
    DEVICE_NOT_FOUND = "DEVICE_NOT_FOUND"
    SITE_NOT_FOUND = "SITE_NOT_FOUND"
    ATTACHMENT_NOT_FOUND = "ATTACHMENT_NOT_FOUND"

    # Monitoring / diagnostics
    SITE_HEALTH_UNAVAILABLE = "SITE_HEALTH_UNAVAILABLE"
    DIAGNOSTIC_UNAVAILABLE = "DIAGNOSTIC_UNAVAILABLE"
    UNSUPPORTED_DIAGNOSTIC = "UNSUPPORTED_DIAGNOSTIC"

    # ITSM / KB
    INCIDENT_NOT_FOUND = "INCIDENT_NOT_FOUND"
    INCIDENT_SEARCH_UNAVAILABLE = "INCIDENT_SEARCH_UNAVAILABLE"
    KB_UNAVAILABLE = "KB_UNAVAILABLE"

    # Shared upstream boundary (preserved from Phase 2)
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"

    # Evidence / proposal
    EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
    EVIDENCE_CONTEXT_MISMATCH = "EVIDENCE_CONTEXT_MISMATCH"
    INSUFFICIENT_OR_INVALID_EVIDENCE = "INSUFFICIENT_OR_INVALID_EVIDENCE"
    INVALID_PROPOSAL = "INVALID_PROPOSAL"
    PROPOSAL_NOT_FOUND = "PROPOSAL_NOT_FOUND"
    PROPOSAL_NOT_PENDING = "PROPOSAL_NOT_PENDING"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"


@dataclass(frozen=True, slots=True)
class DomainError:
    """A typed error safe to expose at tool/API boundaries.

    `details` must contain identifiers or validation facts only. Raw exceptions,
    credentials, stack traces and provider payloads do not belong here.
    """

    code: ErrorCode
    message: str
    retryable: bool = False
    details: tuple[tuple[str, str], ...] = ()
