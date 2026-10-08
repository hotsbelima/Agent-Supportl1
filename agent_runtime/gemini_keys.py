"""Concurrency-safe primary/failover Gemini provider selection."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
import time
from typing import Any, AsyncIterator, Literal

from google.adk.models.google_llm import Gemini
from google.genai import Client


ProviderId = Literal["primary", "secondary"]
PRIMARY: ProviderId = "primary"
SECONDARY: ProviderId = "secondary"
PRIMARY_ENV = "GOOGLE_API_KEY_PRIMARY"
SECONDARY_ENV = "GOOGLE_API_KEY_SECONDARY"
# Canonical names win. These aliases allow a zero-downtime rename from the
# already connected named keys; the legacy single GOOGLE_API_KEY is never read.
_PRIMARY_MIGRATION_ENV = "GOOGLE_API_KEY_HOTS"
_SECONDARY_MIGRATION_ENV = "GOOGLE_API_KEY_Belima"
DEFAULT_GEMINI_PROVIDER_COOLDOWN_SECONDS = 90.0
MAX_GEMINI_PROVIDER_COOLDOWN_SECONDS = 86_400.0
_COOLDOWN_ENV = "GEMINI_PROVIDER_COOLDOWN_SECONDS"


def _positive_float_env(name: str, default: float) -> float:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _is_rate_limited(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "status_code", None) == 429:
            return True
        code = getattr(current, "code", None)
        code_value = code() if callable(code) else code
        code_text = str(getattr(code_value, "name", code_value)).upper()
        text = str(current).upper()
        if "RESOURCE_EXHAUSTED" in code_text or "RESOURCE_EXHAUSTED" in text or "429" in text:
            return True
        current = current.__cause__ or current.__context__
    return False


@dataclass(frozen=True, slots=True)
class GeminiProviderRateLimited(RuntimeError):
    """Safe signal consumed by durable dispatch; contains no key material."""

    provider: ProviderId
    retry_after_seconds: float
    failover_available: bool

    def __str__(self) -> str:
        return (
            f"Gemini provider '{self.provider}' is rate limited; "
            f"retry after {self.retry_after_seconds:.0f}s"
        )


class GeminiProvidersUnavailable(RuntimeError):
    """Both configured providers are cooling down."""

    def __init__(self, retry_after_seconds: float) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"No Gemini provider is currently available; retry after "
            f"{retry_after_seconds:.0f}s"
        )


class GeminiProviderCoordinator:
    """Application-scoped primary/failover state shared by all scenarios."""

    def __init__(
        self,
        *,
        clients: dict[ProviderId, Any] | None = None,
        cooldown_seconds: float | None = None,
        clock: Any = time.monotonic,
    ) -> None:
        self._clock = clock
        requested_cooldown = (
            _positive_float_env(_COOLDOWN_ENV, DEFAULT_GEMINI_PROVIDER_COOLDOWN_SECONDS)
            if cooldown_seconds is None
            else cooldown_seconds
        )
        self._cooldown_seconds = min(
            requested_cooldown,
            MAX_GEMINI_PROVIDER_COOLDOWN_SECONDS,
        )
        if self._cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")
        self._clients: dict[ProviderId, Any] = (
            clients if clients is not None else self._clients_from_environment()
        )
        self._blocked_until: dict[ProviderId, float] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _clients_from_environment() -> dict[ProviderId, Client]:
        values = {
            PRIMARY: os.environ.get(PRIMARY_ENV, "").strip()
            or os.environ.get(_PRIMARY_MIGRATION_ENV, "").strip(),
            SECONDARY: os.environ.get(SECONDARY_ENV, "").strip()
            or os.environ.get(_SECONDARY_MIGRATION_ENV, "").strip(),
        }
        return {
            provider: Client(api_key=value)
            for provider, value in values.items()
            if value
        }

    @property
    def configured(self) -> bool:
        return bool(self._clients)

    @property
    def cooldown_seconds(self) -> float:
        return self._cooldown_seconds

    @property
    def configured_providers(self) -> tuple[ProviderId, ...]:
        return tuple(
            provider for provider in (PRIMARY, SECONDARY) if provider in self._clients
        )

    def client_for(self, provider: ProviderId) -> Any:
        return self._clients[provider]

    async def _select_provider(self) -> ProviderId:
        async with self._lock:
            now = self._clock()
            for provider in (PRIMARY, SECONDARY):
                if provider not in self._clients:
                    continue
                if self._blocked_until.get(provider, 0.0) <= now:
                    self._blocked_until.pop(provider, None)
                    return provider
            retry_after = max(
                0.0,
                min(
                    (deadline - now for deadline in self._blocked_until.values()),
                    default=self._cooldown_seconds,
                ),
            )
        raise GeminiProvidersUnavailable(retry_after)

    async def _mark_rate_limited(self, provider: ProviderId) -> tuple[float, bool]:
        async with self._lock:
            now = self._clock()
            deadline = now + self._cooldown_seconds
            self._blocked_until[provider] = max(
                self._blocked_until.get(provider, 0.0), deadline
            )
            other = SECONDARY if provider == PRIMARY else PRIMARY
            failover_available = (
                other in self._clients
                and self._blocked_until.get(other, 0.0) <= now
            )
            return self._blocked_until[provider] - now, failover_available

    @asynccontextmanager
    async def bind_invocation(self) -> AsyncIterator[ProviderId]:
        """Select one provider for the whole ADK invocation."""
        provider = await self._select_provider()
        try:
            yield provider
        except Exception as error:
            if not _is_rate_limited(error):
                raise
            retry_after, failover_available = await self._mark_rate_limited(provider)
            raise GeminiProviderRateLimited(
                provider=provider,
                retry_after_seconds=retry_after,
                failover_available=failover_available,
            ) from error


def model_for_provider(
    providers: GeminiProviderCoordinator,
    provider: ProviderId,
    model_name: str,
) -> Gemini:
    """Create a model pinned to one explicit client for its full stream."""
    return Gemini(model=model_name, client=providers.client_for(provider))


__all__ = [
    "DEFAULT_GEMINI_PROVIDER_COOLDOWN_SECONDS",
    "GeminiProviderCoordinator",
    "GeminiProviderRateLimited",
    "GeminiProvidersUnavailable",
    "PRIMARY_ENV",
    "SECONDARY_ENV",
    "model_for_provider",
]
