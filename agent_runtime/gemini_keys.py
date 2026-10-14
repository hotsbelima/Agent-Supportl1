"""Concurrency-safe primary/failover Gemini provider selection."""

from __future__ import annotations

import asyncio
from contextlib import aclosing, asynccontextmanager
import contextvars
from dataclasses import dataclass
from functools import wraps
import json
import logging
import os
import time
from uuid import uuid4
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
logger = logging.getLogger(__name__)

_GEMINI_CALL_CONTEXT: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("gemini_call_context", default=None)
)


def diagnostic_invocation(function: Any) -> Any:
    """Keep context creation/reset in one coroutine, never across generator yields."""
    @wraps(function)
    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        previous = _GEMINI_CALL_CONTEXT.get() or {}
        fact = kwargs.get("operational_fact", {})
        context = {
            "run_id": kwargs.get("run_id", previous.get("run_id")),
            "event_seq": fact.get("event", {}).get("event_seq", previous.get("event_seq")),
            "attempt": previous.get("attempt"),
            "call_seq": 0,
        }
        token = _GEMINI_CALL_CONTEXT.set(context)
        try:
            return await function(*args, **kwargs)
        except Exception as error:
            logger.warning(
                "Agent invocation error run_id=%s event_seq=%s attempt=%s "
                "invocation_id=%s last_tool=%s error=%s",
                context.get("run_id"), context.get("event_seq"), context.get("attempt"),
                context.get("invocation_id"), context.get("last_tool"), error_metadata(error),
            )
            raise
        finally:
            _GEMINI_CALL_CONTEXT.reset(token)
    return wrapped


def update_diagnostic_context(**values: Any) -> None:
    context = _GEMINI_CALL_CONTEXT.get()
    if context is not None:
        context.update(values)


def error_metadata(error: BaseException) -> dict[str, Any]:
    """Only types and numeric/canonical codes; never exception messages or repr."""
    chain = []
    status = None
    code = None
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        chain.append(type(current).__name__)
        for field in ("status_code", "code"):
            value = getattr(current, field, None)
            if isinstance(value, int):
                status = value if 100 <= value <= 599 else status
                code = value
        current = current.__cause__ or current.__context__
    return {"error_types": ">".join(chain), "status_code": status, "code": code}


def _request_metrics(llm_request: Any) -> tuple[int, int, int, int]:
    """Return safe shape/size metrics without returning prompt contents."""
    contents = list(getattr(llm_request, "contents", None) or [])
    part_count = 0
    text_chars = 0
    for content in contents:
        parts = list(getattr(content, "parts", None) or [])
        part_count += len(parts)
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                text_chars += len(text)
            for field in ("function_call", "function_response"):
                value = getattr(part, field, None)
                if value is not None:
                    try:
                        text_chars += len(json.dumps(value, default=str, ensure_ascii=False))
                    except Exception:
                        text_chars += len(str(value))
    try:
        serialized = llm_request.model_dump_json(
            exclude_none=True, exclude={"config": {"http_options"}, "live_connect_config": True}
        )
        request_bytes = len(serialized.encode("utf-8"))
    except Exception:
        request_bytes = 0
    return len(contents), part_count, text_chars, request_bytes


def _usage_metrics(response: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return None, None, None
    return (
        getattr(usage, "prompt_token_count", None),
        getattr(usage, "candidates_token_count", None),
        getattr(usage, "total_token_count", None),
    )


class InstrumentedGemini(Gemini):
    """Gemini model with bounded request/response diagnostics."""

    async def generate_content_async(self, llm_request: Any, stream: bool = False):
        context = _GEMINI_CALL_CONTEXT.get() or {}
        context["call_seq"] = context.get("call_seq", 0) + 1
        context = dict(context)
        request_id = uuid4().hex
        prefix = (
            f"request_id={request_id} run_id={context.get('run_id')} "
            f"event_seq={context.get('event_seq')} attempt={context.get('attempt')} "
            f"call_seq={context.get('call_seq')} phase={context.get('last_tool', 'signal')}"
        )
        content_count, part_count, text_chars, request_bytes = _request_metrics(
            llm_request
        )
        started_at = time.monotonic()
        response_count = 0
        prompt_tokens: int | None = None
        output_tokens: int | None = None
        total_tokens: int | None = None
        logger.info(
            "Gemini request start %s run_id=%s event_seq=%s attempt=%s "
            "invocation_id=%s provider=%s model=%s stream=%s contents=%s "
            "parts=%s text_chars=%s request_bytes_estimate=%s",
            prefix,
            context.get("run_id"),
            context.get("event_seq"),
            context.get("attempt"),
            context.get("invocation_id"),
            context.get("provider", "unconfigured"),
            getattr(llm_request, "model", None),
            stream,
            content_count,
            part_count,
            text_chars,
            request_bytes,
        )
        try:
            async with aclosing(super().generate_content_async(llm_request, stream=stream)) as responses:
                async for response in responses:
                    response_count += 1
                    usage = _usage_metrics(response)
                    if usage[0] is not None:
                        prompt_tokens, output_tokens, total_tokens = usage
                    yield response
        except asyncio.CancelledError:
            logger.info("Gemini request cancelled %s duration_ms=%.1f", prefix,
                        (time.monotonic() - started_at) * 1000)
            raise
        except Exception as error:
            logger.warning(
                "Gemini request error %s run_id=%s event_seq=%s attempt=%s "
                "invocation_id=%s provider=%s model=%s stream=%s duration_ms=%.1f "
                "responses=%s status_code=%s error_type=%s code=%s",
                prefix,
                context.get("run_id"),
                context.get("event_seq"),
                context.get("attempt"),
                context.get("invocation_id"),
                context.get("provider", "unconfigured"),
                getattr(llm_request, "model", None),
                stream,
                (time.monotonic() - started_at) * 1000,
                response_count,
                error_metadata(error)["status_code"],
                error_metadata(error)["error_types"],
                error_metadata(error)["code"],
            )
            raise
        else:
            logger.info(
                "Gemini request success %s run_id=%s event_seq=%s attempt=%s "
                "invocation_id=%s provider=%s model=%s stream=%s duration_ms=%.1f "
                "responses=%s prompt_tokens=%s output_tokens=%s total_tokens=%s",
                prefix,
                context.get("run_id"),
                context.get("event_seq"),
                context.get("attempt"),
                context.get("invocation_id"),
                context.get("provider", "unconfigured"),
                getattr(llm_request, "model", None),
                stream,
                (time.monotonic() - started_at) * 1000,
                response_count,
                prompt_tokens,
                output_tokens,
                total_tokens,
            )


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


def _is_temporarily_unavailable(error: BaseException) -> bool:
    """Recognize provider 503/UNAVAILABLE through ADK exception wrappers."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "status_code", None) == 503:
            return True
        code = getattr(current, "code", None)
        code_value = code() if callable(code) else code
        code_text = str(getattr(code_value, "name", code_value)).upper()
        text = str(current).upper()
        if "UNAVAILABLE" in code_text or "UNAVAILABLE" in text or "503" in text:
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


@dataclass(frozen=True, slots=True)
class GeminiProviderUnavailable(RuntimeError):
    """Safe signal for a temporarily unavailable Gemini provider."""

    provider: ProviderId
    retry_after_seconds: float
    failover_available: bool

    def __str__(self) -> str:
        return (
            f"Gemini provider '{self.provider}' is unavailable; "
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

    async def _mark_provider_unavailable(
        self,
        provider: ProviderId,
    ) -> tuple[float, bool]:
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
            if _is_rate_limited(error):
                retry_after, failover_available = await self._mark_provider_unavailable(
                    provider
                )
                raise GeminiProviderRateLimited(
                    provider=provider,
                    retry_after_seconds=retry_after,
                    failover_available=failover_available,
                ) from error
            if _is_temporarily_unavailable(error):
                retry_after, failover_available = await self._mark_provider_unavailable(
                    provider
                )
                raise GeminiProviderUnavailable(
                    provider=provider,
                    retry_after_seconds=retry_after,
                    failover_available=failover_available,
                ) from error
            raise


def model_for_provider(
    providers: GeminiProviderCoordinator,
    provider: ProviderId,
    model_name: str,
) -> Gemini:
    """Create a model pinned to one explicit client for its full stream."""
    return InstrumentedGemini(model=model_name, client=providers.client_for(provider))


__all__ = [
    "DEFAULT_GEMINI_PROVIDER_COOLDOWN_SECONDS",
    "GeminiProviderCoordinator",
    "GeminiProviderRateLimited",
    "GeminiProviderUnavailable",
    "GeminiProvidersUnavailable",
    "PRIMARY_ENV",
    "SECONDARY_ENV",
    "diagnostic_invocation",
    "error_metadata",
    "update_diagnostic_context",
    "model_for_provider",
]
