"""Explicit Gemini API-key pool used by the native ADK runtimes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

from google.adk.models.google_llm import Gemini
from google.genai import Client
from pydantic import PrivateAttr


GEMINI_KEY_ENV_NAMES = ("GOOGLE_API_KEY_HOTS", "GOOGLE_API_KEY_Belima")


@dataclass(frozen=True, slots=True)
class GeminiKey:
    """A configured key without exposing its value to callers or logs."""

    env_name: str
    value: str


class _RotatingModels:
    def __init__(self, clients: tuple[Client, ...]) -> None:
        self._clients = clients
        self._next_index = 0

    def _next_client(self) -> Client:
        client = self._clients[self._next_index % len(self._clients)]
        self._next_index = (self._next_index + 1) % len(self._clients)
        return client

    async def generate_content(self, **kwargs: Any) -> Any:
        return await self._next_client().aio.models.generate_content(**kwargs)

    async def generate_content_stream(self, **kwargs: Any) -> Any:
        return await self._next_client().aio.models.generate_content_stream(**kwargs)


class _RotatingAio:
    def __init__(self, clients: tuple[Client, ...]) -> None:
        self.models = _RotatingModels(clients)


class _RotatingClient:
    """Small google-genai client facade accepted by ADK's Gemini model."""

    vertexai = False

    def __init__(self, clients: tuple[Client, ...]) -> None:
        self.aio = _RotatingAio(clients)


class RotatingGemini(Gemini):
    """One ADK model that round-robins requests across configured clients."""

    _rotating_client: Any = PrivateAttr()

    def __init__(self, *, model: str, clients: tuple[Client, ...]) -> None:
        super().__init__(model=model)
        self._rotating_client = _RotatingClient(clients)

    @property
    def api_client(self) -> Any:
        return self._rotating_client

    @property
    def _live_api_client(self) -> Any:
        return self._rotating_client


class GeminiKeyPool:
    """Round-robin pool for the configured Gemini credentials."""

    def __init__(self, keys: tuple[GeminiKey, ...] | None = None) -> None:
        self._keys = keys if keys is not None else self._read_environment()
        self._clients = tuple(Client(api_key=key.value) for key in self._keys)

    @staticmethod
    def _read_environment() -> tuple[GeminiKey, ...]:
        configured: list[GeminiKey] = []
        for env_name in GEMINI_KEY_ENV_NAMES:
            value = os.environ.get(env_name, "").strip()
            if value:
                configured.append(GeminiKey(env_name=env_name, value=value))
        return tuple(configured)

    @property
    def configured(self) -> bool:
        return bool(self._keys)

    @property
    def clients(self) -> tuple[Client, ...]:
        return self._clients


def model_for_pool(pool: GeminiKeyPool, model_name: str) -> Any:
    """Return one key-rotating model, or the default model when unconfigured."""
    if not pool.configured:
        return model_name
    return RotatingGemini(model=model_name, clients=pool.clients)


__all__ = [
    "GEMINI_KEY_ENV_NAMES",
    "GeminiKey",
    "GeminiKeyPool",
    "RotatingGemini",
    "model_for_pool",
]
