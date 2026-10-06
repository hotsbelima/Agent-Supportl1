"""Small portfolio-grade public-demo safety helpers for Phase 9B.

This intentionally avoids production auth, distributed rate limiting, or a
separate policy framework. Public demo mode fixes tenant context server-side,
hides internal controls, and applies a process-local cooldown to new runs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import os
import re
import time
from typing import Callable


_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"", "0", "false", "no", "off"}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise RuntimeError(f"{name} must be a boolean value")


def _positive_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive number") from exc
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"{name} must be a finite positive number")
    return value


@dataclass(frozen=True, slots=True)
class PublicDemoSettings:
    enabled: bool = False
    tenant_id: str = "TENANT-8OCT"
    run_start_cooldown_seconds: float = 8.0

    def __post_init__(self) -> None:
        if not _TENANT_PATTERN.fullmatch(self.tenant_id):
            raise ValueError("Public demo tenant ID is invalid")
        if (
            not math.isfinite(self.run_start_cooldown_seconds)
            or self.run_start_cooldown_seconds <= 0
        ):
            raise ValueError("Public demo cooldown must be a finite positive number")

    @classmethod
    def from_env(cls) -> "PublicDemoSettings":
        return cls(
            enabled=_bool_env("PUBLIC_DEMO", False),
            tenant_id=os.environ.get("PUBLIC_DEMO_TENANT_ID", "TENANT-8OCT").strip(),
            run_start_cooldown_seconds=_positive_float_env(
                "PUBLIC_DEMO_COOLDOWN_SECONDS",
                8.0,
            ),
        )


class RunStartCooldown:
    """Simple process-local cooldown suitable for a single public demo service."""

    def __init__(
        self,
        cooldown_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(cooldown_seconds) or cooldown_seconds <= 0:
            raise ValueError("Cooldown must be a finite positive number")
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._last_allowed_at: float | None = None
        self._lock = asyncio.Lock()

    async def reserve(self) -> int | None:
        """Return retry-after seconds when blocked, otherwise reserve and return None."""

        async with self._lock:
            now = self._clock()
            if self._last_allowed_at is not None:
                remaining = self._cooldown_seconds - (now - self._last_allowed_at)
                if remaining > 0:
                    return max(1, math.ceil(remaining))
            self._last_allowed_at = now
            return None


def release_sha_from_env() -> str:
    for name in (
        "RELEASE_SHA",
        "GIT_COMMIT_SHA",
        "VERCEL_GIT_COMMIT_SHA",
        "COMMIT_SHA",
    ):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return "unknown"


__all__ = [
    "PublicDemoSettings",
    "RunStartCooldown",
    "release_sha_from_env",
]
