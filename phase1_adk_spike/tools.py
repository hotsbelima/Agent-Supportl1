"""The only two model-visible tools in the Phase 1 spike.

They are pure read-only fixture lookups.  The attachment identifier exists only
in get_device's response; it is never added to the initial input or injected
into the second tool call by application code.
"""

from __future__ import annotations

from typing import Any

from .contracts import ATTACHMENT_ID, DEVICE_ID


def get_device(device_id: str) -> dict[str, Any]:
    """Look up one device by its device_id and return its attachment_id.

    Use this before a diagnostic when the request gives a device_id but not an
    attachment_id. This function is read-only.
    """
    if device_id != DEVICE_ID:
        return {
            "ok": False,
            "error": {"code": "NOT_FOUND", "message": "Device not found"},
        }

    return {
        "ok": True,
        "device_id": DEVICE_ID,
        "attachment_id": ATTACHMENT_ID,
        "device_type": "POS_TERMINAL",
        "site_id": "SITE-KZN-17",
    }


def run_diagnostic(attachment_id: str) -> dict[str, Any]:
    """Run a read-only diagnostic for an attachment_id returned by get_device.

    Do not guess an attachment_id. This function is read-only and does not
    alter the fixture or any external system.
    """
    if attachment_id != ATTACHMENT_ID:
        return {
            "ok": False,
            "error": {"code": "NOT_FOUND", "message": "Attachment not found"},
        }

    return {
        "ok": True,
        "attachment_id": ATTACHMENT_ID,
        "diagnostic": "LINK_DOWN",
        "observed_state": "network interface has no carrier",
    }
