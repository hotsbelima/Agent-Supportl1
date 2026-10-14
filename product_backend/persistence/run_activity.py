"""Persistence operations for active browser sessions and dispatch eligibility."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from .events import RUN_CLIENT_IDLE_TIMEOUT
from .tables import RunRow


class SqlAlchemyRunActivityRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def heartbeat(self, *, tenant_id: str, run_id: str) -> bool | None:
        now = datetime.now(UTC)
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.scalar(
                    select(RunRow)
                    .where(
                        RunRow.tenant_id == tenant_id,
                        RunRow.run_id == run_id,
                    )
                    .with_for_update()
                )
                if row is None:
                    return None
                if row.dispatch_abandoned_at is not None:
                    return False
                if (
                    row.client_last_seen_at is None
                    or row.client_last_seen_at < now - RUN_CLIENT_IDLE_TIMEOUT
                ):
                    row.dispatch_abandoned_at = now
                    return False
                row.client_last_seen_at = now
                return True


__all__ = ["SqlAlchemyRunActivityRepository"]
