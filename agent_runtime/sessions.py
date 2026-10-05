"""Native Google ADK session persistence and Product Run correlation.

ADK owns runtime Session/Event/state persistence. Product owns business state.
The only correlation needed in Phase 6A is deterministic:

    ADK app_name   = ADK_APP_NAME
    ADK user_id    = Product tenant_id
    ADK session_id = Product run_id

No Product entity is copied into ADK state and no second session store exists.
"""

from __future__ import annotations

from google.adk.sessions import DatabaseSessionService
from google.adk.sessions import Session
from sqlalchemy.ext.asyncio import AsyncEngine


ADK_APP_NAME = "autonomous-l1-incident-agent"


def create_database_session_service(
    engine: AsyncEngine,
) -> DatabaseSessionService:
    """Reuse the Product AsyncEngine without creating a second DB pool."""
    return DatabaseSessionService(db_engine=engine)


async def get_run_session(
    session_service: DatabaseSessionService,
    *,
    tenant_id: str,
    run_id: str,
) -> Session | None:
    """Return the ADK session deterministically correlated to a Product Run."""
    return await session_service.get_session(
        app_name=ADK_APP_NAME,
        user_id=tenant_id,
        session_id=run_id,
    )


async def ensure_run_session(
    session_service: DatabaseSessionService,
    *,
    tenant_id: str,
    run_id: str,
) -> Session:
    """Create the ADK session once, otherwise return the persisted session."""
    existing = await get_run_session(
        session_service,
        tenant_id=tenant_id,
        run_id=run_id,
    )
    if existing is not None:
        return existing

    return await session_service.create_session(
        app_name=ADK_APP_NAME,
        user_id=tenant_id,
        session_id=run_id,
        state={},
    )
