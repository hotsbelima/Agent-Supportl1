"""Read application service for persisted run state."""

from __future__ import annotations

from product_backend.contracts.run_state import RunStateSnapshot
from product_backend.ports.run_state import RunStateQueryPort


class RunStateService:
    def __init__(self, query: RunStateQueryPort) -> None:
        self._query = query

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> RunStateSnapshot | None:
        tenant = tenant_id.strip()
        run = run_id.strip()
        if not tenant or not run:
            return None
        return await self._query.get(
            tenant_id=tenant,
            run_id=run,
        )


__all__ = ["RunStateService"]
