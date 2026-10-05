"""Application read service for persisted Scenario 2 ingestion state."""

from __future__ import annotations

from product_backend.contracts.scenario2_ingestion import (
    Scenario2IngestionStateSnapshot,
)
from product_backend.ports.scenario2_state import Scenario2StateQueryPort


class Scenario2StateService:
    def __init__(self, query: Scenario2StateQueryPort) -> None:
        self._query = query

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> Scenario2IngestionStateSnapshot | None:
        tenant = tenant_id.strip()
        run = run_id.strip()
        if not tenant or not run:
            return None
        return await self._query.get(
            tenant_id=tenant,
            run_id=run,
        )


__all__ = ["Scenario2StateService"]
