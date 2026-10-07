from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

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

import agent_runtime.scenario3_service as scenario3_service_module
from agent_runtime.human_decision import (
    WAIT_FOR_HUMAN_DECISION_TOOL,
    build_human_decision_wait_tool,
)
from agent_runtime.scenario3_agent import (
    SCENARIO3_AGENT_INSTRUCTION,
    build_scenario3_agent,
)
from agent_runtime.scenario3_service import Scenario3AgentRuntime
from agent_runtime.service import AgentResumeResult
from agent_runtime.sessions import get_run_session
from product_api.app import ProductApiContainer, create_app
from product_api.dispatch import Scenario1DispatchWorker
from product_backend.application.results import ApprovalProcessed
from product_backend.contracts.events import (
    AGENT_DISPATCH_TOPIC,
    ApplicationOutboxRecord,
)
from product_backend.contracts.run_state import RunStateSnapshot
from product_backend.domain.enums import (
    ActionType,
    ApprovalDecision,
    DiagnosisCode,
    DiagnosticType,
    IncidentStatus,
    OperationalState,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.models import ActionProposal, Approval, Incident, Run


EXPECTED_SCENARIO3_TOOLS = [
    "get_service_dependencies",
    "get_external_dependency_status",
    "get_device",
    "get_site_health",
    "run_diagnostic",
    "search_kb",
    "propose_field_visit",
    WAIT_FOR_HUMAN_DECISION_TOOL,
]


class _ScriptedModel(BaseLlm):
    model: str = "phase8c2-scripted"
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
            raise AssertionError("Scripted model ran out of responses")
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


def _proposal_call() -> types.Part:
    return types.Part.from_function_call(
        name="propose_field_visit",
        args={},
    )


def _wait_call(proposal_id: str) -> types.Part:
    return types.Part.from_function_call(
        name=WAIT_FOR_HUMAN_DECISION_TOOL,
        args={"proposal_id": proposal_id},
    )


def _build_scripted_agent(
    model: BaseLlm,
    *,
    proposal_id: str,
    proposal_calls: list[str],
) -> LlmAgent:
    async def propose_field_visit() -> dict[str, Any]:
        proposal_calls.append(proposal_id)
        return {
            "ok": True,
            "proposal": {
                "proposal_id": proposal_id,
                "status": "PENDING_APPROVAL",
            },
        }

    return LlmAgent(
        name="phase8c2_scripted_scenario3_agent",
        model=model,
        instruction=(
            "Create one field-visit proposal, immediately enter the native "
            "human-decision wait, then after resume report only Product truth."
        ),
        tools=[
            FunctionTool(propose_field_visit),
            build_human_decision_wait_tool(),
        ],
    )


def _tool_schema(tool: object) -> dict[str, Any]:
    declaration = tool._get_declaration()
    assert declaration is not None
    schema = declaration.parameters_json_schema
    if schema is not None:
        return schema
    assert declaration.parameters is not None
    return declaration.parameters.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


def test_phase8c2_scenario1_and_scenario3_share_authoritative_access_link_truth():
    async def scenario() -> None:
        tenant_id = "TENANT-S3-8C2-SHARED-TRUTH"
        run_id = "RUN-S3-8C2-SHARED-TRUTH"

        with TestClient(create_app()) as client:
            container = client.app.state.product_container
            assert container.scenario3_fixture is not None

            container.scenario3_fixture.set_access_link_operational_state(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_state=OperationalState.UP,
            )

            scenario1_view = await container.fixture.run_diagnostic(
                tenant_id=tenant_id,
                run_id=run_id,
                diagnostic_type=DiagnosticType.ACCESS_LINK,
                target_id="ATT-KZN17-POS02",
            )
            scenario3_view = await container.scenario3_fixture.run_diagnostic(
                tenant_id=tenant_id,
                run_id=run_id,
                diagnostic_type=DiagnosticType.ACCESS_LINK,
                target_id="ATT-KZN17-POS02",
            )

            assert scenario1_view is not None
            assert scenario3_view is not None
            assert scenario1_view.operational_state is OperationalState.UP
            assert scenario3_view.operational_state is OperationalState.UP

    asyncio.run(scenario())


def test_phase8c2_scenario3_tool_surface_is_exact_and_trusted_context_is_hidden():
    async def scenario() -> None:
        agent = build_scenario3_agent(object())
        tools = await agent.canonical_tools()

        assert [tool.name for tool in tools] == EXPECTED_SCENARIO3_TOOLS
        assert isinstance(tools[-1], LongRunningFunctionTool)
        assert "MUST call propose_field_visit" in SCENARIO3_AGENT_INSTRUCTION
        assert "Do not finish with a text-only response" in SCENARIO3_AGENT_INSTRUCTION
        assert all(
            isinstance(tool, FunctionTool)
            for tool in tools[:-1]
        )

        forbidden = {
            "search_incidents",
            "get_local_service_health",
            "search_major_incidents",
            "propose_major_incident",
        }
        assert forbidden.isdisjoint(tool.name for tool in tools)

        for tool in tools:
            properties = set(_tool_schema(tool).get("properties", {}))
            assert "tenant_id" not in properties
            assert "run_id" not in properties
            assert "tool_context" not in properties

    asyncio.run(scenario())


def test_phase8c2_scenario3_redelivery_and_hitl_keep_one_native_invocation(monkeypatch):
    async def scenario() -> None:
        proposal_id = "PROPOSAL-S3-8C2"
        proposal_calls: list[str] = []
        model = _ScriptedModel(
            steps=[
                _proposal_call(),
                _wait_call(proposal_id),
                "Human rejected the field visit; no execution occurred.",
            ]
        )
        monkeypatch.setattr(
            scenario3_service_module,
            "build_scenario3_agent",
            lambda adapter: _build_scripted_agent(
                model,
                proposal_id=proposal_id,
                proposal_calls=proposal_calls,
            ),
        )
        sessions = InMemorySessionService()
        runtime = Scenario3AgentRuntime(
            adapter=object(),
            session_service=sessions,
        )
        tenant_id = "TENANT-S3-8C2-NATIVE"
        run_id = "RUN-S3-8C2-NATIVE"
        event_id = "EVENT-S3-8C2-NATIVE"

        try:
            paused = await runtime.invoke_operational_event(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_event_id=event_id,
                operational_signal={
                    "scenario_id": "scenario-3",
                    "incidents": [],
                },
            )
            assert paused.session_id == run_id
            assert paused.invocation_id is not None
            assert paused.awaiting_human_decision is True
            assert paused.pending_proposal_id == proposal_id
            assert paused.paused_function_call_id is not None
            assert proposal_calls == [proposal_id]
            assert len(model.requests) == 2

            redelivery = await runtime.invoke_operational_event(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_event_id=event_id,
                operational_signal={"ignored_on_redelivery": True},
            )
            assert redelivery.invocation_id == paused.invocation_id
            assert redelivery.session_id == run_id
            assert redelivery.awaiting_human_decision is True
            assert proposal_calls == [proposal_id]
            assert len(model.requests) == 2

            resumed = await runtime.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=proposal_id,
                decision_payload={
                    "status": "human_decision_committed",
                    "decision": "REJECTED",
                    "proposal_id": proposal_id,
                    "proposal_status": "REJECTED",
                    "incident_id": "INC-S3-KZN-001",
                    "incident_status": "OPEN",
                    "executed_action": None,
                    "work_order": None,
                    "repair_confirmed": False,
                    "replayed": False,
                },
            )
            assert resumed.invocation_id == paused.invocation_id
            assert resumed.function_call_id == paused.paused_function_call_id
            assert resumed.already_resumed is False

            after_resume = await runtime.invoke_operational_event(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_event_id=event_id,
                operational_signal={"ignored_after_resume": True},
            )
            assert after_resume.invocation_id == paused.invocation_id
            assert after_resume.awaiting_human_decision is False
            assert proposal_calls == [proposal_id]

            session = await get_run_session(
                sessions,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            assert session.id == run_id
            user_envelopes = [
                part.text
                for event in session.events
                if event.author == "user"
                for part in (event.content.parts if event.content else [])
                if part.text
            ]
            assert any('"scenario": "scenario-3"' in item for item in user_envelopes)
        finally:
            await runtime.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("wait_proposal_id", "include_wait", "message"),
    [
        (
            "PROPOSAL-WRONG",
            True,
            "does not match Product proposal",
        ),
        (
            None,
            False,
            "no exact native wait correlation",
        ),
    ],
)
def test_phase8c2_field_visit_requires_exact_same_invocation_native_wait(
    monkeypatch,
    wait_proposal_id: str | None,
    include_wait: bool,
    message: str,
):
    async def scenario() -> None:
        proposal_id = "PROPOSAL-S3-EXACT"
        proposal_calls: list[str] = []
        steps: list[Any] = [_proposal_call()]
        if include_wait:
            assert wait_proposal_id is not None
            steps.append(_wait_call(wait_proposal_id))
        else:
            steps.append("Proposal created but native wait was omitted.")

        model = _ScriptedModel(steps=steps)
        monkeypatch.setattr(
            scenario3_service_module,
            "build_scenario3_agent",
            lambda adapter: _build_scripted_agent(
                model,
                proposal_id=proposal_id,
                proposal_calls=proposal_calls,
            ),
        )
        sessions = InMemorySessionService()
        runtime = Scenario3AgentRuntime(
            adapter=object(),
            session_service=sessions,
        )
        try:
            with pytest.raises(RuntimeError, match=message):
                await runtime.invoke_operational_event(
                    tenant_id="TENANT-S3-EXACT",
                    run_id="RUN-S3-EXACT",
                    operational_event_id="EVENT-S3-EXACT",
                    operational_signal={"scenario_id": "scenario-3"},
                )
            assert proposal_calls == [proposal_id]
        finally:
            await runtime.close()

    asyncio.run(scenario())


class _FakeOutbox:
    def __init__(self, record: ApplicationOutboxRecord) -> None:
        self.record = record
        self.claimed = False
        self.delivered = False
        self.rescheduled = False

    async def claim_next(
        self,
        *,
        topic: str,
        lease_seconds: float,
    ) -> ApplicationOutboxRecord | None:
        assert topic == AGENT_DISPATCH_TOPIC
        assert lease_seconds > 0
        if self.claimed:
            return None
        self.claimed = True
        return self.record

    async def mark_delivered(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
    ) -> ApplicationOutboxRecord:
        assert (tenant_id, run_id, outbox_id) == (
            self.record.tenant_id,
            self.record.run_id,
            self.record.outbox_id,
        )
        self.delivered = True
        return self.record

    async def reschedule(
        self,
        *,
        tenant_id: str,
        run_id: str,
        outbox_id: str,
        delay_seconds: float,
    ) -> ApplicationOutboxRecord:
        assert delay_seconds >= 0
        self.rescheduled = True
        return self.record


class _FakeDispatchUow:
    def __init__(self, outbox: _FakeOutbox) -> None:
        self.outbox = outbox

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _FakeStateService:
    def __init__(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id

    async def get(self, *, tenant_id: str, run_id: str):
        return SimpleNamespace(
            run=SimpleNamespace(scenario_id=self.scenario_id),
            incidents=(
                SimpleNamespace(
                    incident_id="INC-S3-KZN-001",
                    site_id="SITE-KZN-017",
                    reported_device_id="POS-KZN17-02",
                    symptom="Payment gateway timeout",
                    status=IncidentStatus.OPEN,
                ),
            ),
        )


class _RecordingDispatchRuntime:
    gemini_configured = True

    def __init__(self, *, reach_hitl: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.reach_hitl = reach_hitl

    async def invoke_operational_event(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            final_answer=(
                None
                if self.reach_hitl
                else "Evidence complete; finishing with text instead of proposal."
            ),
            awaiting_human_decision=self.reach_hitl,
            pending_proposal_id=(
                "PROPOSAL-S3-DISPATCH" if self.reach_hitl else None
            ),
            paused_function_call_id=(
                "CALL-S3-WAIT" if self.reach_hitl else None
            ),
        )


def test_phase8c2_shared_worker_routes_scenario3_only_to_scenario3_runtime():
    now = datetime.now(UTC)
    record = ApplicationOutboxRecord(
        outbox_id="OUTBOX-S3-8C2",
        tenant_id="TENANT-S3-8C2-DISPATCH",
        run_id="RUN-S3-8C2-DISPATCH",
        event_seq=2,
        topic=AGENT_DISPATCH_TOPIC,
        payload={
            "event_id": "EVENT-S3-8C2-DISPATCH",
            "event_seq": 2,
            "signal": {"signal_type": "itsm.incident.created", "details": {}},
        },
        created_at=now,
        available_at=now,
        delivered_at=None,
        attempt_count=1,
    )
    outbox = _FakeOutbox(record)
    scenario1_runtime = _RecordingDispatchRuntime()
    scenario3_runtime = _RecordingDispatchRuntime()
    worker = Scenario1DispatchWorker(
        uow_factory=lambda: _FakeDispatchUow(outbox),
        state_service=_FakeStateService("scenario-3"),
        agent_runtime=scenario1_runtime,
        scenario3_agent_runtime=scenario3_runtime,
    )

    processed = asyncio.run(worker.dispatch_once())

    assert processed is True
    assert scenario1_runtime.calls == []
    assert len(scenario3_runtime.calls) == 1
    call = scenario3_runtime.calls[0]
    assert call["tenant_id"] == record.tenant_id
    assert call["run_id"] == record.run_id
    assert call["operational_event_id"] == "EVENT-S3-8C2-DISPATCH"
    assert call["operational_signal"]["scenario_id"] == "scenario-3"
    assert outbox.delivered is True
    assert outbox.rescheduled is False


class _FakeApprovalService:
    def __init__(self, result: ApprovalProcessed) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def decide(
        self,
        context,
        *,
        proposal_id: str,
        decision: ApprovalDecision,
        decided_by: str,
    ) -> ApprovalProcessed:
        self.calls.append(
            {
                "context": context,
                "proposal_id": proposal_id,
                "decision": decision,
                "decided_by": decided_by,
            }
        )
        return self.result


class _FakeRunStateService:
    def __init__(self, snapshot: RunStateSnapshot) -> None:
        self.snapshot = snapshot

    async def get(self, *, tenant_id: str, run_id: str) -> RunStateSnapshot:
        assert tenant_id == self.snapshot.run.tenant_id
        assert run_id == self.snapshot.run.run_id
        return self.snapshot


class _FailingRunStateService:
    async def get(self, *, tenant_id: str, run_id: str):
        del tenant_id, run_id
        raise RuntimeError("simulated post-commit state reload failure")


class _RecordingResumeRuntime:
    gemini_configured = True
    resumability_wired = True
    model = "phase8c2-recording"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def resume_human_decision(self, **kwargs) -> AgentResumeResult:
        self.calls.append(kwargs)
        return AgentResumeResult(
            invocation_id="INV-S3-8C2-ROUTED",
            function_call_id="CALL-S3-8C2-ROUTED",
            final_answer="Scenario 3 decision resumed.",
            already_resumed=False,
        )


def _scenario3_rejected_result() -> tuple[RunStateSnapshot, ApprovalProcessed]:
    now = datetime.now(UTC)
    tenant_id = "TENANT-S3-8C2-DECISION"
    run_id = "RUN-S3-8C2-DECISION"
    proposal_id = "PROPOSAL-S3-8C2-DECISION"
    incident = Incident(
        incident_id="INC-S3-KZN-001",
        tenant_id=tenant_id,
        run_id=run_id,
        site_id="SITE-KZN-017",
        reported_device_id="POS-KZN17-02",
        symptom="Payment gateway timeout",
        status=IncidentStatus.OPEN,
        created_at=now,
        updated_at=now,
    )
    run = Run(
        run_id=run_id,
        tenant_id=tenant_id,
        scenario_id="scenario-3",
        status=RunStatus.ACTIVE,
        created_at=now,
        updated_at=now,
    )
    proposal = ActionProposal(
        proposal_id=proposal_id,
        tenant_id=tenant_id,
        run_id=run_id,
        incident_id=incident.incident_id,
        device_id=incident.reported_device_id,
        diagnosis=DiagnosisCode.LOCAL_ACCESS_LINK_FAILURE,
        action_type=ActionType.ONSITE_FIELD_VISIT,
        evidence_ids=("E1", "E2", "E3", "E4"),
        rationale="Phase 8C2 decision routing test.",
        status=ProposalStatus.REJECTED,
        created_at=now,
        updated_at=now,
    )
    approval = Approval(
        approval_id="APPROVAL-S3-8C2",
        tenant_id=tenant_id,
        run_id=run_id,
        proposal_id=proposal_id,
        decision=ApprovalDecision.REJECTED,
        decided_at=now,
        decided_by="phase8c2-test",
    )
    snapshot = RunStateSnapshot(
        run=run,
        incidents=(incident,),
        evidence=(),
        proposals=(proposal,),
        approvals=(approval,),
        executed_actions=(),
        work_orders=(),
        latest_event_seq=5,
    )
    result = ApprovalProcessed(
        ok=True,
        approval=approval,
        proposal=proposal,
        incident=incident,
        executed_action=None,
        work_order=None,
        replayed=False,
    )
    return snapshot, result


def test_phase8c2_scenario3_text_only_final_without_required_hitl_is_rescheduled():
    now = datetime.now(UTC)
    record = ApplicationOutboxRecord(
        outbox_id="OUTBOX-S3-8C2-HITL-GUARD",
        tenant_id="TENANT-S3-8C2-HITL-GUARD",
        run_id="RUN-S3-8C2-HITL-GUARD",
        event_seq=2,
        topic=AGENT_DISPATCH_TOPIC,
        payload={
            "event_id": "EVENT-S3-8C2-HITL-GUARD",
            "event_seq": 2,
            "signal": {"signal_type": "itsm.incident.created", "details": {}},
        },
        created_at=now,
        available_at=now,
        delivered_at=None,
        attempt_count=1,
    )
    outbox = _FakeOutbox(record)
    scenario1_runtime = _RecordingDispatchRuntime()
    scenario3_runtime = _RecordingDispatchRuntime(reach_hitl=False)
    worker = Scenario1DispatchWorker(
        uow_factory=lambda: _FakeDispatchUow(outbox),
        state_service=_FakeStateService("scenario-3"),
        agent_runtime=scenario1_runtime,
        scenario3_agent_runtime=scenario3_runtime,
    )

    processed = asyncio.run(worker.dispatch_once())

    assert processed is True
    assert len(scenario3_runtime.calls) == 1
    assert outbox.delivered is False
    assert outbox.rescheduled is True


def test_phase8c2_committed_field_decision_survives_runtime_selection_failure():
    snapshot, result = _scenario3_rejected_result()
    approval_service = _FakeApprovalService(result)
    scenario1_runtime = _RecordingResumeRuntime()
    scenario3_runtime = _RecordingResumeRuntime()
    container = ProductApiContainer(
        start_service=object(),
        state_service=_FailingRunStateService(),
        lifecycle_service=object(),
        approval_service=approval_service,
        fixture=object(),
        agent_runtime=scenario1_runtime,
        scenario3_agent_runtime=scenario3_runtime,
    )

    with TestClient(create_app(container)) as client:
        response = client.post(
            (
                f"/api/v1/runs/{snapshot.run.run_id}/proposals/"
                f"{result.proposal.proposal_id}/reject"
            ),
            headers={"X-Tenant-ID": snapshot.run.tenant_id},
            json={"decided_by": "phase8c2-test"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["approval"]["decision"] == "REJECTED"
    assert body["agent_resume"]["status"] == "deferred"
    assert body["agent_resume"]["retryable"] is True
    assert scenario1_runtime.calls == []
    assert scenario3_runtime.calls == []


def test_phase8c2_generic_field_decision_routes_resume_by_persisted_scenario_id():
    snapshot, result = _scenario3_rejected_result()
    approval_service = _FakeApprovalService(result)
    scenario1_runtime = _RecordingResumeRuntime()
    scenario3_runtime = _RecordingResumeRuntime()
    container = ProductApiContainer(
        start_service=object(),
        state_service=_FakeRunStateService(snapshot),
        lifecycle_service=object(),
        approval_service=approval_service,
        fixture=object(),
        agent_runtime=scenario1_runtime,
        scenario3_agent_runtime=scenario3_runtime,
    )

    with TestClient(create_app(container)) as client:
        response = client.post(
            (
                f"/api/v1/runs/{snapshot.run.run_id}/proposals/"
                f"{result.proposal.proposal_id}/reject"
            ),
            headers={"X-Tenant-ID": snapshot.run.tenant_id},
            json={"decided_by": "phase8c2-test"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["approval"]["decision"] == "REJECTED"
    assert body["agent_resume"]["status"] == "resumed"
    assert scenario1_runtime.calls == []
    assert len(scenario3_runtime.calls) == 1
    assert scenario3_runtime.calls[0]["run_id"] == snapshot.run.run_id
    assert (
        scenario3_runtime.calls[0]["proposal_id"]
        == result.proposal.proposal_id
    )
