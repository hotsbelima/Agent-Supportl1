from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta
import os
from typing import Any
from uuid import uuid4

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import Field, PrivateAttr

import agent_runtime.scenario3_service as scenario3_service_module
from agent_runtime.human_decision import (
    WAIT_FOR_HUMAN_DECISION_TOOL,
    build_human_decision_wait_tool,
)
from agent_runtime.scenario3_agent import (
    SCENARIO3_AGENT_INSTRUCTION,
    SCENARIO3_AGENT_NAME,
)
from agent_runtime.scenario3_service import Scenario3AgentRuntime
from agent_runtime.scenario3_tools import Scenario3AdkTools
from agent_runtime.sessions import (
    create_database_session_service,
    ensure_run_session,
    get_run_session,
)
from product_api.scenario1_fixture import Scenario1FixtureSources
from product_api.scenario3_fixture import (
    AFFECTED_DEVICE_ID,
    ATTACHMENT_ID,
    INCIDENT_ID,
    SCENARIO_ID,
    SERVICE_KEY,
    SITE_ID,
    Scenario3FixtureSources,
)
from product_api.scenario3_sources import (
    ACMEPAY_DEPENDENCY_ID,
    Scenario3ProviderSources,
)
from product_backend.adapters.scenario3_tool_adapters import (
    DefaultScenario3ToolAdapter,
)
from product_backend.adapters.tool_adapters import DefaultScenario1ToolAdapter
from product_backend.application.field_visit import (
    FieldVisitApprovalService,
    FieldVisitProposalService,
)
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.read_tools import (
    EvidenceTtlPolicy,
    Scenario1ReadToolService,
)
from product_backend.application.run_lifecycle import Scenario1RunStartService
from product_backend.application.run_state import RunStateService
from product_backend.application.scenario3_provider_reads import (
    Scenario3ProviderEvidenceTtlPolicy,
    Scenario3ProviderReadService,
)
from product_backend.contracts.events import ApplicationEventType
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import (
    ApprovalDecision,
    DiagnosisCode,
    EvidenceSourceType,
    HealthState,
    OperationalState,
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
    SqlAlchemyApprovalExecutionUnitOfWork,
    SqlAlchemyLifecycleUnitOfWork,
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyRunStartUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)


PRIVATE_THOUGHT_MARKER = "PHASE8D_PRIVATE_REASONING_MUST_NOT_ENTER_PRODUCT_STATE"

PROVIDER_EVIDENCE_IDS = (
    "EVID-S3-PROVIDER-MAPPING",
    "EVID-S3-PROVIDER-STATUS",
)
LOCAL_EVIDENCE_IDS = (
    "EVID-S3-CMDB",
    "EVID-S3-SITE",
    "EVID-S3-LINK",
    "EVID-S3-KB",
)
EXPECTED_TOOL_TRACE = [
    "get_service_dependencies",
    "get_external_dependency_status",
    "get_device",
    "get_site_health",
    "run_diagnostic",
    "search_kb",
    "propose_field_visit",
    WAIT_FOR_HUMAN_DECISION_TOOL,
]


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 8D deterministic tests")
    return normalize_database_url(value)


class _SequenceIdFactory:
    def __init__(self, values: tuple[str, ...]) -> None:
        self._values = list(values)

    def __call__(self, prefix: str) -> str:
        if not self._values:
            raise AssertionError(f"Unexpected additional ID request for {prefix}")
        return self._values.pop(0)


class _ScriptedTraceModel(BaseLlm):
    model: str = "phase8d-scripted-scenario3"
    steps: list[Any]
    requests: list[LlmRequest] = Field(default_factory=list)
    _index: int = PrivateAttr(default=0)

    async def generate_content_async(
        self,
        llm_request: LlmRequest,
        stream: bool = False,
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        self.requests.append(llm_request)
        if self._index >= len(self.steps):
            raise AssertionError("Phase 8D scripted model ran out of responses")
        step = self.steps[self._index]
        self._index += 1
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, LlmResponse):
            yield step
            return
        if isinstance(step, types.Part):
            yield LlmResponse(
                content=types.Content(role="model", parts=[step])
            )
            return
        if isinstance(step, str):
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text=step)],
                )
            )
            return
        raise TypeError(f"Unsupported scripted model step: {type(step)!r}")


def _call(
    name: str,
    args: dict[str, Any],
    *,
    hidden_thought: str | None = None,
) -> LlmResponse:
    parts: list[types.Part] = []
    if hidden_thought is not None:
        parts.append(types.Part(text=hidden_thought, thought=True))
    parts.append(types.Part.from_function_call(name=name, args=args))
    return LlmResponse(content=types.Content(role="model", parts=parts))


def _scenario3_steps(
    proposal_id: str,
    *,
    final_answer: str = "Human decision committed from Product truth.",
) -> list[Any]:
    return [
        _call(
            "get_service_dependencies",
            {"service_key": SERVICE_KEY},
            hidden_thought=PRIVATE_THOUGHT_MARKER,
        ),
        _call(
            "get_external_dependency_status",
            {"dependency_id": ACMEPAY_DEPENDENCY_ID},
        ),
        _call(
            "get_device",
            {"device_id": AFFECTED_DEVICE_ID},
        ),
        _call(
            "get_site_health",
            {"site_id": SITE_ID},
        ),
        _call(
            "run_diagnostic",
            {
                "diagnostic_type": "ACCESS_LINK",
                "target_id": ATTACHMENT_ID,
            },
        ),
        _call(
            "search_kb",
            {"query": "local access link failure onsite field visit"},
        ),
        _call(
            "propose_field_visit",
            {
                "incident_id": INCIDENT_ID,
                "device_id": AFFECTED_DEVICE_ID,
                "diagnosis": "LOCAL_ACCESS_LINK_FAILURE",
                "evidence_ids": list(LOCAL_EVIDENCE_IDS),
                "rationale": (
                    "AcmePay is healthy; independent CMDB, site health, "
                    "access-link DOWN and approved KB evidence support an "
                    "onsite field visit for the affected terminal."
                ),
            },
        ),
        _call(
            WAIT_FOR_HUMAN_DECISION_TOOL,
            {"proposal_id": proposal_id},
        ),
        final_answer,
    ]


def _build_scripted_agent(adapter, model: BaseLlm) -> LlmAgent:
    tools = Scenario3AdkTools(adapter)
    return LlmAgent(
        name=SCENARIO3_AGENT_NAME,
        model=model,
        instruction=SCENARIO3_AGENT_INSTRUCTION,
        tools=[
            *tools.functions(),
            build_human_decision_wait_tool(),
        ],
    )


def _approval_id_factory(namespace: str):
    values = {
        "approval": f"APPROVAL-{namespace}",
        "action": f"ACTION-{namespace}",
        "workorder": f"WORKORDER-{namespace}",
    }

    def factory(prefix: str) -> str:
        try:
            return values[prefix]
        except KeyError as exc:
            raise AssertionError(f"Unexpected approval ID prefix: {prefix}") from exc

    return factory


async def _build_stack(
    monkeypatch,
    *,
    namespace: str,
    model: BaseLlm,
):
    engine = create_engine(DatabaseSettings(url=_database_url()))
    factory = create_session_factory(engine)

    shared_access_link_overrides: dict[tuple[str, str], OperationalState] = {}
    approval_fixture = Scenario1FixtureSources(shared_access_link_overrides)
    scenario3_fixture = Scenario3FixtureSources(shared_access_link_overrides)
    provider_sources = Scenario3ProviderSources()

    state_service = RunStateService(SqlAlchemyRunStateQuery(factory))
    lifecycle_service = ApplicationLifecycleService(
        lambda: SqlAlchemyLifecycleUnitOfWork(factory)
    )
    start_service = Scenario1RunStartService(
        lambda: SqlAlchemyRunStartUnitOfWork(factory),
        id_factory=lambda prefix: (
            f"RUN-{namespace}"
            if prefix == "run"
            else (_ for _ in ()).throw(
                AssertionError(f"Unexpected start ID prefix: {prefix}")
            )
        ),
    )

    provider_read_service = Scenario3ProviderReadService(
        read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
        dependency_mapping=provider_sources,
        dependency_status=provider_sources,
        ttl_policy=Scenario3ProviderEvidenceTtlPolicy(
            external_dependency_status=timedelta(minutes=2),
        ),
        id_factory=_SequenceIdFactory(PROVIDER_EVIDENCE_IDS),
    )
    local_read_service = Scenario1ReadToolService(
        read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(factory),
        cmdb=scenario3_fixture,
        monitoring=scenario3_fixture,
        itsm=scenario3_fixture,
        kb=scenario3_fixture,
        ttl_policy=EvidenceTtlPolicy(
            site_health=timedelta(minutes=5),
            access_link_diagnostic=timedelta(minutes=2),
        ),
        id_factory=_SequenceIdFactory(LOCAL_EVIDENCE_IDS),
    )
    proposal_id = f"PROPOSAL-{namespace}"
    proposal_service = FieldVisitProposalService(
        lambda: SqlAlchemyProposalCreationUnitOfWork(factory),
        id_factory=lambda prefix: (
            proposal_id
            if prefix == "proposal"
            else (_ for _ in ()).throw(
                AssertionError(f"Unexpected proposal ID prefix: {prefix}")
            )
        ),
    )
    local_adapter = DefaultScenario1ToolAdapter(
        read_service=local_read_service,
        proposal_service=proposal_service,
    )
    adapter = DefaultScenario3ToolAdapter(
        provider_read_service=provider_read_service,
        local_adapter=local_adapter,
    )
    approval_service = FieldVisitApprovalService(
        lambda: SqlAlchemyApprovalExecutionUnitOfWork(factory),
        cmdb=approval_fixture,
        monitoring=approval_fixture,
        id_factory=_approval_id_factory(namespace),
    )

    session_service = create_database_session_service(engine)
    await session_service.prepare_tables()

    monkeypatch.setattr(
        scenario3_service_module,
        "build_scenario3_agent",
        lambda actual_adapter: _build_scripted_agent(actual_adapter, model),
    )
    runtime = Scenario3AgentRuntime(
        adapter=adapter,
        session_service=session_service,
    )

    return {
        "engine": engine,
        "factory": factory,
        "state": state_service,
        "lifecycle": lifecycle_service,
        "start": start_service,
        "approval": approval_service,
        "approval_fixture": approval_fixture,
        "scenario3_fixture": scenario3_fixture,
        "adapter": adapter,
        "session_service": session_service,
        "runtime": runtime,
        "proposal_id": proposal_id,
    }


async def _start_and_pause(stack, tenant_id: str):
    started = await stack["start"].start(
        tenant_id=tenant_id,
        bootstrap=stack["scenario3_fixture"].bootstrap(),
    )
    run_id = started.run.run_id
    assert started.run.scenario_id == SCENARIO_ID

    await ensure_run_session(
        stack["session_service"],
        tenant_id=tenant_id,
        run_id=run_id,
    )

    timeline = await stack["lifecycle"].timeline(
        ToolCallContext(tenant_id=tenant_id, run_id=run_id),
        after_seq=0,
        limit=100,
    )
    signal_event = next(
        event
        for event in timeline
        if event.event_type is ApplicationEventType.EXTERNAL_SIGNAL
    )

    snapshot = await stack["state"].get(
        tenant_id=tenant_id,
        run_id=run_id,
    )
    assert snapshot is not None
    operational_signal = {
        "event_id": signal_event.event_id,
        "event_seq": signal_event.seq,
        "scenario_id": snapshot.run.scenario_id,
        "signal": signal_event.payload,
        "incidents": [
            {
                "incident_id": incident.incident_id,
                "site_id": incident.site_id,
                "reported_device_id": incident.reported_device_id,
                "symptom": incident.symptom,
                "status": incident.status.value,
            }
            for incident in snapshot.incidents
        ],
    }

    paused = await stack["runtime"].invoke_operational_event(
        tenant_id=tenant_id,
        run_id=run_id,
        operational_event_id=signal_event.event_id,
        operational_signal=operational_signal,
    )
    assert paused.session_id == run_id
    assert paused.invocation_id is not None
    assert paused.awaiting_human_decision is True
    assert paused.pending_proposal_id == stack["proposal_id"]
    assert paused.paused_function_call_id is not None

    return run_id, signal_event.event_id, operational_signal, paused


def _tool_call_trace(session) -> list[str]:
    names: list[str] = []
    for event in session.events:
        get_calls = getattr(event, "get_function_calls", None)
        for call in (get_calls() if callable(get_calls) else []):
            names.append(call.name)
    return names


def _tool_call_invocation_ids(session) -> set[str]:
    invocation_ids: set[str] = set()
    for event in session.events:
        get_calls = getattr(event, "get_function_calls", None)
        calls = get_calls() if callable(get_calls) else []
        if calls and event.invocation_id:
            invocation_ids.add(event.invocation_id)
    return invocation_ids


def _decision_payload(result) -> dict[str, Any]:
    executed_action = (
        {
            "action_id": result.executed_action.action_id,
            "action_type": result.executed_action.action_type.value,
        }
        if result.executed_action is not None
        else None
    )
    work_order = (
        {
            "work_order_id": result.work_order.work_order_id,
            "site_id": result.work_order.site_id,
            "attachment_id": result.work_order.attachment_id,
        }
        if result.work_order is not None
        else None
    )
    return {
        "status": "human_decision_committed",
        "decision": result.approval.decision.value,
        "proposal_id": result.proposal.proposal_id,
        "proposal_status": result.proposal.status.value,
        "incident_id": result.incident.incident_id,
        "incident_status": result.incident.status.value,
        "executed_action": executed_action,
        "work_order": work_order,
        "repair_confirmed": False,
        "replayed": result.replayed,
    }


async def _close_stack(stack) -> None:
    await stack["runtime"].close()
    await stack["engine"].dispose()


def test_phase8d_canonical_trace_approve_replay_and_no_product_cot(
    monkeypatch,
):
    async def scenario() -> None:
        namespace = f"8D-A-{uuid4().hex[:8]}"
        tenant_id = f"TENANT-{namespace}"
        model = _ScriptedTraceModel(
            steps=_scenario3_steps(f"PROPOSAL-{namespace}")
        )
        stack = await _build_stack(
            monkeypatch,
            namespace=namespace,
            model=model,
        )
        try:
            run_id, _, _, paused = await _start_and_pause(stack, tenant_id)

            session = await get_run_session(
                stack["session_service"],
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            assert session.id == run_id
            assert _tool_call_trace(session) == EXPECTED_TOOL_TRACE
            assert _tool_call_invocation_ids(session) == {paused.invocation_id}

            correlation = await stack["runtime"].find_human_decision_correlation(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=stack["proposal_id"],
            )
            assert correlation is not None
            assert correlation.invocation_id == paused.invocation_id
            assert correlation.function_call_id == paused.paused_function_call_id
            assert correlation.proposal_id == stack["proposal_id"]

            timeline = await stack["lifecycle"].timeline(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                after_seq=0,
                limit=100,
            )
            observation_types = [
                event.payload["source_type"]
                for event in timeline
                if event.event_type is ApplicationEventType.OBSERVATION_RECORDED
            ]
            assert observation_types == [
                EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING.value,
                EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS.value,
                EvidenceSourceType.CMDB_SNAPSHOT.value,
                EvidenceSourceType.SITE_HEALTH.value,
                EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC.value,
                EvidenceSourceType.KB_ARTICLE.value,
            ]

            snapshot = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert snapshot is not None
            assert snapshot.run.status is RunStatus.WAITING_APPROVAL
            assert {item.source_type for item in snapshot.evidence} == {
                EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING,
                EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS,
                EvidenceSourceType.CMDB_SNAPSHOT,
                EvidenceSourceType.SITE_HEALTH,
                EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC,
                EvidenceSourceType.KB_ARTICLE,
            }
            evidence_by_type = {
                item.source_type: item
                for item in snapshot.evidence
            }
            mapping = evidence_by_type[
                EvidenceSourceType.SERVICE_DEPENDENCY_MAPPING
            ]
            provider_status = evidence_by_type[
                EvidenceSourceType.EXTERNAL_DEPENDENCY_STATUS
            ]
            cmdb = evidence_by_type[EvidenceSourceType.CMDB_SNAPSHOT]
            site_health = evidence_by_type[EvidenceSourceType.SITE_HEALTH]
            access_link = evidence_by_type[
                EvidenceSourceType.ACCESS_LINK_DIAGNOSTIC
            ]
            kb_article = evidence_by_type[EvidenceSourceType.KB_ARTICLE]

            assert mapping.payload.service_key == SERVICE_KEY
            assert mapping.payload.dependency_id == ACMEPAY_DEPENDENCY_ID
            assert provider_status.payload.dependency_id == ACMEPAY_DEPENDENCY_ID
            assert provider_status.payload.status is HealthState.HEALTHY

            assert cmdb.payload.device_id == AFFECTED_DEVICE_ID
            assert cmdb.payload.attachment_id == ATTACHMENT_ID
            assert site_health.payload.site_network is HealthState.HEALTHY
            assert site_health.payload.peer_reachable is True
            assert site_health.payload.affected_device_reachable is False
            assert access_link.payload.operational_state is OperationalState.DOWN
            assert kb_article.payload.approved is True

            assert len(snapshot.proposals) == 1
            assert snapshot.proposals[0].status is ProposalStatus.PENDING_APPROVAL
            assert (
                snapshot.proposals[0].diagnosis
                is DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE
            )
            assert tuple(snapshot.proposals[0].evidence_ids) == LOCAL_EVIDENCE_IDS

            product_blob = repr(snapshot) + repr(
                [(event.event_type.value, event.payload) for event in timeline]
            )
            assert PRIVATE_THOUGHT_MARKER not in product_blob

            approved = await stack["approval"].decide(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                proposal_id=stack["proposal_id"],
                decision=ApprovalDecision.APPROVED,
                decided_by="phase8d-approve",
            )
            assert approved.ok is True
            assert approved.replayed is False
            assert approved.proposal.status is ProposalStatus.EXECUTED
            assert approved.executed_action is not None
            assert approved.work_order is not None

            resumed = await stack["runtime"].resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=stack["proposal_id"],
                decision_payload=_decision_payload(approved),
            )
            assert resumed.invocation_id == paused.invocation_id
            assert resumed.function_call_id == paused.paused_function_call_id
            assert resumed.already_resumed is False

            replay = await stack["approval"].decide(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                proposal_id=stack["proposal_id"],
                decision=ApprovalDecision.APPROVED,
                decided_by="phase8d-approve",
            )
            assert replay.ok is True
            assert replay.replayed is True
            assert replay.approval.approval_id == approved.approval.approval_id
            assert replay.executed_action == approved.executed_action
            assert replay.work_order == approved.work_order

            replay_resume = await stack["runtime"].resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=stack["proposal_id"],
                decision_payload=_decision_payload(replay),
            )
            assert replay_resume.already_resumed is True
            assert replay_resume.invocation_id == paused.invocation_id

            final_state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert final_state is not None
            assert len(final_state.approvals) == 1
            assert len(final_state.executed_actions) == 1
            assert len(final_state.work_orders) == 1
        finally:
            await _close_stack(stack)

    asyncio.run(scenario())


def test_phase8d_reject_resumes_without_execution(monkeypatch):
    async def scenario() -> None:
        namespace = f"8D-R-{uuid4().hex[:8]}"
        tenant_id = f"TENANT-{namespace}"
        model = _ScriptedTraceModel(
            steps=_scenario3_steps(
                f"PROPOSAL-{namespace}",
                final_answer="Field visit rejected; no Product execution.",
            )
        )
        stack = await _build_stack(
            monkeypatch,
            namespace=namespace,
            model=model,
        )
        try:
            run_id, _, _, paused = await _start_and_pause(stack, tenant_id)
            rejected = await stack["approval"].decide(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                proposal_id=stack["proposal_id"],
                decision=ApprovalDecision.REJECTED,
                decided_by="phase8d-reject",
            )
            assert rejected.ok is True
            assert rejected.proposal.status is ProposalStatus.REJECTED
            assert rejected.executed_action is None
            assert rejected.work_order is None

            resumed = await stack["runtime"].resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=stack["proposal_id"],
                decision_payload=_decision_payload(rejected),
            )
            assert resumed.invocation_id == paused.invocation_id
            assert resumed.already_resumed is False

            final_state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert final_state is not None
            assert len(final_state.approvals) == 1
            assert len(final_state.executed_actions) == 0
            assert len(final_state.work_orders) == 0
        finally:
            await _close_stack(stack)

    asyncio.run(scenario())


def test_phase8d_stale_approve_revalidates_shared_access_link_truth(
    monkeypatch,
):
    async def scenario() -> None:
        namespace = f"8D-S-{uuid4().hex[:8]}"
        tenant_id = f"TENANT-{namespace}"
        model = _ScriptedTraceModel(
            steps=_scenario3_steps(
                f"PROPOSAL-{namespace}",
                final_answer="Approval committed, but Product marked proposal stale.",
            )
        )
        stack = await _build_stack(
            monkeypatch,
            namespace=namespace,
            model=model,
        )
        try:
            run_id, _, _, paused = await _start_and_pause(stack, tenant_id)

            stack["scenario3_fixture"].set_access_link_operational_state(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_state=OperationalState.UP,
            )

            stale = await stack["approval"].decide(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                proposal_id=stack["proposal_id"],
                decision=ApprovalDecision.APPROVED,
                decided_by="phase8d-stale",
            )
            assert stale.ok is True
            assert stale.proposal.status is ProposalStatus.STALE
            assert stale.executed_action is None
            assert stale.work_order is None

            resumed = await stack["runtime"].resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=stack["proposal_id"],
                decision_payload=_decision_payload(stale),
            )
            assert resumed.invocation_id == paused.invocation_id
            assert resumed.already_resumed is False

            final_state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert final_state is not None
            assert len(final_state.approvals) == 1
            assert len(final_state.executed_actions) == 0
            assert len(final_state.work_orders) == 0
        finally:
            await _close_stack(stack)

    asyncio.run(scenario())


def test_phase8d_restart_and_redelivery_preserve_native_invocation(
    monkeypatch,
):
    async def scenario() -> None:
        namespace = f"8D-X-{uuid4().hex[:8]}"
        tenant_id = f"TENANT-{namespace}"
        first_model = _ScriptedTraceModel(
            steps=_scenario3_steps(f"PROPOSAL-{namespace}")
        )
        stack = await _build_stack(
            monkeypatch,
            namespace=namespace,
            model=first_model,
        )
        runtime2 = None
        try:
            run_id, event_id, operational_signal, paused = await _start_and_pause(
                stack,
                tenant_id,
            )
            await stack["runtime"].close()

            resumed_model = _ScriptedTraceModel(
                steps=["Restarted runtime resumed the committed Product decision."]
            )
            monkeypatch.setattr(
                scenario3_service_module,
                "build_scenario3_agent",
                lambda actual_adapter: _build_scripted_agent(
                    actual_adapter,
                    resumed_model,
                ),
            )
            runtime2 = Scenario3AgentRuntime(
                adapter=stack["adapter"],
                session_service=stack["session_service"],
            )
            stack["runtime"] = runtime2

            redelivery = await runtime2.invoke_operational_event(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_event_id=event_id,
                operational_signal=operational_signal,
            )
            assert redelivery.invocation_id == paused.invocation_id
            assert redelivery.awaiting_human_decision is True
            assert redelivery.pending_proposal_id == stack["proposal_id"]
            assert resumed_model.requests == []

            rejected = await stack["approval"].decide(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                proposal_id=stack["proposal_id"],
                decision=ApprovalDecision.REJECTED,
                decided_by="phase8d-restart",
            )
            resumed = await runtime2.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=stack["proposal_id"],
                decision_payload=_decision_payload(rejected),
            )
            assert resumed.invocation_id == paused.invocation_id
            assert resumed.function_call_id == paused.paused_function_call_id
            assert resumed.already_resumed is False
            assert len(resumed_model.requests) == 1

            replayed_event = await runtime2.invoke_operational_event(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_event_id=event_id,
                operational_signal=operational_signal,
            )
            assert replayed_event.invocation_id == paused.invocation_id
            assert replayed_event.awaiting_human_decision is False

            final_state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert final_state is not None
            assert len(final_state.proposals) == 1
            assert len(final_state.approvals) == 1
            assert len(final_state.executed_actions) == 0
            assert len(final_state.work_orders) == 0
        finally:
            if runtime2 is None:
                await _close_stack(stack)
            else:
                await runtime2.close()
                await stack["engine"].dispose()

    asyncio.run(scenario())
