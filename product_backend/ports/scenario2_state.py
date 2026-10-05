"""Read/query ports for persisted Scenario 2 ingestion state."""

from __future__ import annotations

from typing import Protocol

from product_backend.contracts.scenario2_ingestion import (
    Scenario2IngestionStateSnapshot,
)


class Scenario2StateQueryPort(Protocol):
    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> Scenario2IngestionStateSnapshot | None: ...


__all__ = ["Scenario2StateQueryPort"]
