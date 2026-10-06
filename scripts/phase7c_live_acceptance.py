"""Live Phase 7C native-ADK continuity and redelivery acceptance.

This uses the real Scenario 2 durable consumer and Gemini runtime. Each canonical
Product fact is ingested in a separate application lifespan so the proof covers
persistent native ADK Session continuity across process-style reconstruction.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import os
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from agent_runtime.scenario2_service import _scenario2_product_event_id
from agent_runtime.sessions import (
    create_database_session_service,
    get_run_session,
)
from product_api.app import create_app
from product_backend.contracts.events import SCENARIO2_AGENT_DISPATCH_TOPIC
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
)
from product_backend.persistence.tables import (
    ActionProposalRow,
    ApplicationEventRow,
    ApplicationOutboxRow,
    FieldServiceWorkOrderRow,
)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for Phase 7C live acceptance")
    return value


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


async def _dispatch_rows(
    tenant_id: str,
    run_id: str,
) -> list[ApplicationOutboxRow]:
    engine = create_engine(DatabaseSettings.from_env())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            rows = (
                await session.execute(
                    select(ApplicationOutboxRow)
                    .where(
                        ApplicationOutboxRow.tenant_id == tenant_id,
                        ApplicationOutboxRow.run_id == run_id,
                        ApplicationOutboxRow.topic
                        == SCENARIO2_AGENT_DISPATCH_TOPIC,
                    )
                    .order_by(ApplicationOutboxRow.event_seq)
                )
            ).scalars().all()
            return list(rows)
    finally:
        await engine.dispose()


async def _external_event_ids(
    tenant_id: str,
    run_id: str,
) -> list[str]:
    engine = create_engine(DatabaseSettings.from_env())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            rows = (
                await session.execute(
                    select(ApplicationEventRow)
                    .where(
                        ApplicationEventRow.tenant_id == tenant_id,
                        ApplicationEventRow.run_id == run_id,
                        ApplicationEventRow.event_type == "external.signal",
                    )
                    .order_by(ApplicationEventRow.seq)
                )
            ).scalars().all()
            return [row.event_id for row in rows]
    finally:
        await engine.dispose()


async def _force_redelivery(
    *,
    tenant_id: str,
    run_id: str,
    outbox_id: str,
) -> None:
    engine = create_engine(DatabaseSettings.from_env())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            await session.execute(
                update(ApplicationOutboxRow)
                .where(
                    ApplicationOutboxRow.tenant_id == tenant_id,
                    ApplicationOutboxRow.run_id == run_id,
                    ApplicationOutboxRow.outbox_id == outbox_id,
                )
                .values(
                    delivered_at=None,
                    available_at=datetime.now(UTC) - timedelta(seconds=1),
                )
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _business_side_effect_counts(
    tenant_id: str,
    run_id: str,
) -> tuple[int, int]:
    engine = create_engine(DatabaseSettings.from_env())
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            proposals = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ActionProposalRow)
                    .where(
                        ActionProposalRow.tenant_id == tenant_id,
                        ActionProposalRow.run_id == run_id,
                    )
                )
                or 0
            )
            work_orders = int(
                await session.scalar(
                    select(func.count())
                    .select_from(FieldServiceWorkOrderRow)
                    .where(
                        FieldServiceWorkOrderRow.tenant_id == tenant_id,
                        FieldServiceWorkOrderRow.run_id == run_id,
                    )
                )
                or 0
            )
            return proposals, work_orders
    finally:
        await engine.dispose()


async def _native_session_correlation(
    *,
    tenant_id: str,
    run_id: str,
) -> tuple[str, list[tuple[str, str]]]:
    engine = create_engine(DatabaseSettings.from_env())
    service = create_database_session_service(engine)
    try:
        session = await get_run_session(
            service,
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if session is None:
            raise AssertionError("persistent native ADK Session was not found")
        correlations: list[tuple[str, str]] = []
        for event in session.events:
            product_event_id = _scenario2_product_event_id(event)
            if product_event_id is None:
                continue
            invocation_id = getattr(event, "invocation_id", None)
            if not isinstance(invocation_id, str) or not invocation_id:
                raise AssertionError(
                    "Scenario 2 ADK user event has no invocation_id"
                )
            correlations.append((product_event_id, invocation_id))
        return session.id, correlations
    finally:
        await engine.dispose()


def _wait_for_delivered(
    *,
    tenant_id: str,
    run_id: str,
    expected_count: int,
    timeout_seconds: float,
    minimum_first_attempts: int = 1,
) -> list[ApplicationOutboxRow]:
    deadline = time.monotonic() + timeout_seconds
    latest: list[ApplicationOutboxRow] = []
    while time.monotonic() < deadline:
        latest = asyncio.run(_dispatch_rows(tenant_id, run_id))
        if (
            len(latest) == expected_count
            and all(row.delivered_at is not None for row in latest)
            and (
                not latest
                or latest[0].attempt_count >= minimum_first_attempts
            )
        ):
            return latest
        time.sleep(0.5)
    raise AssertionError(
        "Scenario 2 durable dispatch did not reach delivered state: "
        f"expected={expected_count} rows={len(latest)}"
    )


def _assert_health(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["scenario2_checkpoint"] == "7C-adk-dispatch"
    assert body["scenario2_ingestion_wired"] is True
    assert body["scenario2_dispatch_consumer_wired"] is True
    assert body["gemini_configured"] is True
    assert body["adk_session_persistence_wired"] is True


def run_acceptance(*, timeout_seconds: float) -> None:
    _require_env("DATABASE_URL")
    _require_env("GOOGLE_API_KEY")
    tenant_id = f"TENANT-7C-LIVE-{uuid4().hex[:10]}"
    run_id: str | None = None

    # Event 1 in application lifespan #1.
    with TestClient(create_app()) as client:
        _assert_health(client)
        started = client.post(
            "/api/v1/scenario-2/runs",
            headers=_headers(tenant_id),
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]

        first = client.post(
            f"/api/v1/scenario-2/runs/{run_id}/simulator/next",
            headers=_headers(tenant_id),
        )
        assert first.status_code == 200, first.text
        assert first.json()["next_index"] == 1
        assert first.json()["ingested"]["dispatch_queued"] is True

        rows = _wait_for_delivered(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_count=1,
            timeout_seconds=timeout_seconds,
        )
        first_outbox_id = rows[0].outbox_id

    assert run_id is not None

    # Force durable redelivery after the first process-style shutdown. The next
    # runtime must reconcile from native ADK history and not create another turn.
    asyncio.run(
        _force_redelivery(
            tenant_id=tenant_id,
            run_id=run_id,
            outbox_id=first_outbox_id,
        )
    )
    with TestClient(create_app()) as client:
        _assert_health(client)
        _wait_for_delivered(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_count=1,
            timeout_seconds=timeout_seconds,
            minimum_first_attempts=2,
        )

    session_id, first_correlations = asyncio.run(
        _native_session_correlation(
            tenant_id=tenant_id,
            run_id=run_id,
        )
    )
    assert session_id == run_id
    assert len(first_correlations) == 1

    # Event 2 in application lifespan #3.
    with TestClient(create_app()) as client:
        _assert_health(client)
        second = client.post(
            f"/api/v1/scenario-2/runs/{run_id}/simulator/next",
            headers=_headers(tenant_id),
        )
        assert second.status_code == 200, second.text
        assert second.json()["next_index"] == 2
        _wait_for_delivered(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_count=2,
            timeout_seconds=timeout_seconds,
            minimum_first_attempts=2,
        )

    proposals, work_orders = asyncio.run(
        _business_side_effect_counts(tenant_id, run_id)
    )
    assert proposals == 0
    assert work_orders == 0

    # Event 3 in application lifespan #4.
    with TestClient(create_app()) as client:
        _assert_health(client)
        third = client.post(
            f"/api/v1/scenario-2/runs/{run_id}/simulator/next",
            headers=_headers(tenant_id),
        )
        assert third.status_code == 200, third.text
        assert third.json()["complete"] is True
        assert third.json()["next_index"] == 3
        _wait_for_delivered(
            tenant_id=tenant_id,
            run_id=run_id,
            expected_count=3,
            timeout_seconds=timeout_seconds,
            minimum_first_attempts=2,
        )

    event_ids = asyncio.run(_external_event_ids(tenant_id, run_id))
    assert len(event_ids) == 3

    session_id, correlations = asyncio.run(
        _native_session_correlation(
            tenant_id=tenant_id,
            run_id=run_id,
        )
    )
    assert session_id == run_id
    assert [product_event_id for product_event_id, _ in correlations] == event_ids
    invocation_ids = [invocation_id for _, invocation_id in correlations]
    assert len(invocation_ids) == 3
    assert len(set(invocation_ids)) == 3

    proposals, work_orders = asyncio.run(
        _business_side_effect_counts(tenant_id, run_id)
    )
    assert proposals == 0
    assert work_orders == 0

    rows = asyncio.run(_dispatch_rows(tenant_id, run_id))
    assert len(rows) == 3
    assert all(row.delivered_at is not None for row in rows)
    assert rows[0].attempt_count >= 2

    print(
        "PHASE7C_LIVE_PASS",
        {
            "run_id": run_id,
            "session_id": session_id,
            "product_event_ids": event_ids,
            "invocation_ids": invocation_ids,
            "first_event_attempts": rows[0].attempt_count,
            "process_style_restarts": 3,
            "independent_invocations": 3,
            "same_native_session": True,
            "duplicate_invocation_on_redelivery": False,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=float, default=150.0)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive")
    run_acceptance(timeout_seconds=args.timeout_seconds)


if __name__ == "__main__":
    main()
