"""Unit coverage for safe, sticky Gemini primary/failover selection."""

from __future__ import annotations

import asyncio
import os

import pytest

from agent_runtime.gemini_keys import (
    GeminiProviderCoordinator,
    GeminiProviderRateLimited,
    GeminiProvidersUnavailable,
    PRIMARY,
    SECONDARY,
    model_for_provider,
)
from google.genai import Client
from product_api.dispatch import (
    _provider_failure_delay_seconds,
    _scenario2_failure_kind,
)


class _Clock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


async def _provider_for_success(
    coordinator: GeminiProviderCoordinator,
) -> str:
    async with coordinator.bind_invocation() as provider:
        assert coordinator.client_for(provider) is not None
        return provider


def test_primary_is_sticky_and_secondary_is_idle() -> None:
    clients = {PRIMARY: object(), SECONDARY: object()}
    coordinator = GeminiProviderCoordinator(clients=clients)

    assert asyncio.run(_provider_for_success(coordinator)) == PRIMARY


def test_adk_models_are_pinned_to_explicit_provider_clients() -> None:
    clients = {
        PRIMARY: Client(api_key="primary-test-key"),
        SECONDARY: Client(api_key="secondary-test-key"),
    }
    coordinator = GeminiProviderCoordinator(clients=clients)
    primary_model = model_for_provider(
        coordinator,
        PRIMARY,
        "gemini-3.5-flash-lite",
    )
    secondary_model = model_for_provider(
        coordinator,
        SECONDARY,
        "gemini-3.5-flash-lite",
    )

    assert primary_model.client is clients[PRIMARY]
    assert secondary_model.client is clients[SECONDARY]
    assert asyncio.run(_provider_for_success(coordinator)) == PRIMARY


def test_primary_429_fails_over_once_to_secondary() -> None:
    coordinator = GeminiProviderCoordinator(
        clients={PRIMARY: object(), SECONDARY: object()},
        cooldown_seconds=90,
    )

    async def fail_primary() -> None:
        with pytest.raises(GeminiProviderRateLimited) as captured:
            async with coordinator.bind_invocation() as provider:
                assert provider == PRIMARY
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
        assert captured.value.provider == PRIMARY
        assert captured.value.failover_available is True

    asyncio.run(fail_primary())
    assert asyncio.run(_provider_for_success(coordinator)) == SECONDARY


def test_both_429_defer_without_bouncing_between_keys() -> None:
    coordinator = GeminiProviderCoordinator(
        clients={PRIMARY: object(), SECONDARY: object()},
        cooldown_seconds=90,
    )

    async def fail(provider: str) -> GeminiProviderRateLimited:
        with pytest.raises(GeminiProviderRateLimited) as captured:
            async with coordinator.bind_invocation() as selected:
                assert selected == provider
                raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return captured.value

    assert asyncio.run(fail(PRIMARY)).failover_available is True
    secondary_error = asyncio.run(fail(SECONDARY))
    assert secondary_error.failover_available is False
    with pytest.raises(GeminiProvidersUnavailable) as unavailable:
        asyncio.run(_provider_for_success(coordinator))
    assert unavailable.value.retry_after_seconds > 0


def test_primary_returns_after_explicit_cooldown() -> None:
    clock = _Clock()
    coordinator = GeminiProviderCoordinator(
        clients={PRIMARY: object(), SECONDARY: object()},
        cooldown_seconds=90,
        clock=clock,
    )

    async def fail_primary() -> None:
        async with coordinator.bind_invocation():
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    with pytest.raises(GeminiProviderRateLimited):
        asyncio.run(fail_primary())
    assert asyncio.run(_provider_for_success(coordinator)) == SECONDARY
    clock.value += 90
    assert asyncio.run(_provider_for_success(coordinator)) == PRIMARY


def test_parallel_invocations_do_not_mutate_process_environment() -> None:
    clients = {PRIMARY: object(), SECONDARY: object()}
    coordinator = GeminiProviderCoordinator(clients=clients)
    original = os.environ.get("GOOGLE_API_KEY")

    async def invoke() -> tuple[str, object]:
        async with coordinator.bind_invocation() as provider:
            await asyncio.sleep(0)
            return provider, coordinator.client_for(provider)

    async def parallel() -> list[tuple[str, object]]:
        return await asyncio.gather(invoke(), invoke())

    results = asyncio.run(parallel())
    assert results == [(PRIMARY, clients[PRIMARY]), (PRIMARY, clients[PRIMARY])]
    assert os.environ.get("GOOGLE_API_KEY") == original


def test_safe_exception_and_logs_cannot_contain_key_value(caplog: pytest.LogCaptureFixture) -> None:
    secret = "must-never-be-emitted"
    coordinator = GeminiProviderCoordinator(
        clients={PRIMARY: object(), SECONDARY: object()},
    )

    async def fail() -> None:
        async with coordinator.bind_invocation():
            raise RuntimeError(f"429 RESOURCE_EXHAUSTED {secret}")

    with pytest.raises(GeminiProviderRateLimited) as captured:
        asyncio.run(fail())
    assert secret not in str(captured.value)
    assert secret not in caplog.text


def test_durable_retry_uses_one_immediate_primary_failover_then_cooldown() -> None:
    assert _provider_failure_delay_seconds(
        GeminiProviderRateLimited(PRIMARY, 90, True),
        1,
    ) == 0.0
    assert _provider_failure_delay_seconds(
        GeminiProviderRateLimited(SECONDARY, 90, False),
        1,
    ) == 90


def test_provider_503_is_deferred_with_bounded_backoff_and_safe_reason() -> None:
    class ProviderUnavailable(RuntimeError):
        status_code = 503

    provider_error = ProviderUnavailable("private provider response")
    wrapped = RuntimeError("ADK invocation failed")
    wrapped.__cause__ = provider_error

    assert _provider_failure_delay_seconds(wrapped, 1) == 15
    assert _provider_failure_delay_seconds(wrapped, 2) == 30
    assert _provider_failure_delay_seconds(wrapped, 9) == 60
    assert _scenario2_failure_kind(wrapped) == "provider_unavailable"
    assert _scenario2_failure_kind(TimeoutError()) == "invocation_timeout"
