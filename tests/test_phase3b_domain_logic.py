from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

from product_backend.application.field_visit import (
    FieldVisitApprovalService,
    FieldVisitProposalService,
)
from product_backend.contracts.tools import ProposeFieldVisitRequest, ToolCallContext
from product_backend.domain.enums import (
    ActionType,
    AdminState,
    ApprovalDecision,
    ConfigurationState,
    DiagnosisCode,
    EvidenceSourceType,
    HealthState,
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
    Approval,
    DeviceTopology,
    Evidence,
    ExecutedAction,
    FieldServiceWorkOrder,
    Incident,
    KbArticle,
    Run,
    SiteHealthSnapshot,
)

TENANT = "TENANT-8OCT"
RUN_ID = "RUN-001"
INCIDENT_ID = "INC-1042"
SITE = "SITE-KZN-017"
DEVICE = "POS-KZN17-02"
PEER = "POS-KZN17-01"
ATTACHMENT = "ATT-KZN17-POS02"
SWITCH = "SW-KZN17-01"
PORT = "Gi1/0/18"
T0 = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


@dataclass
class Store:
    runs: dict[tuple[str, str], Run] = field(default_factory=dict)
    incidents: dict[tuple[str, str, str], Incident] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    proposals: dict[str, ActionProposal] = field(default_factory=dict)
    approvals: dict[str, Approval] = field(default_factory=dict)
    actions: dict[str, ExecutedAction] = field(default_factory=dict)
    workorders: dict[str, FieldServiceWorkOrder] = field(default_factory=dict)


class RunRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, item: Run) -> None:
        self.store.runs[(item.tenant_id, item.run_id)] = item

    async def get(self, *, tenant_id: str, run_id: str) -> Run | None:
        return self.store.runs.get((tenant_id, run_id))

    async def save(self, item: Run) -> None:
        self.store.runs[(item.tenant_id, item.run_id)] = item


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

    async def save(self, item: Incident) -> None:
        self.store.incidents[(item.tenant_id, item.run_id, item.incident_id)] = item


class EvidenceRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, item: Evidence) -> None:
        self.store.evidence[item.evidence_id] = item

    async def get_many(
        self,
        *,
        tenant_id: str,
        run_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[Evidence, ...]:
        result = []
        for evidence_id in evidence_ids:
            item = self.store.evidence.get(evidence_id)
            if item and item.tenant_id == tenant_id and item.run_id == run_id:
                result.append(item)
        return tuple(result)


class ProposalRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, item: ActionProposal) -> None:
        self.store.proposals[item.proposal_id] = item

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

    async def save(self, item: ActionProposal) -> None:
        self.store.proposals[item.proposal_id] = item

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


class ApprovalRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, item: Approval) -> None:
        self.store.approvals[item.proposal_id] = item

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> Approval | None:
        item = self.store.approvals.get(proposal_id)
        if item and item.tenant_id == tenant_id and item.run_id == run_id:
            return item
        return None


class ActionRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, item: ExecutedAction) -> None:
        self.store.actions[item.action_id] = item

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> ExecutedAction | None:
        return next(
            (
                item
                for item in self.store.actions.values()
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
        run_id: str,
        incident_id: str,
        device_id: str,
        action_type: ActionType,
    ) -> ExecutedAction | None:
        return next(
            (
                item
                for item in self.store.actions.values()
                if item.tenant_id == tenant_id
                and item.run_id == run_id
                and item.incident_id == incident_id
                and item.device_id == device_id
                and item.action_type is action_type
            ),
            None,
        )


class WorkOrderRepo:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def add(self, item: FieldServiceWorkOrder) -> None:
        self.store.workorders[item.work_order_id] = item

    async def get_for_proposal(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
    ) -> FieldServiceWorkOrder | None:
        return next(
            (
                item
                for item in self.store.workorders.values()
                if item.tenant_id == tenant_id
                and item.run_id == run_id
                and item.proposal_id == proposal_id
            ),
            None,
        )

    async def get_for_incident(
        self,
        *,
        tenant_id: str,
        run_id: str,
        incident_id: str,
    ) -> FieldServiceWorkOrder | None:
        return next(
            (
                item
                for item in self.store.workorders.values()
                if item.tenant_id == tenant_id
                and item.run_id == run_id
                and item.incident_id == incident_id
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
        self.approvals = ApprovalRepo(store)
        self.executed_actions = ActionRepo(store)
        self.work_orders = WorkOrderRepo(store)
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
        self.store.approvals = self._snapshot.approvals
        self.store.actions = self._snapshot.actions
        self.store.workorders = self._snapshot.workorders


class FakeCmdb:
    def __init__(self, topology: DeviceTopology | None) -> None:
        self.topology = topology

    async def get_device(
        self,
        *,
        tenant_id: str,
        run_id: str,
        device_id: str,
    ) -> DeviceTopology | None:
        if tenant_id != TENANT or run_id != RUN_ID or self.topology is None:
            return None
        if self.topology.device_id != device_id:
            return None
        return self.topology


class FakeMonitoring:
    def __init__(
        self,
        diagnostic: AccessLinkDiagnosticSnapshot | None,
    ) -> None:
        self.diagnostic = diagnostic

    async def get_site_health(self, *, tenant_id: str, run_id: str, site_id: str):
        return None

    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type,
        target_id: str,
    ) -> AccessLinkDiagnosticSnapshot | None:
        if tenant_id != TENANT or run_id != RUN_ID or self.diagnostic is None:
            return None
        if self.diagnostic.target_id != target_id:
            return None
        return self.diagnostic


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class Ids:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def __call__(self, prefix: str) -> str:
        self.counts[prefix] = self.counts.get(prefix, 0) + 1
        return f"{prefix.upper()}-{self.counts[prefix]:03d}"


def approval_service(
    store: Store,
    *,
    clock: Clock,
    ids: Ids,
    topology: DeviceTopology | None = None,
    diagnostic: AccessLinkDiagnosticSnapshot | None = None,
) -> FieldVisitApprovalService:
    if topology is None:
        topology = store.evidence["E-CMDB"].payload
    if diagnostic is None:
        diagnostic = store.evidence["E-DIAG"].payload
    return FieldVisitApprovalService(
        lambda: Uow(store),
        cmdb=FakeCmdb(topology),
        monitoring=FakeMonitoring(diagnostic),
        clock=clock,
        id_factory=ids,
    )


def make_store(
    *,
    dynamic_expiry: datetime = T0 + timedelta(minutes=5),
) -> Store:
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
    evidence = [
        Evidence(
            "E-CMDB",
            TENANT,
            RUN_ID,
            EvidenceSourceType.CMDB_SNAPSHOT,
            T0,
            (DEVICE, SITE, ATTACHMENT, SWITCH, PORT),
            DeviceTopology(
                DEVICE,
                SITE,
                ATTACHMENT,
                "POS_TERMINAL",
                SWITCH,
                PORT,
            ),
        ),
        Evidence(
            "E-SITE",
            TENANT,
            RUN_ID,
            EvidenceSourceType.SITE_HEALTH,
            T0,
            (SITE, PEER, DEVICE),
            SiteHealthSnapshot(
                SITE,
                HealthState.HEALTHY,
                HealthState.HEALTHY,
                PEER,
                True,
                DEVICE,
                False,
            ),
            expires_at=dynamic_expiry,
        ),
        Evidence(
            "E-DIAG",
            TENANT,
            RUN_ID,
            EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
            T0,
            (ATTACHMENT, SWITCH, PORT),
            AccessLinkDiagnosticSnapshot(
                ATTACHMENT,
                ATTACHMENT,
                SWITCH,
                PORT,
                True,
                AdminState.UP,
                OperationalState.DOWN,
                PortSecurityState.NORMAL,
                ConfigurationState.EXPECTED,
            ),
            expires_at=dynamic_expiry,
        ),
        Evidence(
            "E-KB",
            TENANT,
            RUN_ID,
            EvidenceSourceType.KB_ARTICLE,
            T0,
            ("KB-LOCAL-LINK",),
            KbArticle(
                "KB-LOCAL-LINK",
                "Physical access path inspection",
                True,
                (DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,),
                (ActionType.ONSITE_FIELD_VISIT,),
            ),
        ),
    ]
    store.evidence = {item.evidence_id: item for item in evidence}
    return store


def request(
    evidence_ids: tuple[str, ...] = ("E-CMDB", "E-SITE", "E-DIAG", "E-KB"),
) -> ProposeFieldVisitRequest:
    return ProposeFieldVisitRequest(
        INCIDENT_ID,
        DEVICE,
        DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
        evidence_ids,
        "Evidence supports a local access-link failure; request onsite inspection.",
    )


def create_proposal(
    store: Store,
    clock: Clock | None = None,
    ids: Ids | None = None,
):
    clock = clock or Clock(T0 + timedelta(minutes=1))
    ids = ids or Ids()
    service = FieldVisitProposalService(
        lambda: Uow(store),
        clock=clock,
        id_factory=ids,
    )
    return asyncio.run(
        service.create(
            ToolCallContext(TENANT, RUN_ID),
            request(),
        )
    )


def test_canonical_evidence_creates_only_pending_proposal_and_wait_state():
    store = make_store()
    result = create_proposal(store)

    assert result.ok is True
    assert result.proposal.status is ProposalStatus.PENDING_APPROVAL
    assert store.runs[(TENANT, RUN_ID)].status is RunStatus.WAITING_APPROVAL
    assert not store.approvals
    assert not store.actions
    assert not store.workorders


def test_missing_required_evidence_is_rejected_without_mutation():
    store = make_store()
    service = FieldVisitProposalService(
        lambda: Uow(store),
        clock=Clock(T0 + timedelta(minutes=1)),
        id_factory=Ids(),
    )
    result = asyncio.run(
        service.create(
            ToolCallContext(TENANT, RUN_ID),
            request(("E-CMDB", "E-SITE", "E-DIAG")),
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE
    assert store.runs[(TENANT, RUN_ID)].status is RunStatus.ACTIVE
    assert not store.proposals


def test_cross_run_evidence_is_rejected():
    store = make_store()
    store.evidence["E-KB"] = replace(
        store.evidence["E-KB"],
        run_id="OTHER-RUN",
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_expired_dynamic_evidence_is_rejected_at_proposal_boundary():
    store = make_store(dynamic_expiry=T0 + timedelta(seconds=30))

    result = create_proposal(
        store,
        Clock(T0 + timedelta(minutes=1)),
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_wrong_access_link_pattern_is_rejected():
    store = make_store()
    diagnostic = store.evidence["E-DIAG"]
    store.evidence["E-DIAG"] = replace(
        diagnostic,
        payload=replace(
            diagnostic.payload,
            port_security=PortSecurityState.VIOLATION,
        ),
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_valid_approve_executes_once_escalates_incident_and_resumes_run():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok is True
    assert result.proposal.status is ProposalStatus.EXECUTED
    assert result.incident.status is IncidentStatus.ESCALATED
    assert result.executed_action is not None
    assert result.work_order is not None
    assert result.work_order.site_id == SITE
    assert result.work_order.attachment_id == ATTACHMENT
    assert result.work_order.switch_id == SWITCH
    assert result.work_order.port_id == PORT
    assert len(store.actions) == 1
    assert len(store.workorders) == 1
    assert len(store.approvals) == 1
    assert store.runs[(TENANT, RUN_ID)].status is RunStatus.ACTIVE


def test_repeated_approve_returns_stored_result_and_creates_no_duplicate():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    first = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )
    second = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert first.ok
    assert second.ok
    assert second.replayed is True
    assert second.approval.approval_id == first.approval.approval_id
    assert second.executed_action.action_id == first.executed_action.action_id
    assert second.work_order.work_order_id == first.work_order.work_order_id
    assert len(store.actions) == 1
    assert len(store.workorders) == 1
    assert len(store.approvals) == 1


def test_reject_records_human_decision_and_never_executes():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.REJECTED,
            decided_by="human-1",
        )
    )

    assert result.ok
    assert result.proposal.status is ProposalStatus.REJECTED
    assert result.incident.status is IncidentStatus.OPEN
    assert result.executed_action is None
    assert result.work_order is None
    assert not store.actions
    assert not store.workorders
    assert store.runs[(TENANT, RUN_ID)].status is RunStatus.ACTIVE


def test_approve_when_current_link_is_no_longer_down_records_approved_but_marks_stale():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    current_diagnostic = replace(
        store.evidence["E-DIAG"].payload,
        operational_state=OperationalState.UP,
    )
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
        diagnostic=current_diagnostic,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok
    assert result.approval.decision is ApprovalDecision.APPROVED
    assert result.proposal.status is ProposalStatus.STALE
    assert result.incident.status is IncidentStatus.OPEN
    assert not store.actions
    assert not store.workorders


def test_approve_when_equivalent_action_already_exists_marks_stale_no_second_action():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    existing = ExecutedAction(
        "ACTION-EXISTING",
        TENANT,
        RUN_ID,
        "OTHER-PROP",
        INCIDENT_ID,
        DEVICE,
        ActionType.ONSITE_FIELD_VISIT,
        T0,
    )
    store.actions[existing.action_id] = existing
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok
    assert result.proposal.status is ProposalStatus.STALE
    assert len(store.actions) == 1
    assert not store.workorders


def test_conflicting_second_human_decision_is_rejected():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    first = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.REJECTED,
            decided_by="human-1",
        )
    )
    second = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert first.ok
    assert second.ok is False
    assert second.error.code is ErrorCode.PROPOSAL_NOT_PENDING
    assert not store.actions
    assert not store.workorders


def test_duplicate_pending_proposal_is_blocked():
    store = make_store()
    ids = Ids()
    first = create_proposal(store, ids=ids)
    store.runs[(TENANT, RUN_ID)] = replace(
        store.runs[(TENANT, RUN_ID)],
        status=RunStatus.ACTIVE,
    )

    second = create_proposal(store, ids=ids)

    assert first.ok
    assert second.ok is False
    assert second.error.code is ErrorCode.INVALID_PROPOSAL
    assert len(store.proposals) == 1


def test_approve_when_incident_is_no_longer_open_records_approved_but_marks_stale():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    incident = store.incidents[(TENANT, RUN_ID, INCIDENT_ID)]
    store.incidents[(TENANT, RUN_ID, INCIDENT_ID)] = replace(
        incident,
        status=IncidentStatus.ESCALATED,
    )
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok
    assert result.approval.decision is ApprovalDecision.APPROVED
    assert result.proposal.status is ProposalStatus.STALE
    assert not store.actions
    assert not store.workorders


def test_approve_when_work_order_already_exists_marks_stale_no_second_work_order():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    existing = FieldServiceWorkOrder(
        "WO-EXISTING",
        TENANT,
        RUN_ID,
        "OTHER-PROP",
        INCIDENT_ID,
        DEVICE,
        SITE,
        ATTACHMENT,
        SWITCH,
        PORT,
        T0,
    )
    store.workorders[existing.work_order_id] = existing
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok
    assert result.proposal.status is ProposalStatus.STALE
    assert len(store.workorders) == 1
    assert not store.actions


def test_repeated_approve_of_stale_proposal_replays_same_blocked_result():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    current_diagnostic = replace(
        store.evidence["E-DIAG"].payload,
        operational_state=OperationalState.UP,
    )
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
        diagnostic=current_diagnostic,
    )

    first = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )
    second = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert first.ok
    assert second.ok
    assert second.replayed is True
    assert second.approval.approval_id == first.approval.approval_id
    assert second.proposal.status is ProposalStatus.STALE
    assert second.executed_action is None
    assert second.work_order is None
    assert len(store.approvals) == 1
    assert not store.actions
    assert not store.workorders


def test_invalid_runtime_decision_value_is_rejected_before_mutation():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision="APPROVED",
            decided_by="human-1",
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.INVALID_ARGUMENT
    assert not store.approvals
    assert not store.actions
    assert not store.workorders
    assert store.proposals[proposal_id].status is ProposalStatus.PENDING_APPROVAL


def test_approve_when_current_cmdb_relationship_changed_marks_stale():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    changed_topology = replace(
        store.evidence["E-CMDB"].payload,
        expected_port_id="Gi1/0/99",
    )
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
        topology=changed_topology,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok
    assert result.proposal.status is ProposalStatus.STALE
    assert not store.actions
    assert not store.workorders


def test_evidence_entity_ids_must_match_typed_payload_relationships():
    store = make_store()
    store.evidence["E-CMDB"] = replace(
        store.evidence["E-CMDB"],
        entity_ids=(DEVICE, SITE),
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_proposal_rejects_diagnostic_run_for_wrong_target_even_if_payload_looks_right():
    store = make_store()
    store.evidence["E-DIAG"] = replace(
        store.evidence["E-DIAG"],
        payload=replace(
            store.evidence["E-DIAG"].payload,
            target_id="ATT-OTHER",
        ),
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


class MissingCmdb:
    async def get_device(self, *, tenant_id: str, run_id: str, device_id: str):
        return None


class RaisingCmdb:
    async def get_device(self, *, tenant_id: str, run_id: str, device_id: str):
        raise RuntimeError("provider secret should never escape")


class MissingMonitoring:
    async def get_site_health(self, *, tenant_id: str, run_id: str, site_id: str):
        return None

    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type,
        target_id: str,
    ):
        return None


class RaisingMonitoring(MissingMonitoring):
    async def run_diagnostic(
        self,
        *,
        tenant_id: str,
        run_id: str,
        diagnostic_type,
        target_id: str,
    ):
        raise RuntimeError("provider secret should never escape")


def _approval_service_with_ports(store: Store, ids: Ids, cmdb, monitoring):
    return FieldVisitApprovalService(
        lambda: Uow(store),
        cmdb=cmdb,
        monitoring=monitoring,
        clock=Clock(T0 + timedelta(minutes=2)),
        id_factory=ids,
    )


def test_authoritative_missing_cmdb_state_marks_approved_proposal_stale():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = _approval_service_with_ports(
        store,
        ids,
        MissingCmdb(),
        FakeMonitoring(store.evidence["E-DIAG"].payload),
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok is True
    assert result.approval.decision is ApprovalDecision.APPROVED
    assert result.proposal.status is ProposalStatus.STALE
    assert store.runs[(TENANT, RUN_ID)].status is RunStatus.ACTIVE
    assert len(store.approvals) == 1
    assert not store.actions
    assert not store.workorders


def test_cmdb_exception_is_normalized_and_does_not_escape_or_consume_approval():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = _approval_service_with_ports(
        store,
        ids,
        RaisingCmdb(),
        FakeMonitoring(store.evidence["E-DIAG"].payload),
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert result.error.retryable is True
    assert "secret" not in result.error.message.lower()
    assert store.proposals[proposal_id].status is ProposalStatus.PENDING_APPROVAL
    assert not store.approvals


def test_authoritative_missing_diagnostic_marks_approved_proposal_stale():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = _approval_service_with_ports(
        store,
        ids,
        FakeCmdb(store.evidence["E-CMDB"].payload),
        MissingMonitoring(),
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok is True
    assert result.approval.decision is ApprovalDecision.APPROVED
    assert result.proposal.status is ProposalStatus.STALE
    assert len(store.approvals) == 1
    assert not store.actions
    assert not store.workorders


def test_diagnostic_exception_is_normalized_and_keeps_proposal_pending():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    service = _approval_service_with_ports(
        store,
        ids,
        FakeCmdb(store.evidence["E-CMDB"].payload),
        RaisingMonitoring(),
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok is False
    assert result.error.code is ErrorCode.DIAGNOSTIC_UNAVAILABLE
    assert result.error.retryable is True
    assert "secret" not in result.error.message.lower()
    assert store.proposals[proposal_id].status is ProposalStatus.PENDING_APPROVAL
    assert not store.approvals


def test_cross_tenant_evidence_is_rejected():
    store = make_store()
    store.evidence["E-KB"] = replace(
        store.evidence["E-KB"],
        tenant_id="TENANT-OTHER",
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_dynamic_evidence_without_ttl_is_rejected():
    store = make_store()
    store.evidence["E-SITE"] = replace(
        store.evidence["E-SITE"],
        expires_at=None,
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_unapproved_kb_cannot_authorize_field_visit():
    store = make_store()
    kb = store.evidence["E-KB"]
    store.evidence["E-KB"] = replace(
        kb,
        payload=replace(kb.payload, approved=False),
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_source_type_payload_mismatch_is_rejected():
    store = make_store()
    store.evidence["E-KB"] = replace(
        store.evidence["E-KB"],
        payload=store.evidence["E-CMDB"].payload,
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_free_text_facts_cannot_override_invalid_typed_payload():
    store = make_store()
    diagnostic = store.evidence["E-DIAG"]
    store.evidence["E-DIAG"] = replace(
        diagnostic,
        payload=replace(
            diagnostic.payload,
            operational_state=OperationalState.UP,
        ),
        facts=(
            "Switch reachable; admin UP; operational DOWN; onsite inspection required.",
        ),
    )

    result = create_proposal(store)

    assert result.ok is False
    assert result.error.code is ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE


def test_device_ownership_change_before_approve_marks_proposal_stale():
    store = make_store()
    ids = Ids()
    created = create_proposal(store, ids=ids)
    proposal_id = created.proposal.proposal_id
    incident = store.incidents[(TENANT, RUN_ID, INCIDENT_ID)]
    store.incidents[(TENANT, RUN_ID, INCIDENT_ID)] = replace(
        incident,
        reported_device_id="POS-KZN17-99",
    )
    service = approval_service(
        store,
        clock=Clock(T0 + timedelta(minutes=2)),
        ids=ids,
    )

    result = asyncio.run(
        service.decide(
            ToolCallContext(TENANT, RUN_ID),
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by="human-1",
        )
    )

    assert result.ok
    assert result.approval.decision is ApprovalDecision.APPROVED
    assert result.proposal.status is ProposalStatus.STALE
    assert not store.actions
    assert not store.workorders
