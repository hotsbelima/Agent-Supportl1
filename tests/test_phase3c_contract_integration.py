from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from product_backend.adapters.tool_adapters import DefaultScenario1ToolAdapter
from product_backend.application.field_visit import FieldVisitProposalService
from product_backend.application.read_tools import (
    EvidenceTtlPolicy,
    Scenario1ReadToolService,
)
from product_backend.contracts.tools import (
    GetDeviceRequest,
    GetSiteHealthRequest,
    ProposeFieldVisitRequest,
    RunDiagnosticRequest,
    SearchIncidentsRequest,
    SearchKbRequest,
    ToolCallContext,
)
from product_backend.domain.enums import (
    ActionType,
    AdminState,
    ConfigurationState,
    DiagnosisCode,
    DiagnosticType,
    EvidenceSourceType,
    HealthState,
    IncidentSearchScope,
    IncidentStatus,
    OperationalState,
    PortSecurityState,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.errors import ErrorCode
from product_backend.domain.models import (
    AccessLinkDiagnosticSnapshot,
    ActionProposal,
    DeviceTopology,
    Evidence,
    Incident,
    IncidentSearchSnapshot,
    KbArticle,
    Run,
    SiteHealthSnapshot,
)

TENANT = "TENANT-8OCT"
RUN_ID = "RUN-3C"
INCIDENT_ID = "INC-1042"
SITE = "SITE-KZN-017"
DEVICE = "POS-KZN17-02"
PEER = "POS-KZN17-01"
ATTACHMENT = "ATT-KZN17-POS02"
SWITCH = "SW-KZN17-01"
PORT = "Gi1/0/18"
T0 = datetime(2026, 10, 4, 15, 0, tzinfo=UTC)


@dataclass
class Store:
    runs: dict[tuple[str, str], Run] = field(default_factory=dict)
    incidents: dict[tuple[str, str, str], Incident] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    proposals: dict[str, ActionProposal] = field(default_factory=dict)


class RunRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, run: Run) -> None:
        self.store.runs[(run.tenant_id, run.run_id)] = run

    async def get(self, *, tenant_id: str, run_id: str) -> Run | None:
        return self.store.runs.get((tenant_id, run_id))

    async def save(self, run: Run) -> None:
        self.store.runs[(run.tenant_id, run.run_id)] = run


class IncidentRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> Incident | None:
        return self.store.incidents.get((tenant_id, run_id, incident_id))

    async def find_by_device(
        self,
        *,
        tenant_id: str,
        run_id: str,
        device_id: str,
    ) -> Incident | None:
        return next(
            (
                item
                for item in self.store.incidents.values()
                if item.tenant_id == tenant_id
                and item.run_id == run_id
                and item.reported_device_id == device_id
            ),
            None,
        )

    async def find_by_site(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
    ) -> Incident | None:
        return next(
            (
                item
                for item in self.store.incidents.values()
                if item.tenant_id == tenant_id
                and item.run_id == run_id
                and item.site_id == site_id
            ),
            None,
        )

    async def save(self, incident: Incident) -> None:
        self.store.incidents[
            (incident.tenant_id, incident.run_id, incident.incident_id)
        ] = incident


class EvidenceRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, evidence: Evidence) -> None:
        self.store.evidence[evidence.evidence_id] = evidence

    async def get_many(
        self,
        *,
        tenant_id: str,
        run_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[Evidence, ...]:
        return tuple(
            item
            for evidence_id in evidence_ids
            if (item := self.store.evidence.get(evidence_id)) is not None
            and item.tenant_id == tenant_id
            and item.run_id == run_id
        )

    async def find_by_entity_id(
        self,
        *,
        tenant_id: str,
        run_id: str,
        entity_id: str,
    ) -> tuple[Evidence, ...]:
        return tuple(
            item
            for item in self.store.evidence.values()
            if item.tenant_id == tenant_id
            and item.run_id == run_id
            and entity_id in item.entity_ids
        )


class ProposalRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, proposal: ActionProposal) -> None:
        self.store.proposals[proposal.proposal_id] = proposal

    async def get(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> ActionProposal | None:
        item = self.store.proposals.get(proposal_id)
        if item and item.tenant_id == tenant_id and item.run_id == run_id:
            return item
        return None

    async def save(self, proposal: ActionProposal) -> None:
        self.store.proposals[proposal.proposal_id] = proposal

    async def get_pending_for_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> ActionProposal | None:
        return next(
            (
                item
                for item in self.store.proposals.values()
                if item.tenant_id == tenant_id
                and item.run_id == run_id
                and item.incident_id == incident_id
                and item.status is ProposalStatus.PENDING_APPROVAL
            ),
            None,
        )


class Uow:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.runs = RunRepo(store)
        self.incidents = IncidentRepo(store)
        self.evidence = EvidenceRepo(store)
        self.proposals = ProposalRepo(store)
        self._snapshot: Store | None = None
        self._committed = False

    async def __aenter__(self):
        self._snapshot = copy.deepcopy(self.store)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type or not self._committed:
            self._restore()

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        self._restore()

    def _restore(self) -> None:
        if self._snapshot is None:
            return
        self.store.runs = self._snapshot.runs
        self.store.incidents = self._snapshot.incidents
        self.store.evidence = self._snapshot.evidence
        self.store.proposals = self._snapshot.proposals


class Ids:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix.upper()}-{self.counts[prefix]:03d}"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeCmdb:
    def __init__(
        self,
        topology: DeviceTopology | None,
        *,
        raises: bool = False,
    ) -> None:
        self.topology = topology
        self.raises = raises
        self.calls = 0

    async def get_device(
        self,
        *,
        tenant_id: str,
        run_id: str,
        device_id: str,
    ) -> DeviceTopology | None:
        self.calls += 1
        if self.raises:
            raise RuntimeError("provider secret should never escape")
        if tenant_id != TENANT or run_id != RUN_ID:
            return None
        if self.topology is None or self.topology.device_id != device_id:
            return None
        return self.topology


class FakeMonitoring:
    def __init__(
        self,
        site_health: SiteHealthSnapshot | None,
        diagnostic: AccessLinkDiagnosticSnapshot | None,
    ) -> None:
        self.site_health = site_health
        self.diagnostic = diagnostic
        self.health_calls = 0
        self.diagnostic_calls = 0

    async def get_site_health(
        self,
        *,
        tenant_id: str,
        run_id: str,
        site_id: str,
    ) -> SiteHealthSnapshot | None:
        self.health_calls += 1
        if tenant_id != TENANT or run_id != RUN_ID:
            return None
        return self.site_health

    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type: DiagnosticType,
        target_id: str,
    ) -> AccessLinkDiagnosticSnapshot | None:
        self.diagnostic_calls += 1
        if tenant_id != TENANT or run_id != RUN_ID:
            return None
        return self.diagnostic


class FakeItsm:
    def __init__(self, snapshot: IncidentSearchSnapshot) -> None:
        self.snapshot = snapshot
        self.calls = 0

    async def get_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> Incident | None:
        return None

    async def search_incidents(
        self,
        *,
        tenant_id: str,
        run_id: str,
        scope: IncidentSearchScope,
        entity_id: str,
    ) -> IncidentSearchSnapshot:
        self.calls += 1
        return self.snapshot


class FakeKb:
    def __init__(
        self,
        articles: tuple[KbArticle, ...],
        *,
        raises: bool = False,
    ) -> None:
        self.articles = articles
        self.raises = raises
        self.calls = 0

    async def search(
        self,
        *,
        tenant_id: str,
        run_id: str,
        query: str,
    ) -> tuple[KbArticle, ...]:
        self.calls += 1
        if self.raises:
            raise RuntimeError("provider secret should never escape")
        return self.articles


def canonical_topology() -> DeviceTopology:
    return DeviceTopology(
        DEVICE,
        SITE,
        ATTACHMENT,
        "POS_TERMINAL",
        SWITCH,
        PORT,
    )


def canonical_site_health() -> SiteHealthSnapshot:
    return SiteHealthSnapshot(
        SITE,
        HealthState.HEALTHY,
        HealthState.HEALTHY,
        PEER,
        True,
        DEVICE,
        False,
    )


def canonical_diagnostic() -> AccessLinkDiagnosticSnapshot:
    return AccessLinkDiagnosticSnapshot(
        ATTACHMENT,
        ATTACHMENT,
        SWITCH,
        PORT,
        True,
        AdminState.UP,
        OperationalState.DOWN,
        PortSecurityState.NORMAL,
        ConfigurationState.EXPECTED,
    )


def canonical_kb() -> KbArticle:
    return KbArticle(
        "KB-LOCAL-LINK",
        "Physical access path inspection",
        True,
        (DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,),
        (ActionType.ONSITE_FIELD_VISIT,),
    )


def make_store() -> Store:
    store = Store()
    store.runs[(TENANT, RUN_ID)] = Run(
        RUN_ID,
        TENANT,
        "scenario-1",
        RunStatus.ACTIVE,
        T0,
        T0,
    )
    store.incidents[(TENANT, RUN_ID, INCIDENT_ID)] = Incident(
        INCIDENT_ID,
        TENANT,
        RUN_ID,
        SITE,
        DEVICE,
        "terminal unavailable",
        IncidentStatus.OPEN,
        T0,
        T0,
    )
    return store


def make_adapter(
    *,
    store: Store | None = None,
    topology: DeviceTopology | None = None,
    site_health: SiteHealthSnapshot | None = None,
    diagnostic: AccessLinkDiagnosticSnapshot | None = None,
    kb_articles: tuple[KbArticle, ...] | None = None,
    cmdb_raises: bool = False,
    kb_raises: bool = False,
):
    store = store or make_store()
    ids = Ids()
    clock = Clock(T0)
    cmdb = FakeCmdb(
        canonical_topology() if topology is None else topology,
        raises=cmdb_raises,
    )
    monitoring = FakeMonitoring(
        canonical_site_health() if site_health is None else site_health,
        canonical_diagnostic() if diagnostic is None else diagnostic,
    )
    itsm = FakeItsm(
        IncidentSearchSnapshot(
            IncidentSearchScope.DEVICE,
            DEVICE,
            (INCIDENT_ID,),
        )
    )
    kb = FakeKb(
        (canonical_kb(),) if kb_articles is None else kb_articles,
        raises=kb_raises,
    )
    proposal_service = FieldVisitProposalService(
        lambda: Uow(store),
        clock=clock,
        id_factory=ids,
    )
    read_service = Scenario1ReadToolService(
        read_uow_factory=lambda: Uow(store),
        cmdb=cmdb,
        monitoring=monitoring,
        itsm=itsm,
        kb=kb,
        ttl_policy=EvidenceTtlPolicy(
            site_health=timedelta(minutes=5),
            access_link_diagnostic=timedelta(minutes=2),
        ),
        clock=clock,
        id_factory=ids,
    )
    adapter = DefaultScenario1ToolAdapter(
        read_service=read_service,
        proposal_service=proposal_service,
    )
    return adapter, store, cmdb, monitoring, itsm, kb


def test_full_six_tool_contract_integration_creates_valid_pending_proposal():
    adapter, store, _, _, _, _ = make_adapter()
    context = ToolCallContext(TENANT, RUN_ID)

    device = asyncio.run(adapter.get_device(context, GetDeviceRequest(DEVICE)))
    site = asyncio.run(adapter.get_site_health(context, GetSiteHealthRequest(SITE)))
    diagnostic = asyncio.run(
        adapter.run_diagnostic(
            context,
            RunDiagnosticRequest(DiagnosticType.ACCESS_LINK, ATTACHMENT),
        )
    )
    incidents = asyncio.run(
        adapter.search_incidents(
            context,
            SearchIncidentsRequest(IncidentSearchScope.DEVICE, DEVICE),
        )
    )
    kb = asyncio.run(adapter.search_kb(context, SearchKbRequest("local link failure")))

    assert device.ok and site.ok and diagnostic.ok and incidents.ok and kb.ok
    assert device.evidence.source_type is EvidenceSourceType.CMDB_SNAPSHOT
    assert site.evidence.source_type is EvidenceSourceType.SITE_HEALTH
    assert diagnostic.attachment_id == ATTACHMENT
    assert diagnostic.diagnostic == "LINK_DOWN"
    assert diagnostic.evidence.source_type is EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC
    assert incidents.evidence.source_type is EvidenceSourceType.INCIDENT_SEARCH
    assert kb.evidence[0].source_type is EvidenceSourceType.KB_ARTICLE

    proposal = asyncio.run(
        adapter.propose_field_visit(
            context,
            ProposeFieldVisitRequest(
                INCIDENT_ID,
                DEVICE,
                DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
                (
                    device.evidence.evidence_id,
                    site.evidence.evidence_id,
                    diagnostic.evidence.evidence_id,
                    kb.evidence[0].evidence_id,
                ),
                "Evidence supports local access-link failure; request onsite inspection.",
            ),
        )
    )

    assert proposal.ok
    assert proposal.proposal.status is ProposalStatus.PENDING_APPROVAL
    assert store.runs[(TENANT, RUN_ID)].status is RunStatus.WAITING_APPROVAL
    assert len(store.proposals) == 1
    assert len(store.evidence) == 5


def test_diagnostic_target_must_first_be_discovered_from_cmdb_evidence():
    adapter, store, _, monitoring, _, _ = make_adapter()

    result = asyncio.run(
        adapter.run_diagnostic(
            ToolCallContext(TENANT, RUN_ID),
            RunDiagnosticRequest(DiagnosticType.ACCESS_LINK, ATTACHMENT),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.ATTACHMENT_NOT_FOUND
    assert monitoring.diagnostic_calls == 0
    assert not store.evidence


def test_unknown_device_is_blocked_before_cmdb_call():
    adapter, store, cmdb, _, _, _ = make_adapter()

    result = asyncio.run(
        adapter.get_device(
            ToolCallContext(TENANT, RUN_ID),
            GetDeviceRequest("POS-UNKNOWN"),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.CONTEXT_MISMATCH
    assert cmdb.calls == 0
    assert not store.evidence


def test_cross_run_context_is_blocked_before_provider_call():
    adapter, store, cmdb, _, _, _ = make_adapter()

    result = asyncio.run(
        adapter.get_device(
            ToolCallContext(TENANT, "OTHER-RUN"),
            GetDeviceRequest(DEVICE),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.CONTEXT_MISMATCH
    assert cmdb.calls == 0
    assert not store.evidence


def test_cmdb_cannot_write_topology_from_unknown_site():
    adapter, store, _, _, _, _ = make_adapter(
        topology=replace(canonical_topology(), site_id="SITE-OTHER"),
    )

    result = asyncio.run(
        adapter.get_device(
            ToolCallContext(TENANT, RUN_ID),
            GetDeviceRequest(DEVICE),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert not store.evidence


def test_site_health_cannot_introduce_unowned_affected_device():
    adapter, store, _, _, _, _ = make_adapter(
        site_health=replace(
            canonical_site_health(),
            affected_device_id="POS-OTHER",
        ),
    )

    result = asyncio.run(
        adapter.get_site_health(
            ToolCallContext(TENANT, RUN_ID),
            GetSiteHealthRequest(SITE),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.SITE_HEALTH_UNAVAILABLE
    assert not store.evidence


def test_diagnostic_must_match_switch_and_port_discovered_by_cmdb():
    adapter, store, _, _, _, _ = make_adapter(
        diagnostic=replace(canonical_diagnostic(), port_id="Gi1/0/99"),
    )
    context = ToolCallContext(TENANT, RUN_ID)
    device = asyncio.run(adapter.get_device(context, GetDeviceRequest(DEVICE)))
    assert device.ok

    result = asyncio.run(
        adapter.run_diagnostic(
            context,
            RunDiagnosticRequest(DiagnosticType.ACCESS_LINK, ATTACHMENT),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.DIAGNOSTIC_UNAVAILABLE
    assert len(store.evidence) == 1


def test_dynamic_evidence_receives_configured_ttl():
    adapter, _, _, _, _, _ = make_adapter()
    context = ToolCallContext(TENANT, RUN_ID)

    device = asyncio.run(adapter.get_device(context, GetDeviceRequest(DEVICE)))
    site = asyncio.run(adapter.get_site_health(context, GetSiteHealthRequest(SITE)))
    diagnostic = asyncio.run(
        adapter.run_diagnostic(
            context,
            RunDiagnosticRequest(DiagnosticType.ACCESS_LINK, device.attachment_id),
        )
    )

    assert site.ok and diagnostic.ok
    assert site.evidence.expires_at == T0 + timedelta(minutes=5)
    assert diagnostic.evidence.expires_at == T0 + timedelta(minutes=2)
    assert device.evidence.expires_at is None


def test_search_kb_empty_result_is_valid_and_creates_no_fake_evidence():
    adapter, store, _, _, _, _ = make_adapter(kb_articles=())

    result = asyncio.run(
        adapter.search_kb(
            ToolCallContext(TENANT, RUN_ID),
            SearchKbRequest("unknown topic"),
        )
    )

    assert result.ok
    assert result.articles == ()
    assert result.evidence == ()
    assert not store.evidence


def test_invalid_kb_article_identity_is_rejected_before_evidence_write():
    adapter, store, _, _, _, _ = make_adapter(
        kb_articles=(replace(canonical_kb(), article_id=""),),
    )

    result = asyncio.run(
        adapter.search_kb(
            ToolCallContext(TENANT, RUN_ID),
            SearchKbRequest("local link"),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.KB_UNAVAILABLE
    assert not store.evidence


def test_provider_exception_is_normalized_without_raw_message():
    adapter, store, _, _, _, _ = make_adapter(cmdb_raises=True)

    result = asyncio.run(
        adapter.get_device(
            ToolCallContext(TENANT, RUN_ID),
            GetDeviceRequest(DEVICE),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert result.error.retryable is True
    assert "secret" not in result.error.message.lower()
    assert not store.evidence


def test_proposal_tool_cannot_bypass_deterministic_evidence_validator():
    adapter, store, _, _, _, _ = make_adapter()
    context = ToolCallContext(TENANT, RUN_ID)
    device = asyncio.run(adapter.get_device(context, GetDeviceRequest(DEVICE)))
    assert device.ok

    result = asyncio.run(
        adapter.propose_field_visit(
            context,
            ProposeFieldVisitRequest(
                INCIDENT_ID,
                DEVICE,
                DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
                (device.evidence.evidence_id,),
                "Please create visit anyway.",
            ),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE
    assert not store.proposals
    assert store.runs[(TENANT, RUN_ID)].status is RunStatus.ACTIVE


def test_read_tools_are_blocked_after_proposal_enters_waiting_approval():
    adapter, _, _, _, _, kb = make_adapter()
    context = ToolCallContext(TENANT, RUN_ID)

    device = asyncio.run(adapter.get_device(context, GetDeviceRequest(DEVICE)))
    site = asyncio.run(adapter.get_site_health(context, GetSiteHealthRequest(SITE)))
    diagnostic = asyncio.run(
        adapter.run_diagnostic(
            context,
            RunDiagnosticRequest(DiagnosticType.ACCESS_LINK, ATTACHMENT),
        )
    )
    kb_result = asyncio.run(adapter.search_kb(context, SearchKbRequest("local link")))
    proposal = asyncio.run(
        adapter.propose_field_visit(
            context,
            ProposeFieldVisitRequest(
                INCIDENT_ID,
                DEVICE,
                DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
                (
                    device.evidence.evidence_id,
                    site.evidence.evidence_id,
                    diagnostic.evidence.evidence_id,
                    kb_result.evidence[0].evidence_id,
                ),
                "Request onsite inspection.",
            ),
        )
    )
    assert proposal.ok
    calls_before = kb.calls

    blocked = asyncio.run(
        adapter.search_kb(
            context,
            SearchKbRequest("another query"),
        )
    )

    assert blocked.ok is False
    assert blocked.error.code is ErrorCode.INVALID_STATE_TRANSITION
    assert kb.calls == calls_before


def test_ttl_policy_rejects_non_positive_values():
    try:
        EvidenceTtlPolicy(
            site_health=timedelta(0),
            access_link_diagnostic=timedelta(minutes=1),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("zero site-health TTL must be rejected")

    try:
        EvidenceTtlPolicy(
            site_health=timedelta(minutes=1),
            access_link_diagnostic=timedelta(seconds=-1),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("negative diagnostic TTL must be rejected")
