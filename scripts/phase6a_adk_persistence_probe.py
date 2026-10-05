"""Separate-process probe for the Phase 6A ADK persistence gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from uuid import uuid4

from google.adk.events import Event

from agent_runtime.sessions import create_database_session_service
from agent_runtime.sessions import ensure_run_session
from agent_runtime.sessions import get_run_session
from product_backend.persistence.database import DatabaseSettings
from product_backend.persistence.database import create_engine


async def _run(mode: str, tenant_id: str, run_id: str) -> int:
    engine = create_engine(DatabaseSettings.from_env())
    service = create_database_session_service(engine)
    try:
        await service.prepare_tables()

        if mode == "append":
            session = await ensure_run_session(
                service,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            await service.append_event(
                session,
                Event(
                    invocation_id=f"INV-6A-PROCESS-{uuid4().hex[:12]}",
                    author="phase6a-process-probe",
                    state={"runtime_checkpoint": "persisted-across-process"},
                ),
            )

        session = await get_run_session(
            service,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if session is None:
            print(json.dumps({"found": False}))
            return 3

        print(
            json.dumps(
                {
                    "found": True,
                    "session_id": session.id,
                    "app_name": session.app_name,
                    "user_id": session.user_id,
                    "state": session.state,
                    "events": [
                        {
                            "author": event.author,
                            "invocation_id": event.invocation_id,
                            "state_delta": dict(event.actions.state_delta),
                        }
                        for event in session.events
                    ],
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inspect", "append"))
    parser.add_argument("tenant_id")
    parser.add_argument("run_id")
    args = parser.parse_args()

    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required")

    return asyncio.run(_run(args.mode, args.tenant_id, args.run_id))


if __name__ == "__main__":
    raise SystemExit(main())
