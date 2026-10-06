from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import json
import os
from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import InMemorySessionService
from google.adk.tools import FunctionTool, LongRunningFunctionTool
from google.genai import types
from pydantic import Field, PrivateAttr
from sqlalchemy import delete

import agent_runtime.scenario2_service as scenario2_service_module
from agent_runtime.human_decision import (
    WAIT_FOR_HUMAN_DECISION_TOOL,
    build_human_decision_wait_tool,
)
from agent_runtime.scenario2_agent import (
    SCENARIO2_AGENT_INSTRUCTION,
    build_scenario2_agent,
)
from agent_runtime.scenario2_service import (
    Scenario2AgentRuntime,
    _find_scenario2_event_correlation,
)
from product_api.app import create_app
from product_api.scenario2_fixture import (
    ACMEPAY_DEPENDENCY_ID,
    CORRELATION_KEY,
    SERVICE_KEY,
    SITE_KZN,
    SITE_SAM,
)
from product_api.scenario2_simulator import Scenario2SimulatorService
from product_api.scenario2_sources import PersistedScenario2FixtureSources
from product_backend.adapters.scenario2_tool_adapters import (
    DefaultScenario2ToolAdapter,
)
from product_backend.application.major_incident import (
    MajorIncidentApprovalService,
    MajorIncidentProposalService,
)
from product_backend.application.scenario2_ingestion import (
    Scenario2FixtureTransitionService,
    Scenario2RunStartService,
    Scenario2SignalIngestionService,
)
from product_backend.application.scenario2_read_tools import (
    Scenario2EvidenceTtlPolicy,
    Scenario2ReadToolService,
)
from product_backend.application.scenario2_state import Scenario2StateService
from product_backend.contracts.scenario2_tools import (
    GetExternalDependencyStatusRequest,
    GetLocalServiceHealthRequest,
    GetServiceDependenciesRequest,
    ProposeMajorIncidentRequest,
    SCENARIO2_MODEL_VISIBLE_TOOL_NAMES,
    SearchMajorIncidentsRequest,
)
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import (
    ApprovalDecision,
    EvidenceSourceType,
    HealthState,
    ProposalStatus,
    RunStatus,
)
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from product_backend.persistence.scenario2_state import (
    SqlAlchemyScenario2StateQuery,
)
from product_backend.persistence.tables import ApplicationOutboxRow
from product_backend.persistence.uow import (
    SqlAlchemyScenario2ApprovalUnitOfWork,
    SqlAlchemyScenario2FixtureStateUnitOfWork,
    SqlAlchemyScenario2ProposalUnitOfWork,
    SqlAlchemyScenario2RunStartUnitOfWork,
    SqlAlchemyScenario2SignalIngestionUnitOfWork,
    SqlAlchemyScenario2ToolReadUnitOfWork,
)


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for Phase 7D persistence tests")
    return normalize_database_url(value)


class _UnusedAdapter:
    async def get_local_service_health(self, context, request):
        raise AssertionError("not invoked")

    async def get_service_dependencies(self, context, request):
        raise AssertionError("not invoked")

    async def get_external_dependency_status(self, context, request):
        raise AssertionError("not invoked")

    async def search_major_incidents(self, context, request):
        raise AssertionError("not invoked")

    async def propose_major_incident(self, context, request):
        raise AssertionError("not invoked")


def _parameter_schema(tool: FunctionTool) -> dict[str, Any]:
    declaration = tool._get_declaration()
    assert declaration is not None
    schema = declaration.parameters_json_schema
    if schema is None:
        assert declaration.parameters is not None
        schema = declaration.parameters.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    return schema


class _FakeEvent:
    def __init__(
        self,
        *,
        invocation_id: str,
        author: str = "model",
        text: str | None = None,
        calls: tuple[Any, ...] = (),
        responses: tuple[Any, ...] = (),
        long_running_ids: tuple[str, ...] = (),
        final: bool = False,
    ) -> None:
        self.invocation_id = invocation_id
        self.author = author
        self.content = (
            SimpleNamespace(
                parts=[SimpleNamespace(text=text, thought=False)]
            )
            if text is not None
            else None
        )
        self._calls = calls
        self._responses = responses
        self.long_running_tool_ids = list(long_running_ids)
        self._final = final
        self.actions = SimpleNamespace(end_of_agent=False)

    def get_function_calls(self):
        return list(self._calls)

    def get_function_responses(self):
        return list(self._responses)

    def is_final_response(self) -> bool:
        return self._final


def _event_envelope(event_id: str) -> str:
    return json.dumps(
        {
            "type": "scenario2_operational_signal",
            "product_event_id": event_id,
            "payload": {},
        }
    )


def _proposal_response(proposal_id: str):
    return SimpleNamespace(
        name="propose_major_incident",
        id="CALL-PROPOSE",
        response={
            "ok": True,
            "proposal": {
                "proposal_id": proposal_id,
                "status": "PENDING_APPROVAL",
            },
        },
    )


def _wait_call(proposal_id: str, call_id: str = "CALL-WAIT"):
    return SimpleNamespace(
        name=WAIT_FOR_HUMAN_DECISION_TOOL,
        id=call_id,
        args={"proposal_id": proposal_id},
    )


def _decision_response(call_id: str = "CALL-WAIT"):
    return SimpleNamespace(
        name=WAIT_FOR_HUMAN_DECISION_TOOL,
        id=call_id,
        response={
            "status": "human_decision_committed",
            "decision": "APPROVED",
        },
    )


def test_phase7d_agent_exposes_exact_product_tools_plus_native_wait():
    async def scenario() -> None:
        agent = build_scenario2_agent(_UnusedAdapter())
        tools = await agent.canonical_tools()

        assert [tool.name for tool in tools[:-1]] == list(
            SCENARIO2_MODEL_VISIBLE_TOOL_NAMES
        )
        assert all(
            isinstance(tool, FunctionTool)
            and not isinstance(tool, LongRunningFunctionTool)
            for tool in tools[:-1]
        )
        assert tools[-1].name == WAIT_FOR_HUMAN_DECISION_TOOL
        assert isinstance(tools[-1], LongRunningFunctionTool)

        expected = {
            "get_local_service_health": {"site_id", "service_key"},
            "get_service_dependencies": {"service_key"},
            "get_external_dependency_status": {"dependency_id"},
            "search_major_incidents": {
                "service_key",
                "correlation_key",
                "dependency_id",
            },
            "propose_major_incident": {
                "correlation_key",
                "service_key",
                "affected_site_ids",
                "dependency_id",
                "evidence_ids",
                "summary",
                "rationale",
            },
        }
        by_name = {tool.name: tool for tool in tools}
        for name, expected_parameters in expected.items():
            properties = _parameter_schema(by_name[name]).get("properties", {})
            assert set(properties) == expected_parameters
            assert "tool_context" not in properties
            assert "tenant_id" not in properties
            assert "run_id" not in properties

        wait_properties = _parameter_schema(
            by_name[WAIT_FOR_HUMAN_DECISION_TOOL]
        ).get("properties", {})
        assert set(wait_properties) == {"proposal_id"}

        assert "OPERATIONAL_SIGNAL" in SCENARIO2_AGENT_INSTRUCTION
        assert "LOCAL_SERVICE_HEALTH" in SCENARIO2_AGENT_INSTRUCTION
        assert "SERVICE_DEPENDENCY_MAPPING" in SCENARIO2_AGENT_INSTRUCTION
        assert "EXTERNAL_DEPENDENCY_STATUS" in SCENARIO2_AGENT_INSTRUCTION
        assert "MAJOR_INCIDENT_SEARCH" in SCENARIO2_AGENT_INSTRUCTION
        assert "await_human_decision" in SCENARIO2_AGENT_INSTRUCTION

    asyncio.run(scenario())


def test_phase7d_runtime_refuses_proposal_without_matching_native_wait():
    event_id = "EVENT-7D-GUARD"
    invocation_id = "INV-7D-GUARD"
    proposal_id = "MI-PROP-7D-GUARD"
    events = [
        _FakeEvent(
            invocation_id=invocation_id,
            author="user",
            text=_event_envelope(event_id),
        ),
        _FakeEvent(
            invocation_id=invocation_id,
            responses=(_proposal_response(proposal_id),),
        ),
        _FakeEvent(
            invocation_id=invocation_id,
            text="Proposal created.",
            final=True,
        ),
    ]

    correlation = _find_scenario2_event_correlation(
        events,
        product_event_id=event_id,
    )
    assert correlation is not None
    assert correlation.pending_proposal_id == proposal_id
    assert correlation.proposal_created_without_wait is True
    assert correlation.settled is False

    with pytest.raises(
        RuntimeError,
        match="no successful Product proposal",
    ):
        _find_scenario2_event_correlation(
            [
                events[0],
                _FakeEvent(
                    invocation_id=invocation_id,
                    calls=(_wait_call("MI-PROP-FABRICATED"),),
                    long_running_ids=("CALL-WAIT",),
                ),
            ],
            product_event_id=event_id,
        )

    with pytest.raises(
        RuntimeError,
        match="does not match Product proposal",
    ):
        _find_scenario2_event_correlation(
            [
                events[0],
                events[1],
                _FakeEvent(
                    invocation_id=invocation_id,
                    calls=(_wait_call("MI-PROP-OTHER"),),
                    long_running_ids=("CALL-WAIT",),
                ),
            ],
            product_event_id=event_id,
        )


def test_phase7d_runtime_native_wait_stops_awaiting_after_function_response():
    event_id = "EVENT-7D-HITL"
    invocation_id = "INV-7D-HITL"
    proposal_id = "MI-PROP-7D-HITL"
    paused_events = [
        _FakeEvent(
            invocation_id=invocation_id,
            author="user",
            text=_event_envelope(event_id),
        ),
        _FakeEvent(
            invocation_id=invocation_id,
            responses=(_proposal_response(proposal_id),),
        ),
        _FakeEvent(
            invocation_id=invocation_id,
            calls=(_wait_call(proposal_id),),
            long_running_ids=("CALL-WAIT",),
        ),
    ]

    paused = _find_scenario2_event_correlation(
        paused_events,
        product_event_id=event_id,
    )
    assert paused is not None
    assert paused.settled is True
    assert paused.pending_proposal_id == proposal_id
    assert paused.paused_function_call_id == "CALL-WAIT"
    assert paused.proposal_created_without_wait is False

    resumed = _find_scenario2_event_correlation(
        [
            *paused_events,
            _FakeEvent(
                invocation_id=invocation_id,
                author="user",
                responses=(_decision_response(),),
            ),
            _FakeEvent(
                invocation_id=invocation_id,
                text="Major Incident created after human approval.",
                final=True,
            ),
        ],
        product_event_id=event_id,
    )
    assert resumed is not None
    assert resumed.settled is True
    assert resumed.pending_proposal_id == proposal_id
    assert resumed.paused_function_call_id is None
    assert resumed.final_answer == "Major Incident created after human approval."



class _Scenario2ScriptedModel(BaseLlm):
    model: str = "phase7d-scripted"
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
            raise AssertionError("Scenario 2 scripted model ran out of responses")
        step = self.steps[self._index]
        self._index += 1
        if isinstance(step, BaseException):
            raise step
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


def _scripted_proposal_call() -> types.Part:
    return types.Part.from_function_call(
        name="propose_major_incident",
        args={},
    )


def _scripted_wait_call(proposal_id: str) -> types.Part:
    return types.Part.from_function_call(
        name=WAIT_FOR_HUMAN_DECISION_TOOL,
        args={"proposal_id": proposal_id},
    )


def _build_scripted_scenario2_agent(
    model: BaseLlm,
    proposal_id: str,
    proposal_calls: list[str],
) -> LlmAgent:
    async def propose_major_incident() -> dict[str, Any]:
        proposal_calls.append(proposal_id)
        return {
            "ok": True,
            "proposal": {
                "proposal_id": proposal_id,
                "status": "PENDING_APPROVAL",
            },
        }

    return LlmAgent(
        name="phase7d_scripted_agent",
        model=model,
        instruction=(
            "Create the Product Major Incident proposal, call the native wait "
            "tool, then after resume report the committed human decision."
        ),
        tools=[
            FunctionTool(propose_major_incident),
            build_human_decision_wait_tool(),
        ],
    )


def test_phase7d_native_adk_pause_resume_and_redelivery_use_same_invocation(
    monkeypatch,
):
    async def scenario() -> None:
        proposal_id = "MI-PROP-7D-NATIVE"
        proposal_calls: list[str] = []
        model = _Scenario2ScriptedModel(
            steps=[
                _scripted_proposal_call(),
                _scripted_wait_call(proposal_id),
                "Major Incident was created after the committed human approval.",
            ]
        )
        monkeypatch.setattr(
            scenario2_service_module,
            "build_scenario2_agent",
            lambda adapter: _build_scripted_scenario2_agent(
                model,
                proposal_id,
                proposal_calls,
            ),
        )
        sessions = InMemorySessionService()
        runtime = Scenario2AgentRuntime(
            adapter=object(),
            session_service=sessions,
        )
        try:
            tenant_id = "TENANT-7D-NATIVE"
            run_id = "RUN-7D-NATIVE"
            event_id = "EVENT-7D-NATIVE"

            paused = await runtime.invoke_operational_signal(
                tenant_id=tenant_id,
                run_id=run_id,
                product_event_id=event_id,
                operational_fact={"signal": {"signal_id": "SIG-7D-NATIVE"}},
            )
            assert proposal_calls == [proposal_id]
            assert paused.recoverable is True
            assert paused.awaiting_human_decision is True
            assert paused.pending_proposal_id == proposal_id
            assert paused.paused_function_call_id is not None
            assert paused.invocation_id is not None

            resumed = await runtime.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=proposal_id,
                decision_payload={
                    "status": "human_decision_committed",
                    "decision": "APPROVED",
                    "proposal_id": proposal_id,
                    "proposal_status": "EXECUTED",
                    "execution": {
                        "execution_id": "MI-EXEC-7D-NATIVE",
                        "action_type": "CREATE_MAJOR_INCIDENT",
                        "major_incident_id": "MI-7D-NATIVE",
                    },
                    "major_incident": {
                        "major_incident_id": "MI-7D-NATIVE",
                        "status": "OPEN",
                    },
                    "replayed": False,
                },
            )
            assert resumed.invocation_id == paused.invocation_id
            assert resumed.function_call_id == paused.paused_function_call_id
            assert resumed.already_resumed is False
            assert "created" in (resumed.final_answer or "").lower()

            replay_resume = await runtime.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=proposal_id,
                decision_payload={
                    "status": "human_decision_committed",
                    "decision": "APPROVED",
                    "proposal_id": proposal_id,
                    "proposal_status": "EXECUTED",
                    "replayed": True,
                },
            )
            assert replay_resume.already_resumed is True
            assert replay_resume.invocation_id == paused.invocation_id

            redelivery = await runtime.invoke_operational_signal(
                tenant_id=tenant_id,
                run_id=run_id,
                product_event_id=event_id,
                operational_fact={"signal": {"signal_id": "SIG-7D-NATIVE"}},
            )
            assert redelivery.invocation_id == paused.invocation_id
            assert redelivery.recoverable is True
            assert redelivery.awaiting_human_decision is False
            assert proposal_calls == [proposal_id]
        finally:
            await runtime.close()

    asyncio.run(scenario())


def _build_stack(factory):
    state_service = Scenario2StateService(
        SqlAlchemyScenario2StateQuery(factory)
    )
    start_service = Scenario2RunStartService(
        lambda: SqlAlchemyScenario2RunStartUnitOfWork(factory)
    )
    ingestion_service = Scenario2SignalIngestionService(
        lambda: SqlAlchemyScenario2SignalIngestionUnitOfWork(factory)
    )
    simulator = Scenario2SimulatorService(
        state_service=state_service,
        ingestion_service=ingestion_service,
    )
    sources = PersistedScenario2FixtureSources(
        state_service,
        factory,
    )
    read_service = Scenario2ReadToolService(
        read_uow_factory=lambda: SqlAlchemyScenario2ToolReadUnitOfWork(
            factory
        ),
        local_health=sources,
        dependency_mapping=sources,
        dependency_status=sources,
        major_incident_directory=sources,
        ttl_policy=Scenario2EvidenceTtlPolicy(
            local_service_health=timedelta(minutes=5),
            external_dependency_status=timedelta(minutes=2),
            major_incident_search=timedelta(minutes=2),
        ),
    )
    proposal_service = MajorIncidentProposalService(
        lambda: SqlAlchemyScenario2ProposalUnitOfWork(factory)
    )
    adapter = DefaultScenario2ToolAdapter(
        read_service=read_service,
        proposal_service=proposal_service,
    )
    approval_service = MajorIncidentApprovalService(
        lambda: SqlAlchemyScenario2ApprovalUnitOfWork(factory),
        local_health=sources,
        dependency_mapping=sources,
        dependency_status=sources,
        major_incident_directory=sources,
    )
    fixture_service = Scenario2FixtureTransitionService(
        lambda: SqlAlchemyScenario2FixtureStateUnitOfWork(factory)
    )
    return {
        "state": state_service,
        "start": start_service,
        "simulator": simulator,
        "sources": sources,
        "adapter": adapter,
        "approval": approval_service,
        "fixture": fixture_service,
    }


async def _prepare_pending_major_incident(stack, tenant_id: str):
    started = await stack["start"].start(tenant_id=tenant_id)
    run_id = started.run.run_id
    context = ToolCallContext(tenant_id=tenant_id, run_id=run_id)

    for expected_index in (1, 2, 3):
        step = await stack["simulator"].next(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        assert step.next_index == expected_index

    state = await stack["state"].get(
        tenant_id=tenant_id,
        run_id=run_id,
    )
    assert state is not None
    assert len(state.operational_signals) == 3

    before_mapping = await stack["adapter"].get_external_dependency_status(
        context,
        GetExternalDependencyStatusRequest(
            dependency_id=ACMEPAY_DEPENDENCY_ID
        ),
    )
    assert before_mapping.ok is False
    assert dict(before_mapping.error.details)["reason"] == "unknown_run_dependency"

    local_kzn = await stack["adapter"].get_local_service_health(
        context,
        GetLocalServiceHealthRequest(
            site_id=SITE_KZN,
            service_key=SERVICE_KEY,
        ),
    )
    local_sam = await stack["adapter"].get_local_service_health(
        context,
        GetLocalServiceHealthRequest(
            site_id=SITE_SAM,
            service_key=SERVICE_KEY,
        ),
    )
    mappings = await stack["adapter"].get_service_dependencies(
        context,
        GetServiceDependenciesRequest(service_key=SERVICE_KEY),
    )
    assert local_kzn.ok is True
    assert local_sam.ok is True
    assert mappings.ok is True
    assert len(mappings.evidence) == 1

    dependency_status = await stack["adapter"].get_external_dependency_status(
        context,
        GetExternalDependencyStatusRequest(
            dependency_id=ACMEPAY_DEPENDENCY_ID
        ),
    )
    duplicate_search = await stack["adapter"].search_major_incidents(
        context,
        SearchMajorIncidentsRequest(
            service_key=SERVICE_KEY,
            correlation_key=CORRELATION_KEY,
            dependency_id=ACMEPAY_DEPENDENCY_ID,
        ),
    )
    assert dependency_status.ok is True
    assert dependency_status.status.status is HealthState.DEGRADED
    assert duplicate_search.ok is True
    assert duplicate_search.snapshot.open_major_incident_ids == ()

    state = await stack["state"].get(
        tenant_id=tenant_id,
        run_id=run_id,
    )
    assert state is not None
    signal_evidence_ids = tuple(
        item.evidence_id
        for item in state.evidence
        if item.source_type is EvidenceSourceType.OPERATIONAL_SIGNAL
    )
    assert len(signal_evidence_ids) == 3

    evidence_ids = (
        *signal_evidence_ids,
        local_kzn.evidence.evidence_id,
        local_sam.evidence.evidence_id,
        mappings.evidence[0].evidence_id,
        dependency_status.evidence.evidence_id,
        duplicate_search.evidence.evidence_id,
    )
    proposal_result = await stack["adapter"].propose_major_incident(
        context,
        ProposeMajorIncidentRequest(
            correlation_key=CORRELATION_KEY,
            service_key=SERVICE_KEY,
            affected_site_ids=(SITE_KZN, SITE_SAM),
            dependency_id=ACMEPAY_DEPENDENCY_ID,
            evidence_ids=evidence_ids,
            summary="Payment gateway timeouts across independent stores",
            rationale=(
                "Persisted cross-site signals plus healthy local services "
                "and degraded common provider support Major Incident review."
            ),
        ),
    )
    assert proposal_result.ok is True
    assert proposal_result.proposal.status is ProposalStatus.PENDING_APPROVAL

    state = await stack["state"].get(
        tenant_id=tenant_id,
        run_id=run_id,
    )
    assert state is not None
    assert state.run.status is RunStatus.WAITING_APPROVAL
    assert [item.proposal_id for item in state.major_incident_proposals] == [
        proposal_result.proposal.proposal_id
    ]
    assert len(state.major_incidents) == 0
    assert len(state.major_incident_executions) == 0
    return run_id, proposal_result.proposal.proposal_id


async def _clear_scenario2_outbox(factory, tenant_id: str) -> None:
    async with factory() as session:
        await session.execute(
            delete(ApplicationOutboxRow).where(
                ApplicationOutboxRow.tenant_id == tenant_id
            )
        )
        await session.commit()


def test_phase7d_postgres_tools_proposal_approve_replay_and_cross_run_search():
    async def scenario() -> None:
        tenant_id = f"TENANT-7D-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        stack = _build_stack(factory)
        try:
            run_id, proposal_id = await _prepare_pending_major_incident(
                stack,
                tenant_id,
            )
            context = ToolCallContext(tenant_id=tenant_id, run_id=run_id)

            approved = await stack["approval"].decide(
                context,
                proposal_id=proposal_id,
                decision=ApprovalDecision.APPROVED,
                decided_by="phase7d-test",
            )
            assert approved.ok is True
            assert approved.replayed is False
            assert approved.proposal.status is ProposalStatus.EXECUTED
            assert approved.execution is not None
            assert approved.major_incident is not None

            replay = await stack["approval"].decide(
                context,
                proposal_id=proposal_id,
                decision=ApprovalDecision.APPROVED,
                decided_by="phase7d-test",
            )
            assert replay.ok is True
            assert replay.replayed is True
            assert replay.approval.approval_id == approved.approval.approval_id
            assert replay.execution == approved.execution
            assert replay.major_incident == approved.major_incident

            state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert state is not None
            assert state.run.status is RunStatus.ACTIVE
            assert len(state.major_incident_proposals) == 1
            assert len(state.major_incident_approvals) == 1
            assert len(state.major_incident_executions) == 1
            assert len(state.major_incidents) == 1

            second = await stack["start"].start(tenant_id=tenant_id)
            cross_run_search = await stack["sources"].search_major_incidents(
                tenant_id=tenant_id,
                run_id=second.run.run_id,
                service_key=SERVICE_KEY,
                correlation_key=CORRELATION_KEY,
                dependency_id=ACMEPAY_DEPENDENCY_ID,
            )
            assert cross_run_search.open_major_incident_ids == (
                approved.major_incident.major_incident_id,
            )
        finally:
            await _clear_scenario2_outbox(factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_phase7d_approve_goes_stale_when_provider_recovers_in_persisted_world():
    async def scenario() -> None:
        tenant_id = f"TENANT-7D-STALE-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        stack = _build_stack(factory)
        try:
            run_id, proposal_id = await _prepare_pending_major_incident(
                stack,
                tenant_id,
            )
            changed = await stack["fixture"].set_dependency_status(
                tenant_id=tenant_id,
                run_id=run_id,
                status=HealthState.HEALTHY,
            )
            assert changed.dependency_status is HealthState.HEALTHY

            result = await stack["approval"].decide(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                proposal_id=proposal_id,
                decision=ApprovalDecision.APPROVED,
                decided_by="phase7d-stale-test",
            )
            assert result.ok is True
            assert result.proposal.status is ProposalStatus.STALE
            assert result.execution is None
            assert result.major_incident is None

            state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert state is not None
            assert state.run.status is RunStatus.ACTIVE
            assert len(state.major_incident_approvals) == 1
            assert len(state.major_incident_executions) == 0
            assert len(state.major_incidents) == 0
        finally:
            await _clear_scenario2_outbox(factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_phase7d_postgres_reject_records_decision_without_execution():
    async def scenario() -> None:
        tenant_id = f"TENANT-7D-REJECT-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        stack = _build_stack(factory)
        try:
            run_id, proposal_id = await _prepare_pending_major_incident(
                stack,
                tenant_id,
            )
            result = await stack["approval"].decide(
                ToolCallContext(tenant_id=tenant_id, run_id=run_id),
                proposal_id=proposal_id,
                decision=ApprovalDecision.REJECTED,
                decided_by="phase7d-reject-test",
            )
            assert result.ok is True
            assert result.proposal.status is ProposalStatus.REJECTED
            assert result.execution is None
            assert result.major_incident is None

            state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert state is not None
            assert state.run.status is RunStatus.ACTIVE
            assert len(state.major_incident_approvals) == 1
            assert (
                state.major_incident_approvals[0].decision
                is ApprovalDecision.REJECTED
            )
            assert len(state.major_incident_executions) == 0
            assert len(state.major_incidents) == 0
        finally:
            await _clear_scenario2_outbox(factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_phase7d_pending_equivalent_is_blocked_tenant_wide_across_runs():
    async def scenario() -> None:
        tenant_id = f"TENANT-7D-DUP-{uuid4().hex[:10]}"
        engine = create_engine(DatabaseSettings(url=_database_url()))
        factory = create_session_factory(engine)
        stack = _build_stack(factory)
        try:
            _, first_proposal_id = await _prepare_pending_major_incident(
                stack,
                tenant_id,
            )
            second = await stack["start"].start(tenant_id=tenant_id)
            duplicate = await stack["adapter"].propose_major_incident(
                ToolCallContext(
                    tenant_id=tenant_id,
                    run_id=second.run.run_id,
                ),
                ProposeMajorIncidentRequest(
                    correlation_key=CORRELATION_KEY,
                    service_key=SERVICE_KEY,
                    affected_site_ids=(SITE_KZN, SITE_SAM),
                    dependency_id=ACMEPAY_DEPENDENCY_ID,
                    evidence_ids=("EV-DUMMY-NOT-REACHED",),
                    summary="Equivalent pending proposal",
                    rationale="Must be rejected before evidence resolution.",
                ),
            )
            assert duplicate.ok is False
            assert (
                dict(duplicate.error.details)["reason"]
                == "duplicate_pending_major_incident_proposal"
            )

            first_state = await stack["state"].get(
                tenant_id=tenant_id,
                run_id=(
                    await stack["state"]._query.get(  # type: ignore[attr-defined]
                        tenant_id=tenant_id,
                        run_id=second.run.run_id,
                    )
                ).run.run_id
                if False
                else second.run.run_id,
            )
            assert first_proposal_id
            assert first_state is not None
            assert first_state.major_incident_proposals == ()
        finally:
            await _clear_scenario2_outbox(factory, tenant_id)
            await engine.dispose()

    asyncio.run(scenario())


def test_phase7d_api_wiring_is_visible_without_changing_phase7c_health_contract(
    monkeypatch,
):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with TestClient(create_app()) as client:
        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["scenario2_checkpoint"] == "7C-adk-dispatch"
        assert body["scenario2_phase7d_tools_hitl_wired"] is True
        assert body["scenario2_tools_wired"] is True
        assert body["scenario2_hitl_wired"] is True

        paths = client.get("/openapi.json").json()["paths"]
        assert (
            "/api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/approve"
            in paths
        )
        assert (
            "/api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/reject"
            in paths
        )
