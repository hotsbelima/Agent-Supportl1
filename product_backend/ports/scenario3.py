"""Transaction boundary required by Scenario 3 provider reads."""

from __future__ import annotations

from typing import Protocol

from product_backend.ports.events import ApplicationEventRepository
from product_backend.ports.repositories import EvidenceRepository, RunRepository


class Scenario3ProviderReadUnitOfWork(Protocol):
    runs: RunRepository
    evidence: EvidenceRepository
    events: ApplicationEventRepository

    async def __aenter__(self) -> "Scenario3ProviderReadUnitOfWork": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


__all__ = ["Scenario3ProviderReadUnitOfWork"]
