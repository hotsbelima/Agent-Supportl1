from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agent_runtime.tools import Scenario1AdkTools
from product_api.app import create_app
from product_api.scenario1_fixture import (
    AFFECTED_DEVICE_ID,
    ATTACHMENT_ID,
    INCIDENT_ID,
    SITE_ID,
    Scenario1FixtureSources,
)
from product_backend.adapters.tool_adapters import DefaultScenario1ToolAdapter
from product_backend.application.field_visit import FieldVisitProposalService
from product_backend.application.read_tools import (
    EvidenceTtlPolicy,
    Scenario1ReadToolService,
)
from product_backend.application.run_lifecycle import Scenario1RunStartService
from product_backend.application.run_state import RunStateService
from product_backend.domain.enums import (
    EvidenceSourceType,
    ProposalStatus,
    RunStatus,
)
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.run_state import SqlAlchemyRunStateQuery
from product_backend.persistence.uow import (
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyRunStartUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    return normalize_database_url(value)


def test_all_six_adk_wrappers_reach_existing_product_services_and_persistence():
    async def scenario() -> None:
        tenant_id = f"TENANT-6B-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        fixture = Scenario1FixtureSources()

        start_service = Scenario1RunStartService(
            lambda: SqlAlchemyRunStartUnitOfWork(factory)
        )
        read_service = Scenario1ReadToolService(
            read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
            cmdb=fixture,
            monitoring=fixture,
            itsm=fixture,
            kb=fixture,
            ttl_policy=EvidenceTtlPolicy(
                site_health=timedelta(minutes=5),
                access_link_diagnostic=timedelta(minutes=2),
            ),
        )
        proposal_service = FieldVisitProposalService(
            lambda: SqlAlchemyProposalCreationUnitOfWork(factory)
        )
        adapter = DefaultScenario1ToolAdapter(
            read_service=read_service,
            proposal_service=proposal_service,
        )
        tools = Scenario1AdkTools(adapter)
        state_service = RunStateService(SqlAlchemyRunStateQuery(factory))

        try:
            started = await start_service.start(
                tenant_id=tenant_id,
                bootstrap=fixture.bootstrap(),
            )
            run_id = started.run.run_id
            tool_context = SimpleNamespace(
                user_id=tenant_id,
                session=SimpleNamespace(id=run_id),
            )

            incidents = await tools.search_incidents(
                scope="DEVICE",
                entity_id=AFFECTED_DEVICE_ID,
                tool_context=tool_context,
            )
            kb = await tools.search_kb(
                query="local access link failure physical path inspection",
                tool_context=tool_context,
            )
            site = await tools.get_site_health(
                site_id=SITE_ID,
                tool_context=tool_context,
            )
            device = await tools.get_device(
                device_id=AFFECTED_DEVICE_ID,
                tool_context=tool_context,
            )
            diagnostic = await tools.run_diagnostic(
                diagnostic_type="ACCESS_LINK",
                target_id=device["attachment_id"],
                tool_context=tool_context,
            )

            for result in (incidents, kb, site, device, diagnostic):
                assert result["ok"] is True

            assert incidents["snapshot"]["open_incident_ids"] == [INCIDENT_ID]
            assert device["attachment_id"] == ATTACHMENT_ID
            assert diagnostic["target_id"] == device["attachment_id"]
            assert kb["articles"][0]["article_id"] == "KB-LOCAL-LINK"
            assert kb["articles"][0]["approved"] is True

            evidence_ids = [
                device["evidence"]["evidence_id"],
                site["evidence"]["evidence_id"],
                diagnostic["evidence"]["evidence_id"],
                kb["evidence"][0]["evidence_id"],
            ]
            proposal = await tools.propose_field_visit(
                incident_id=INCIDENT_ID,
                device_id=AFFECTED_DEVICE_ID,
                diagnosis="LOCAL_ACCESS_LINK_FAILURE",
                evidence_ids=evidence_ids,
                rationale=(
                    "CMDB, site health, access-link diagnostic and approved KB "
                    "support an onsite physical-path inspection."
                ),
                tool_context=tool_context,
            )
            assert proposal["ok"] is True
            assert proposal["proposal"]["status"] == ProposalStatus.PENDING_APPROVAL.value

            snapshot = await state_service.get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert snapshot is not None
            assert snapshot.run.status is RunStatus.WAITING_APPROVAL
            assert len(snapshot.proposals) == 1
            assert snapshot.proposals[0].status is ProposalStatus.PENDING_APPROVAL

            evidence_types = {item.source_type for item in snapshot.evidence}
            assert EvidenceSourceType.CMDB_SNAPSHOT in evidence_types
            assert EvidenceSourceType.SITE_HEALTH in evidence_types
            assert EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC in evidence_types
            assert EvidenceSourceType.INCIDENT_SEARCH in evidence_types
            assert EvidenceSourceType.KB_ARTICLE in evidence_types
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_agent_invoke_fails_safe_when_gemini_key_is_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    tenant_id = f"TENANT-6B-NOKEY-{uuid4().hex[:8]}"
    headers = {"X-Tenant-ID": tenant_id}

    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["adk_wired"] is True
        assert health.json()["gemini_configured"] is False

        started = client.post(
            "/api/v1/scenario-1/runs",
            headers=headers,
        )
        assert started.status_code == 201, started.text
        run_id = started.json()["run"]["run_id"]

        invoked = client.post(
            f"/api/v1/runs/{run_id}/agent/invoke",
            headers=headers,
        )
        assert invoked.status_code == 503
        assert invoked.json() == {
            "error": {
                "code": "GEMINI_NOT_CONFIGURED",
                "message": (
                    "Gemini credentials are not configured for the agent runtime."
                ),
                "retryable": False,
                "details": {},
            }
        }

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=headers,
        )
        assert state.status_code == 200
        assert state.json()["run"]["status"] == "ACTIVE"
