from __future__ import annotations

import asyncio
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
import os
from uuid import uuid4

import pytest

from product_api.scenario2_fixture import (
    ACMEPAY_DEPENDENCY_ID,
    ACMEPAY_NAME,
    CANONICAL_SERVICE_INCIDENTS,
    CANONICAL_SIGNAL_SEQUENCE,
    CORRELATION_KEY,
    INCIDENT_KZN,
    INCIDENT_SAM,
    SERVICE_KEY,
    SIGNAL_1_ID,
    SIGNAL_2_ID,
    SIGNAL_3_ID,
    SITE_KZN,
    SITE_SAM,
)
from product_backend.application.major_incident import (
    MajorIncidentApprovalService,
    MajorIncidentProposalService,
)
from product_backend.contracts.scenario2_signal import validate_operational_signal
from product_backend.contracts.scenario2_tools import ProposeMajorIncidentRequest
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import (
    ApprovalDecision,
    EvidenceSourceType,
    HealthState,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.models import Evidence, Run
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.repositories import SqlAlchemyRunRepository
from product_backend.persistence.scenario2 import (
    SqlAlchemyOperationalSignalRepository,
    SqlAlchemyServiceIncidentRepository,
)
from product_backend.persistence.serialization import (
    deserialize_evidence_payload,
    serialize_evidence_payload,
)
from product_backend.domain.scenario2 import (
    DependencyKind,
    ExternalDependencyStatusSnapshot,
    LocalServiceHealthSnapshot,
    MajorIncidentApproval,
    MajorIncidentExecution,
    MajorIncidentProposal,
    MajorIncidentRecord,
    MajorIncidentSearchSnapshot,
    MajorIncidentStatus,
    OperationalSignal,
    OperationalSignalEvidenceSnapshot,
    Scenario2ActionType,
    Scenario2SignalSource,
    ServiceDependencyMappingSnapshot,
    major_incident_equivalence_key,
)
from product_backend.domain.validators_scenario2 import (
    validate_major_incident_approval_currentness,
    validate_major_incident_proposal_evidence,
)


TENANT = "TENANT-S2"
RUN_ID = "RUN-S2"
NOW = datetime(2026, 10, 6, 0, 0, tzinfo=UTC)
TTL = NOW + timedelta(minutes=15)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 7B persistence tests")
    return normalize_database_url(value)


def _ev(
    evidence_id: str,
    source_type: EvidenceSourceType,
    payload,
    entity_ids: tuple[str, ...],
    *,
    tenant_id: str = TENANT,
    run_id: str = RUN_ID,
    dynamic: bool = True,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        tenant_id=tenant_id,
        run_id=run_id,
        source_type=source_type,
        captured_at=NOW,
        entity_ids=entity_ids,
        payload=payload,
        expires_at=TTL if dynamic else None,
    )


def _valid_evidence() -> tuple[Evidence, ...]:
    return (
        _ev(
            "EV-SIG-KZN",
            EvidenceSourceType.OPERATIONAL_SIGNAL,
            OperationalSignalEvidenceSnapshot(
                signal_id=SIGNAL_1_ID,
                source=Scenario2SignalSource.MONITORING,
                site_id=SITE_KZN,
                service_key=SERVICE_KEY,
                symptom_key=CORRELATION_KEY,
                source_ref="MON-ALERT-KZN-901",
            ),
            (SIGNAL_1_ID, SITE_KZN, SERVICE_KEY, CORRELATION_KEY),
        ),
        _ev(
            "EV-SIG-SAM",
            EvidenceSourceType.OPERATIONAL_SIGNAL,
            OperationalSignalEvidenceSnapshot(
                signal_id=SIGNAL_3_ID,
                source=Scenario2SignalSource.MONITORING,
                site_id=SITE_SAM,
                service_key=SERVICE_KEY,
                symptom_key=CORRELATION_KEY,
                source_ref="MON-ALERT-SAM-337",
            ),
            (SIGNAL_3_ID, SITE_SAM, SERVICE_KEY, CORRELATION_KEY),
        ),
        _ev(
            "EV-LOCAL-KZN",
            EvidenceSourceType.LOCAL_SERVICE_HEALTH,
            LocalServiceHealthSnapshot(
                site_id=SITE_KZN,
                service_key=SERVICE_KEY,
                network_health=HealthState.HEALTHY,
                local_service_health=HealthState.HEALTHY,
            ),
            (SITE_KZN, SERVICE_KEY),
        ),
        _ev(
            "EV-LOCAL-SAM",
            EvidenceSourceType.LOCAL_SERVICE_HEALTH,
            LocalServiceHealthSnapshot(
                site_id=SITE_SAM,
                service_key=SERVICE_KEY,
                network_health=HealthState.HEALTHY,
                local_service_health=HealthState.HEALTHY,
            ),
            (SITE_SAM, SERVICE_KEY),
        ),
        _ev(
            "EV-MAP",
            EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING,
            ServiceDependencyMappingSnapshot(
                service_key=SERVICE_KEY,
                dependency_id=ACMEPAY_DEPENDENCY_ID,
                dependency_name=ACMEPAY_NAME,
                dependency_kind=DependencyKind.EXTERNAL_PROVIDER,
            ),
            (SERVICE_KEY, ACMEPAY_DEPENDENCY_ID),
            dynamic=False,
        ),
        _ev(
            "EV-STATUS",
            EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS,
            ExternalDependencyStatusSnapshot(
                dependency_id=ACMEPAY_DEPENDENCY_ID,
                dependency_name=ACMEPAY_NAME,
                status=HealthState.DEGRADED,
                status_detail="elevated_timeout_rate",
            ),
            (ACMEPAY_DEPENDENCY_ID,),
        ),
        _ev(
            "EV-MI-SEARCH",
            EvidenceSourceType.MAJOR_INCIDENT_SEARCH,
            MajorIncidentSearchSnapshot(
                correlation_key=CORRELATION_KEY,
                dependency_id=ACMEPAY_DEPENDENCY_ID,
                open_major_incident_ids=(),
            ),
            (CORRELATION_KEY, ACMEPAY_DEPENDENCY_ID),
        ),
    )


def _proposal(
    evidence: tuple[Evidence, ...] | None = None,
    *,
    status: ProposalStatus = ProposalStatus.PENDING_APPROVAL,
) -> MajorIncidentProposal:
    items = evidence or _valid_evidence()
    return MajorIncidentProposal(
        proposal_id="MIP-1",
        tenant_id=TENANT,
        run_id=RUN_ID,
        correlation_key=CORRELATION_KEY,
        service_key=SERVICE_KEY,
        affected_site_ids=(SITE_KZN, SITE_SAM),
        dependency_id=ACMEPAY_DEPENDENCY_ID,
        dependency_name=ACMEPAY_NAME,
        action_type=Scenario2ActionType.CREATE_MAJOR_INCIDENT,
        evidence_ids=tuple(item.evidence_id for item in items),
        summary="Payment gateway timeouts across independent stores",
        rationale="Cross-site evidence points to a degraded common dependency.",
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def test_canonical_fixture_sequence_and_incident_reuse_are_exact():
    assert [item.signal_id for item in CANONICAL_SIGNAL_SEQUENCE] == [
        SIGNAL_1_ID,
        SIGNAL_2_ID,
        SIGNAL_3_ID,
    ]
    assert [item.site_id for item in CANONICAL_SIGNAL_SEQUENCE] == [
        SITE_KZN,
        SITE_KZN,
        SITE_SAM,
    ]
    assert CANONICAL_SIGNAL_SEQUENCE[0].incident_id == INCIDENT_KZN
    assert CANONICAL_SIGNAL_SEQUENCE[1].incident_id == INCIDENT_KZN
    assert CANONICAL_SIGNAL_SEQUENCE[2].incident_id == INCIDENT_SAM
    assert len(CANONICAL_SERVICE_INCIDENTS) == 2
    assert all(
        "AcmePay" not in str(item.safe_payload)
        for item in CANONICAL_SIGNAL_SEQUENCE
    )


def test_operational_signal_contract_requires_server_utc_and_safe_payload():
    signal = OperationalSignal(
        signal_id=SIGNAL_1_ID,
        tenant_id=TENANT,
        run_id=RUN_ID,
        source=Scenario2SignalSource.MONITORING,
        site_id=SITE_KZN,
        service_key=SERVICE_KEY,
        symptom_key=CORRELATION_KEY,
        source_ref="MON-ALERT-KZN-901",
        received_at=NOW,
        safe_payload={"kind": "payment_timeout_rate"},
        incident_id=INCIDENT_KZN,
    )
    validate_operational_signal(signal)

    unsafe = replace(signal, safe_payload={"api_key": "never-persist"})
    try:
        validate_operational_signal(unsafe)
    except ValueError as exc:
        assert "not allowed" in str(exc)
    else:
        raise AssertionError("secret-like payload key must be rejected")


def test_major_incident_contract_has_no_scenario1_dummy_fields():
    proposal_fields = {item.name for item in fields(MajorIncidentProposal)}
    record_fields = {item.name for item in fields(MajorIncidentRecord)}
    execution_fields = {item.name for item in fields(MajorIncidentExecution)}

    forbidden = {"device_id", "diagnosis", "work_order_id", "attachment_id"}
    assert proposal_fields.isdisjoint(forbidden)
    assert record_fields.isdisjoint(forbidden)
    assert execution_fields.isdisjoint(forbidden)
    assert Scenario2ActionType.CREATE_MAJOR_INCIDENT.value == "CREATE_MAJOR_INCIDENT"


def test_scenario2_evidence_payloads_round_trip_losslessly():
    for item in _valid_evidence():
        payload = serialize_evidence_payload(item.source_type, item.payload)
        restored = deserialize_evidence_payload(item.source_type, payload)
        assert restored == item.payload


def test_expired_dynamic_evidence_is_rejected():
    evidence = list(_valid_evidence())
    evidence[0] = replace(
        evidence[0],
        expires_at=NOW + timedelta(seconds=30),
    )
    error = validate_major_incident_proposal_evidence(
        proposal=_proposal(tuple(evidence)),
        evidence=tuple(evidence),
        now=NOW + timedelta(minutes=1),
    )
    assert error is not None
    assert dict(error.details)["reason"] == "expired_evidence"


def test_persisted_operational_signals_are_tenant_and_run_isolated():
    async def scenario() -> None:
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                run_repo = SqlAlchemyRunRepository(session)
                service_incidents = SqlAlchemyServiceIncidentRepository(session)
                signals = SqlAlchemyOperationalSignalRepository(session)

                suffix = uuid4().hex[:10]
                run_a = Run(
                    run_id=f"{RUN_ID}-A-{suffix}",
                    tenant_id=f"{TENANT}-A-{suffix}",
                    scenario_id="scenario-2",
                    status=RunStatus.ACTIVE,
                    created_at=NOW,
                    updated_at=NOW,
                )
                run_b = Run(
                    run_id=f"{RUN_ID}-B-{suffix}",
                    tenant_id=f"{TENANT}-B-{suffix}",
                    scenario_id="scenario-2",
                    status=RunStatus.ACTIVE,
                    created_at=NOW,
                    updated_at=NOW,
                )
                await run_repo.add(run_a)
                await run_repo.add(run_b)
                await session.flush()

                from product_backend.domain.enums import IncidentStatus
                from product_backend.domain.scenario2 import ServiceIncident

                incident_a = ServiceIncident(
                    incident_id=f"{INCIDENT_KZN}-A",
                    tenant_id=run_a.tenant_id,
                    run_id=run_a.run_id,
                    site_id=SITE_KZN,
                    service_key=SERVICE_KEY,
                    symptom_key=CORRELATION_KEY,
                    status=IncidentStatus.OPEN,
                    created_at=NOW,
                    updated_at=NOW,
                )
                incident_b = ServiceIncident(
                    incident_id=f"{INCIDENT_KZN}-B",
                    tenant_id=run_b.tenant_id,
                    run_id=run_b.run_id,
                    site_id=SITE_KZN,
                    service_key=SERVICE_KEY,
                    symptom_key=CORRELATION_KEY,
                    status=IncidentStatus.OPEN,
                    created_at=NOW,
                    updated_at=NOW,
                )
                await service_incidents.add(incident_a)
                await service_incidents.add(incident_b)

                signal_a = OperationalSignal(
                    signal_id=f"{SIGNAL_1_ID}-A",
                    tenant_id=run_a.tenant_id,
                    run_id=run_a.run_id,
                    source=Scenario2SignalSource.MONITORING,
                    site_id=SITE_KZN,
                    service_key=SERVICE_KEY,
                    symptom_key=CORRELATION_KEY,
                    source_ref="SHARED-SOURCE-REF",
                    received_at=NOW,
                    safe_payload={"kind": "payment_timeout_rate"},
                    incident_id=incident_a.incident_id,
                )
                signal_b = OperationalSignal(
                    signal_id=f"{SIGNAL_1_ID}-B",
                    tenant_id=run_b.tenant_id,
                    run_id=run_b.run_id,
                    source=Scenario2SignalSource.MONITORING,
                    site_id=SITE_KZN,
                    service_key=SERVICE_KEY,
                    symptom_key=CORRELATION_KEY,
                    source_ref="SHARED-SOURCE-REF",
                    received_at=NOW,
                    safe_payload={"kind": "payment_timeout_rate"},
                    incident_id=incident_b.incident_id,
                )
                await signals.add(signal_a)
                await signals.add(signal_b)
                await session.commit()

            async with factory() as session:
                signals = SqlAlchemyOperationalSignalRepository(session)
                assert await signals.list_for_run(
                    tenant_id=run_a.tenant_id,
                    run_id=run_a.run_id,
                ) == (signal_a,)
                assert await signals.list_for_run(
                    tenant_id=run_b.tenant_id,
                    run_id=run_b.run_id,
                ) == (signal_b,)
                assert (
                    await signals.get(
                        tenant_id=run_a.tenant_id,
                        run_id=run_a.run_id,
                        signal_id=signal_b.signal_id,
                    )
                    is None
                )
                assert (
                    await signals.get_by_source_identity(
                        tenant_id=run_a.tenant_id,
                        run_id=run_a.run_id,
                        source=Scenario2SignalSource.MONITORING,
                        source_ref="SHARED-SOURCE-REF",
                    )
                    == signal_a
                )
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_valid_cross_site_evidence_supports_major_incident_proposal():
    evidence = _valid_evidence()
    error = validate_major_incident_proposal_evidence(
        proposal=_proposal(evidence),
        evidence=evidence,
        now=NOW + timedelta(minutes=1),
    )
    assert error is None


def test_single_site_evidence_is_insufficient():
    evidence = _valid_evidence()
    proposal = replace(
        _proposal(evidence),
        affected_site_ids=(SITE_KZN,),
        evidence_ids=tuple(
            item.evidence_id
            for item in evidence
            if not (
                item.source_type
                in {
                    EvidenceSourceType.OPERATIONAL_SIGNAL,
                    EvidenceSourceType.LOCAL_SERVICE_HEALTH,
                }
                and SITE_SAM in item.entity_ids
            )
        ),
    )
    selected = tuple(
        item for item in evidence if item.evidence_id in proposal.evidence_ids
    )
    error = validate_major_incident_proposal_evidence(
        proposal=proposal,
        evidence=selected,
        now=NOW + timedelta(minutes=1),
    )
    assert error is not None
    assert dict(error.details)["reason"] == "insufficient_cross_site_evidence"


def test_cross_tenant_or_cross_run_evidence_is_rejected():
    evidence = list(_valid_evidence())
    evidence[0] = replace(evidence[0], tenant_id="OTHER-TENANT")
    error = validate_major_incident_proposal_evidence(
        proposal=_proposal(tuple(evidence)),
        evidence=tuple(evidence),
        now=NOW + timedelta(minutes=1),
    )
    assert error is not None
    assert dict(error.details)["reason"] == "foreign_tenant_or_run"

    evidence = list(_valid_evidence())
    evidence[0] = replace(evidence[0], run_id="OTHER-RUN")
    error = validate_major_incident_proposal_evidence(
        proposal=_proposal(tuple(evidence)),
        evidence=tuple(evidence),
        now=NOW + timedelta(minutes=1),
    )
    assert error is not None
    assert dict(error.details)["reason"] == "foreign_tenant_or_run"


def test_same_run_fabricated_signal_evidence_without_persisted_signal_is_rejected():
    async def scenario() -> None:
        store = _Store()
        fabricated = replace(
            store.evidence["EV-SIG-KZN"],
            evidence_id="EV-SIG-FAKE",
            payload=OperationalSignalEvidenceSnapshot(
                signal_id="SIG-NOT-PERSISTED",
                source=Scenario2SignalSource.MONITORING,
                site_id=SITE_KZN,
                service_key=SERVICE_KEY,
                symptom_key=CORRELATION_KEY,
                source_ref="MON-FAKE",
            ),
            entity_ids=(
                "SIG-NOT-PERSISTED",
                SITE_KZN,
                SERVICE_KEY,
                CORRELATION_KEY,
            ),
        )
        store.evidence[fabricated.evidence_id] = fabricated
        evidence_ids = tuple(
            "EV-SIG-FAKE" if item == "EV-SIG-KZN" else item
            for item in _proposal().evidence_ids
        )
        service = MajorIncidentProposalService(
            lambda: _Uow(store),
            clock=lambda: NOW + timedelta(minutes=1),
            id_factory=lambda prefix: "MIP-FAKE",
        )
        result = await service.create(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            replace(_request(), evidence_ids=evidence_ids),
        )
        assert result.ok is False
        assert dict(result.error.details)["reason"] == "persisted_signal_not_found"

    asyncio.run(scenario())


def test_fabricated_or_unresolved_evidence_id_is_rejected():
    evidence = _valid_evidence()
    proposal = replace(
        _proposal(evidence),
        evidence_ids=tuple(item.evidence_id for item in evidence) + ("EV-FAKE",),
    )
    error = validate_major_incident_proposal_evidence(
        proposal=proposal,
        evidence=evidence,
        now=NOW + timedelta(minutes=1),
    )
    assert error is not None
    assert dict(error.details)["reason"] == "evidence_ids_not_resolved_exactly"


def test_approve_revalidation_goes_stale_when_provider_recovers():
    evidence = _valid_evidence()
    proposal = _proposal(evidence)
    current_health = (
        LocalServiceHealthSnapshot(
            site_id=SITE_KZN,
            service_key=SERVICE_KEY,
            network_health=HealthState.HEALTHY,
            local_service_health=HealthState.HEALTHY,
        ),
        LocalServiceHealthSnapshot(
            site_id=SITE_SAM,
            service_key=SERVICE_KEY,
            network_health=HealthState.HEALTHY,
            local_service_health=HealthState.HEALTHY,
        ),
    )
    error = validate_major_incident_approval_currentness(
        proposal=proposal,
        proposal_evidence=evidence,
        current_local_health=current_health,
        current_dependency_status=ExternalDependencyStatusSnapshot(
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            dependency_name=ACMEPAY_NAME,
            status=HealthState.HEALTHY,
            status_detail="operating_normally",
        ),
        current_major_incident_search=MajorIncidentSearchSnapshot(
            correlation_key=CORRELATION_KEY,
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            open_major_incident_ids=(),
        ),
        now=NOW + timedelta(minutes=1),
    )
    assert error is not None
    assert dict(error.details)["reason"] == "external_dependency_recovered"


def test_approve_revalidation_goes_stale_when_matching_major_incident_exists():
    evidence = _valid_evidence()
    proposal = _proposal(evidence)
    current_health = tuple(
        item.payload
        for item in evidence
        if item.source_type is EvidenceSourceType.LOCAL_SERVICE_HEALTH
        and isinstance(item.payload, LocalServiceHealthSnapshot)
    )
    error = validate_major_incident_approval_currentness(
        proposal=proposal,
        proposal_evidence=evidence,
        current_local_health=current_health,
        current_dependency_status=ExternalDependencyStatusSnapshot(
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            dependency_name=ACMEPAY_NAME,
            status=HealthState.DEGRADED,
            status_detail="elevated_timeout_rate",
        ),
        current_major_incident_search=MajorIncidentSearchSnapshot(
            correlation_key=CORRELATION_KEY,
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            open_major_incident_ids=("MI-EXISTS",),
        ),
        now=NOW + timedelta(minutes=1),
    )
    assert error is not None
    assert dict(error.details)["reason"] == "matching_major_incident_now_exists"


def test_duplicate_key_is_tenant_service_correlation_dependency_scoped():
    assert major_incident_equivalence_key(
        tenant_id=TENANT,
        service_key=SERVICE_KEY,
        correlation_key=CORRELATION_KEY,
        dependency_id=ACMEPAY_DEPENDENCY_ID,
    ) == (
        TENANT,
        SERVICE_KEY,
        CORRELATION_KEY,
        ACMEPAY_DEPENDENCY_ID,
    )


class _Store:
    def __init__(self) -> None:
        self.run = Run(
            run_id=RUN_ID,
            tenant_id=TENANT,
            scenario_id="scenario-2",
            status=RunStatus.ACTIVE,
            created_at=NOW,
            updated_at=NOW,
        )
        self.evidence = {item.evidence_id: item for item in _valid_evidence()}
        self.signals = {
            SIGNAL_1_ID: OperationalSignal(
                signal_id=SIGNAL_1_ID,
                tenant_id=TENANT,
                run_id=RUN_ID,
                source=Scenario2SignalSource.MONITORING,
                site_id=SITE_KZN,
                service_key=SERVICE_KEY,
                symptom_key=CORRELATION_KEY,
                source_ref="MON-ALERT-KZN-901",
                received_at=NOW,
                safe_payload={"kind": "payment_timeout_rate"},
                incident_id=INCIDENT_KZN,
            ),
            SIGNAL_3_ID: OperationalSignal(
                signal_id=SIGNAL_3_ID,
                tenant_id=TENANT,
                run_id=RUN_ID,
                source=Scenario2SignalSource.MONITORING,
                site_id=SITE_SAM,
                service_key=SERVICE_KEY,
                symptom_key=CORRELATION_KEY,
                source_ref="MON-ALERT-SAM-337",
                received_at=NOW,
                safe_payload={"kind": "payment_timeout_rate"},
                incident_id=INCIDENT_SAM,
            ),
        }
        self.proposals: dict[str, MajorIncidentProposal] = {}
        self.approvals: dict[str, MajorIncidentApproval] = {}
        self.major_incidents: dict[str, MajorIncidentRecord] = {}
        self.executions: dict[str, MajorIncidentExecution] = {}


class _RunRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def get(self, *, tenant_id: str, run_id: str):
        if tenant_id == TENANT and run_id == RUN_ID:
            return self.store.run
        return None

    async def save(self, run: Run) -> None:
        self.store.run = run


class _SignalRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        signal_id: str,
    ):
        signal = self.store.signals.get(signal_id)
        if (
            signal is not None
            and signal.tenant_id == tenant_id
            and signal.run_id == run_id
        ):
            return signal
        return None


class _EvidenceRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def get_many(self, *, tenant_id: str, run_id: str, evidence_ids):
        return tuple(
            self.store.evidence[item]
            for item in evidence_ids
            if item in self.store.evidence
        )


class _ProposalRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def add(self, proposal: MajorIncidentProposal) -> None:
        self.store.proposals[proposal.proposal_id] = proposal

    async def get(self, *, tenant_id: str, run_id: str, proposal_id: str):
        proposal = self.store.proposals.get(proposal_id)
        if (
            proposal is not None
            and proposal.tenant_id == tenant_id
            and proposal.run_id == run_id
        ):
            return proposal
        return None

    async def save(self, proposal: MajorIncidentProposal) -> None:
        self.store.proposals[proposal.proposal_id] = proposal

    async def get_pending_equivalent(
        self,
        *,
        tenant_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ):
        return next(
            (
                item
                for item in self.store.proposals.values()
                if item.tenant_id == tenant_id
                and item.service_key == service_key
                and item.correlation_key == correlation_key
                and item.dependency_id == dependency_id
                and item.status is ProposalStatus.PENDING_APPROVAL
            ),
            None,
        )


class _ApprovalRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def add(self, approval: MajorIncidentApproval) -> None:
        self.store.approvals[approval.proposal_id] = approval

    async def get_for_proposal(self, *, tenant_id: str, run_id: str, proposal_id: str):
        approval = self.store.approvals.get(proposal_id)
        if (
            approval is not None
            and approval.tenant_id == tenant_id
            and approval.run_id == run_id
        ):
            return approval
        return None


class _MajorIncidentRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def add(self, major_incident: MajorIncidentRecord) -> None:
        self.store.major_incidents[major_incident.major_incident_id] = major_incident

    async def get_for_proposal(self, *, tenant_id: str, run_id: str, proposal_id: str):
        return next(
            (
                item
                for item in self.store.major_incidents.values()
                if item.tenant_id == tenant_id
                and item.run_id == run_id
                and item.proposal_id == proposal_id
            ),
            None,
        )

    async def get_equivalent(
        self,
        *,
        tenant_id: str,
        service_key: str,
        correlation_key: str,
        dependency_id: str,
    ):
        return next(
            (
                item
                for item in self.store.major_incidents.values()
                if item.tenant_id == tenant_id
                and item.service_key == service_key
                and item.correlation_key == correlation_key
                and item.dependency_id == dependency_id
            ),
            None,
        )


class _ExecutionRepo:
    def __init__(self, store: _Store) -> None:
        self.store = store

    async def add(self, execution: MajorIncidentExecution) -> None:
        self.store.executions[execution.proposal_id] = execution

    async def get_for_proposal(self, *, tenant_id: str, run_id: str, proposal_id: str):
        execution = self.store.executions.get(proposal_id)
        if (
            execution is not None
            and execution.tenant_id == tenant_id
            and execution.run_id == run_id
        ):
            return execution
        return None


class _NullRepo:
    async def add(self, value) -> None:
        return None


class _Uow:
    def __init__(self, store: _Store) -> None:
        self.runs = _RunRepo(store)
        self.service_incidents = _NullRepo()
        self.signals = _SignalRepo(store)
        self.evidence = _EvidenceRepo(store)
        self.major_incident_proposals = _ProposalRepo(store)
        self.major_incident_approvals = _ApprovalRepo(store)
        self.major_incidents = _MajorIncidentRepo(store)
        self.major_incident_executions = _ExecutionRepo(store)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _Sources:
    def __init__(
        self,
        *,
        provider_status: HealthState = HealthState.DEGRADED,
        existing_major_incidents: tuple[str, ...] = (),
    ) -> None:
        self.provider_status = provider_status
        self.existing_major_incidents = existing_major_incidents

    async def get_local_service_health(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
        service_key: str,
    ):
        if tenant_id != TENANT or run_id != RUN_ID:
            return None
        return LocalServiceHealthSnapshot(
            site_id=site_id,
            service_key=service_key,
            network_health=HealthState.HEALTHY,
            local_service_health=HealthState.HEALTHY,
        )

    async def get_external_dependency_status(
        self,
        *,
        tenant_id: str,
        run_id: str,
        dependency_id: str,
    ):
        if tenant_id != TENANT or run_id != RUN_ID:
            return None
        return ExternalDependencyStatusSnapshot(
            dependency_id=dependency_id,
            dependency_name=ACMEPAY_NAME,
            status=self.provider_status,
            status_detail="fixture",
        )

    async def search_major_incidents(
        self,
        *,
        tenant_id: str,
        run_id: str,
        correlation_key: str,
        dependency_id: str,
    ):
        return MajorIncidentSearchSnapshot(
            correlation_key=correlation_key,
            dependency_id=dependency_id,
            open_major_incident_ids=self.existing_major_incidents,
        )


def _request(evidence: tuple[Evidence, ...] | None = None):
    evidence = evidence or _valid_evidence()
    return ProposeMajorIncidentRequest(
        correlation_key=CORRELATION_KEY,
        service_key=SERVICE_KEY,
        affected_site_ids=(SITE_KZN, SITE_SAM),
        dependency_id=ACMEPAY_DEPENDENCY_ID,
        evidence_ids=tuple(item.evidence_id for item in evidence),
        summary="Payment gateway timeouts across stores",
        rationale="Cross-site and dependency evidence support escalation.",
    )


def test_product_approve_creates_one_record_and_replay_creates_no_duplicate():
    async def scenario() -> None:
        store = _Store()
        ids = iter(
            [
                "MIP-1",
                "MIA-1",
                "MI-1",
                "MIX-1",
                "SHOULD-NOT-BE-USED",
            ]
        )
        id_factory = lambda prefix: next(ids)
        proposal_service = MajorIncidentProposalService(
            lambda: _Uow(store),
            clock=lambda: NOW,
            id_factory=id_factory,
        )
        sources = _Sources()
        approval_service = MajorIncidentApprovalService(
            lambda: _Uow(store),
            local_health=sources,
            dependency_status=sources,
            major_incident_directory=sources,
            clock=lambda: NOW + timedelta(minutes=1),
            id_factory=id_factory,
        )

        created = await proposal_service.create(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            _request(),
        )
        assert created.ok is True
        assert store.run.status is RunStatus.WAITING_APPROVAL

        approved = await approval_service.decide(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            proposal_id=created.proposal.proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="operator",
        )
        assert approved.ok is True
        assert approved.proposal.status is ProposalStatus.EXECUTED
        assert approved.execution is not None
        assert approved.major_incident is not None
        assert approved.major_incident.status is MajorIncidentStatus.OPEN
        assert len(store.major_incidents) == 1
        assert len(store.executions) == 1

        replay = await approval_service.decide(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            proposal_id=created.proposal.proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="operator",
        )
        assert replay.ok is True
        assert replay.replayed is True
        assert replay.major_incident == approved.major_incident
        assert replay.execution == approved.execution
        assert len(store.major_incidents) == 1
        assert len(store.executions) == 1

    asyncio.run(scenario())


def test_equivalent_pending_proposal_is_blocked_across_runs():
    async def scenario() -> None:
        store = _Store()
        existing = _proposal()
        store.proposals[existing.proposal_id] = replace(
            existing,
            run_id="OTHER-RUN",
            proposal_id="MIP-OTHER-RUN",
        )
        service = MajorIncidentProposalService(
            lambda: _Uow(store),
            clock=lambda: NOW,
            id_factory=lambda prefix: "SHOULD-NOT-BE-CREATED",
        )
        result = await service.create(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            _request(),
        )
        assert result.ok is False
        assert (
            dict(result.error.details)["reason"]
            == "duplicate_pending_major_incident_proposal"
        )
        assert len(store.proposals) == 1

    asyncio.run(scenario())


def test_existing_equivalent_major_incident_blocks_new_proposal():
    async def scenario() -> None:
        store = _Store()
        existing = MajorIncidentRecord(
            major_incident_id="MI-EXISTING",
            tenant_id=TENANT,
            run_id="OLDER-RUN",
            proposal_id="OLDER-PROPOSAL",
            correlation_key=CORRELATION_KEY,
            service_key=SERVICE_KEY,
            affected_site_ids=(SITE_KZN, SITE_SAM),
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            dependency_name=ACMEPAY_NAME,
            summary="Existing incident",
            status=MajorIncidentStatus.OPEN,
            created_at=NOW,
        )
        store.major_incidents[existing.major_incident_id] = existing
        proposal_service = MajorIncidentProposalService(
            lambda: _Uow(store),
            clock=lambda: NOW,
            id_factory=lambda prefix: "SHOULD-NOT-BE-CREATED",
        )
        result = await proposal_service.create(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            _request(),
        )
        assert result.ok is False
        assert dict(result.error.details)["reason"] == "duplicate_major_incident_exists"
        assert store.proposals == {}

    asyncio.run(scenario())


def test_product_approve_becomes_stale_when_matching_major_incident_appears():
    async def scenario() -> None:
        store = _Store()
        ids = iter(["MIP-1", "MIA-1"])
        id_factory = lambda prefix: next(ids)
        proposal_service = MajorIncidentProposalService(
            lambda: _Uow(store),
            clock=lambda: NOW,
            id_factory=id_factory,
        )
        create_sources = _Sources()
        created = await proposal_service.create(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            _request(),
        )
        assert created.ok is True

        decision_sources = _Sources(existing_major_incidents=("MI-EXTERNAL",))
        approval_service = MajorIncidentApprovalService(
            lambda: _Uow(store),
            local_health=decision_sources,
            dependency_status=decision_sources,
            major_incident_directory=decision_sources,
            clock=lambda: NOW + timedelta(minutes=1),
            id_factory=id_factory,
        )
        stale = await approval_service.decide(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            proposal_id=created.proposal.proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="operator",
        )
        assert stale.ok is True
        assert stale.proposal.status is ProposalStatus.STALE
        assert stale.execution is None
        assert stale.major_incident is None
        assert store.major_incidents == {}

    asyncio.run(scenario())


def test_product_reject_creates_audit_decision_and_zero_execution():
    async def scenario() -> None:
        store = _Store()
        ids = iter(["MIP-1", "MIA-1"])
        id_factory = lambda prefix: next(ids)
        proposal_service = MajorIncidentProposalService(
            lambda: _Uow(store),
            clock=lambda: NOW,
            id_factory=id_factory,
        )
        sources = _Sources()
        approval_service = MajorIncidentApprovalService(
            lambda: _Uow(store),
            local_health=sources,
            dependency_status=sources,
            major_incident_directory=sources,
            clock=lambda: NOW + timedelta(minutes=1),
            id_factory=id_factory,
        )
        created = await proposal_service.create(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            _request(),
        )
        rejected = await approval_service.decide(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            proposal_id=created.proposal.proposal_id,
            decision=ApprovalDecision.REJECTED,
            decided_by="operator",
        )
        assert rejected.ok is True
        assert rejected.proposal.status is ProposalStatus.REJECTED
        assert rejected.execution is None
        assert rejected.major_incident is None
        assert len(store.approvals) == 1
        assert store.major_incidents == {}
        assert store.executions == {}

    asyncio.run(scenario())


def test_product_approve_becomes_stale_on_recovered_provider():
    async def scenario() -> None:
        store = _Store()
        ids = iter(["MIP-1", "MIA-1"])
        id_factory = lambda prefix: next(ids)
        proposal_service = MajorIncidentProposalService(
            lambda: _Uow(store),
            clock=lambda: NOW,
            id_factory=id_factory,
        )
        sources = _Sources(provider_status=HealthState.HEALTHY)
        approval_service = MajorIncidentApprovalService(
            lambda: _Uow(store),
            local_health=sources,
            dependency_status=sources,
            major_incident_directory=sources,
            clock=lambda: NOW + timedelta(minutes=1),
            id_factory=id_factory,
        )
        created = await proposal_service.create(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            _request(),
        )
        stale = await approval_service.decide(
            ToolCallContext(tenant_id=TENANT, run_id=RUN_ID),
            proposal_id=created.proposal.proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="operator",
        )
        assert stale.ok is True
        assert stale.proposal.status is ProposalStatus.STALE
        assert stale.execution is None
        assert stale.major_incident is None
        assert store.major_incidents == {}

    asyncio.run(scenario())
