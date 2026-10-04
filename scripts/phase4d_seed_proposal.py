"""Create one canonical Scenario 1 pending proposal for managed acceptance.

This is a controlled, non-HTTP helper.  It intentionally uses the same
fixture, evidence persistence unit of work and proposal service as the product
path instead of inserting rows directly.  It prints only safe identifiers and
status; DATABASE_URL is never displayed.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
from uuid import uuid4

# Permit both ``python scripts/phase4d_seed_proposal.py`` and module execution
# from a Northflank one-off job without requiring the project to be packaged.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from product_api.scenario1_fixture import (
    AFFECTED_DEVICE_ID,
    ATTACHMENT_ID,
    INCIDENT_ID,
    SITE_ID,
    Scenario1FixtureSources,
)
from product_backend.application.field_visit import FieldVisitProposalService
from product_backend.contracts.tools import ProposeFieldVisitRequest, ToolCallContext
from product_backend.domain.enums import (
    ActionType,
    DiagnosisCode,
    DiagnosticType,
    EvidenceSourceType,
)
from product_backend.domain.models import Evidence, KbArticle
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
)
from product_backend.persistence.uow import (
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)


async def seed(*, tenant_id: str, run_id: str) -> dict[str, object]:
    settings = DatabaseSettings.from_env()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    fixture = Scenario1FixtureSources()
    now = datetime.now(UTC)

    try:
        topology = await fixture.get_device(
            tenant_id=tenant_id,
            run_id=run_id,
            device_id=AFFECTED_DEVICE_ID,
        )
        health = await fixture.get_site_health(
            tenant_id=tenant_id,
            run_id=run_id,
            site_id=SITE_ID,
        )
        diagnostic = await fixture.run_diagnostic(
            tenant_id=tenant_id,
            run_id=run_id,
            diagnostic_type=DiagnosticType.ACCESS_LINK,
            target_id=ATTACHMENT_ID,
        )
        if topology is None or health is None or diagnostic is None:
            raise RuntimeError("canonical Scenario 1 fixture was unavailable")

        knowledge_base = KbArticle(
            article_id="KB-S1-FIELD-VISIT",
            title="Approved local physical-path inspection",
            approved=True,
            diagnosis_codes=(DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,),
            allowed_actions=(ActionType.ONSITE_FIELD_VISIT,),
        )
        evidence = (
            Evidence(
                evidence_id=f"E-CMDB-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.CMDB_SNAPSHOT,
                captured_at=now,
                entity_ids=(
                    topology.device_id,
                    topology.site_id,
                    topology.attachment_id,
                    topology.expected_switch_id,
                    topology.expected_port_id,
                ),
                payload=topology,
            ),
            Evidence(
                evidence_id=f"E-SITE-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.SITE_HEALTH,
                captured_at=now,
                entity_ids=(
                    health.site_id,
                    health.peer_device_id,
                    health.affected_device_id,
                ),
                payload=health,
                expires_at=now + timedelta(minutes=30),
            ),
            Evidence(
                evidence_id=f"E-DIAG-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
                captured_at=now,
                entity_ids=(
                    diagnostic.attachment_id,
                    diagnostic.switch_id,
                    diagnostic.port_id,
                ),
                payload=diagnostic,
                expires_at=now + timedelta(minutes=30),
            ),
            Evidence(
                evidence_id=f"E-KB-{uuid4().hex}",
                tenant_id=tenant_id,
                run_id=run_id,
                source_type=EvidenceSourceType.KB_ARTICLE,
                captured_at=now,
                entity_ids=(knowledge_base.article_id,),
                payload=knowledge_base,
            ),
        )

        async with SqlAlchemyToolReadUnitOfWork(session_factory) as uow:
            for item in evidence:
                await uow.evidence.add(item)
            await uow.commit()

        service = FieldVisitProposalService(
            lambda: SqlAlchemyProposalCreationUnitOfWork(session_factory)
        )
        result = await service.create(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            ProposeFieldVisitRequest(
                incident_id=INCIDENT_ID,
                device_id=AFFECTED_DEVICE_ID,
                diagnosis=DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
                evidence_ids=tuple(item.evidence_id for item in evidence),
                rationale="Evidence supports an onsite physical-path inspection.",
            ),
        )
        if not result.ok:
            raise RuntimeError(f"proposal creation failed: {result.error.code.value}")

        return {
            "tenant_id": tenant_id,
            "run_id": run_id,
            "proposal_id": result.proposal.proposal_id,
            "proposal_status": result.proposal.status.value,
            "evidence_count": len(evidence),
        }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    print(json.dumps(asyncio.run(seed(**vars(arguments))), sort_keys=True))


if __name__ == "__main__":
    main()
