"""Read port for persisted product run state."""

from __future__ import annotations

from typing import Protocol

from product_backend.contracts.run_state import RunStateSnapshot


class RunStateQueryPort(Protocol):
    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
    ) -> RunStateSnapshot | None: ...


__all__ = ["RunStateQueryPort"]
