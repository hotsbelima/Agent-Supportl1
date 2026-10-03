"""Small immutable fixture and model-visible input for the Phase 1 spike."""

from __future__ import annotations

from typing import Final

MODEL: Final = "gemini-3.5-flash-lite"
APP_NAME: Final = "alp_itsm_phase_1_spike"
USER_ID: Final = "phase-1-spike-user"

DEVICE_ID: Final = "POS-KZN17-03"
ATTACHMENT_ID: Final = "ATT-KZN17-POS03-NIC"

# This is deliberately the complete model-visible starting fact. In particular,
# it does not contain attachment_id or an equivalent value.
INITIAL_EVENT: Final[dict[str, str]] = {
    "incident_id": "INC-P1-SPIKE-001",
    "device_id": DEVICE_ID,
    "symptom": "POS terminal is unreachable",
}
