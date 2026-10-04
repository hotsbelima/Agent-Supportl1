"""Read-only managed-PostgreSQL assertions for Phase 4D acceptance.

The helper exposes counts, event metadata and integrity booleans only.  It
does not print DATABASE_URL, event payload values, credentials or hidden model
reasoning.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC
import json
from pathlib import Path
import sys

from sqlalchemy import func, select

# Permit both ``python scripts/phase4d_db_assert.py`` and module execution
# from a Northflank one-off job without requiring the project to be packaged.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_backend.contracts.events import validate_safe_event_payload
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
)
from product_backend.persistence.tables import (
    ApprovalRow,
    ApplicationEventRow,
    ApplicationOutboxRow,
    ExecutedActionRow,
    FieldServiceWorkOrderRow,
)


async def inspect(*, tenant_id: str, run_id: str, proposal_id: str | None) -> dict[str, object]:
    engine = create_engine(DatabaseSettings.from_env())
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            conditions = (
                ApprovalRow.tenant_id == tenant_id,
                ApprovalRow.run_id == run_id,
            )
            if proposal_id:
                conditions = (*conditions, ApprovalRow.proposal_id == proposal_id)

            approvals = await session.scalar(
                select(func.count()).select_from(ApprovalRow).where(*conditions)
            )
            action_conditions = (
                ExecutedActionRow.tenant_id == tenant_id,
                ExecutedActionRow.run_id == run_id,
            )
            work_order_conditions = (
                FieldServiceWorkOrderRow.tenant_id == tenant_id,
                FieldServiceWorkOrderRow.run_id == run_id,
            )
            if proposal_id:
                action_conditions = (*action_conditions, ExecutedActionRow.proposal_id == proposal_id)
                work_order_conditions = (*work_order_conditions, FieldServiceWorkOrderRow.proposal_id == proposal_id)
            actions = await session.scalar(
                select(func.count()).select_from(ExecutedActionRow).where(*action_conditions)
            )
            work_orders = await session.scalar(
                select(func.count())
                .select_from(FieldServiceWorkOrderRow)
                .where(*work_order_conditions)
            )
            events = list(
                (
                    await session.execute(
                        select(ApplicationEventRow)
                        .where(
                            ApplicationEventRow.tenant_id == tenant_id,
                            ApplicationEventRow.run_id == run_id,
                        )
                        .order_by(ApplicationEventRow.seq)
                    )
                ).scalars()
            )
            outbox_count = await session.scalar(
                select(func.count())
                .select_from(ApplicationOutboxRow)
                .where(
                    ApplicationOutboxRow.tenant_id == tenant_id,
                    ApplicationOutboxRow.run_id == run_id,
                )
            )

        sequences = [row.seq for row in events]
        safe_payloads = True
        for row in events:
            try:
                validate_safe_event_payload(row.payload)
            except ValueError:
                safe_payloads = False
                break

        return {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "proposal_id": proposal_id,
            "approval_count": int(approvals or 0),
            "executed_action_count": int(actions or 0),
            "work_order_count": int(work_orders or 0),
            "event_count": len(events),
            "outbox_count": int(outbox_count or 0),
            "event_sequences": sequences,
            "event_types": [row.event_type for row in events],
            "event_timestamps_utc": [
                row.occurred_at.astimezone(UTC).isoformat() for row in events
            ],
            "strictly_monotonic_sequences": sequences == sorted(set(sequences)),
            "safe_event_payloads": safe_payloads,
            "event_outbox_one_to_one": len(events) == int(outbox_count or 0),
        }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--proposal-id")
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(inspect(**vars(arguments))), sort_keys=True))


if __name__ == "__main__":
    main()
