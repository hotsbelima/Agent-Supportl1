from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
import os
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

import agent_runtime.service as service_module
from agent_runtime.human_decision import (
    WAIT_FOR_HUMAN_DECISION_TOOL,
    build_human_decision_wait_tool,
)
from agent_runtime.service import AgentResumeResult
from agent_runtime.sessions import (
    create_database_session_service,
    get_run_session,
)
from product_api.app import create_app
from product_backend.domain.enums import OperationalState
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    normalize_database_url,
)
from scripts.phase4d_seed_proposal import seed as seed_pending_proposal


PROPOSAL_ID = "PROPOSAL-6C-NATIVE"


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")
    return normalize_database_url(value)


class _ScriptedModel(BaseLlm):
    model: str = "phase6c-scripted"
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


def _wait_call(proposal_id: str = PROPOSAL_ID) -> types.Part:
    return types.Part.from_function_call(
        name=WAIT_FOR_HUMAN_DECISION_TOOL,
        args={"proposal_id": proposal_id},
    )


def _build_test_agent(
    model: BaseLlm,
    proposal_calls: list[str],
) -> LlmAgent:
    async def propose_field_visit() -> dict[str, Any]:
        proposal_calls.append(PROPOSAL_ID)
        return {
            "ok": True,
            "proposal": {
                "proposal_id": PROPOSAL_ID,
                "status": "PENDING_APPROVAL",
            },
        }

    return LlmAgent(
        name="phase6c_test_agent",
        model=model,
        instruction=(
            "Create the proposal, then wait for the external human decision. "
            "After resume, answer without calling more tools."
        ),
        tools=[
            FunctionTool(propose_field_visit),
            build_human_decision_wait_tool(),
        ],
    )


def _decision_payload(
    *,
    decision: str = "REJECTED",
    proposal_status: str = "REJECTED",
) -> dict[str, Any]:
    return {
        "status": "human_decision_committed",
        "decision": decision,
        "proposal_id": PROPOSAL_ID,
        "proposal_status": proposal_status,
        "incident_id": "INC-1042",
        "incident_status": "OPEN",
        "executed_action": None,
        "work_order": None,
        "repair_confirmed": False,
        "replayed": False,
    }


def _function_responses(session, name: str) -> list[types.FunctionResponse]:
    return [
        response
        for event in session.events
        if event.author == "user"
        for response in event.get_function_responses()
        if response.name == name
    ]


def test_phase6c_tool_composition_uses_native_long_running_wait_after_product_tools():
    async def scenario() -> None:
        from agent_runtime.agent import build_scenario1_agent
        from product_backend.contracts.tools import MODEL_VISIBLE_TOOL_NAMES

        class UnusedAdapter:
            pass

        agent = build_scenario1_agent(UnusedAdapter())
        tools = await agent.canonical_tools()

        assert [tool.name for tool in tools[:-1]] == list(MODEL_VISIBLE_TOOL_NAMES)
        assert all(
            isinstance(tool, FunctionTool)
            and not isinstance(tool, LongRunningFunctionTool)
            for tool in tools[:-1]
        )
        assert tools[-1].name == WAIT_FOR_HUMAN_DECISION_TOOL
        assert isinstance(tools[-1], LongRunningFunctionTool)

        declaration = tools[-1]._get_declaration()
        assert declaration is not None
        schema = declaration.parameters_json_schema
        if schema is None:
            assert declaration.parameters is not None
            schema = declaration.parameters.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
        assert set(schema.get("properties", {})) == {"proposal_id"}
        assert "tool_context" not in schema.get("properties", {})

    asyncio.run(scenario())


def test_native_adk_proposal_executes_before_pause_and_same_invocation_resumes(
    monkeypatch,
):
    async def scenario() -> None:
        proposal_calls: list[str] = []
        model = _ScriptedModel(
            steps=[
                _proposal_call(),
                _wait_call(),
                "Human rejected the field visit; no execution occurred.",
            ]
        )
        monkeypatch.setattr(
            service_module,
            "build_scenario1_agent",
            lambda adapter: _build_test_agent(model, proposal_calls),
        )
        sessions = InMemorySessionService()
        runtime = service_module.Scenario1AgentRuntime(
            adapter=object(),
            session_service=sessions,
        )
        tenant_id = "TENANT-6C-NATIVE"
        run_id = "RUN-6C-NATIVE"

        try:
            paused = await runtime.invoke(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_signal={"incidents": []},
            )

            assert proposal_calls == [PROPOSAL_ID]
            assert len(model.requests) == 2
            assert paused.awaiting_human_decision is True
            assert paused.pending_proposal_id == PROPOSAL_ID
            assert paused.paused_function_call_id
            assert paused.invocation_id

            session = await get_run_session(
                sessions,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            wait_events = [
                event
                for event in session.events
                if any(
                    call.name == WAIT_FOR_HUMAN_DECISION_TOOL
                    for call in event.get_function_calls()
                )
            ]
            assert len(wait_events) == 1
            assert paused.paused_function_call_id in set(
                wait_events[0].long_running_tool_ids or []
            )

            correlation = await runtime.find_human_decision_correlation(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=PROPOSAL_ID,
            )
            assert correlation is not None
            assert correlation.invocation_id == paused.invocation_id
            assert correlation.function_call_id == paused.paused_function_call_id
            assert correlation.response_delivered is False
            assert correlation.completed is False

            resumed = await runtime.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=PROPOSAL_ID,
                decision_payload=_decision_payload(),
            )
            assert resumed.invocation_id == paused.invocation_id
            assert resumed.function_call_id == paused.paused_function_call_id
            assert resumed.already_resumed is False
            assert "rejected" in (resumed.final_answer or "").lower()

            session = await get_run_session(
                sessions,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            responses = _function_responses(
                session,
                WAIT_FOR_HUMAN_DECISION_TOOL,
            )
            assert len(responses) == 1
            assert responses[0].id == paused.paused_function_call_id
            assert responses[0].response["decision"] == "REJECTED"

            replay = await runtime.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=PROPOSAL_ID,
                decision_payload=_decision_payload(),
            )
            assert replay.already_resumed is True
            assert replay.invocation_id == paused.invocation_id

            session = await get_run_session(
                sessions,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            assert len(
                _function_responses(session, WAIT_FOR_HUMAN_DECISION_TOOL)
            ) == 1
        finally:
            await runtime.close()

    asyncio.run(scenario())


def test_resume_reconciles_function_response_persisted_before_provider_failure(
    monkeypatch,
):
    async def scenario() -> None:
        proposal_calls: list[str] = []
        model = _ScriptedModel(
            steps=[
                _proposal_call(),
                _wait_call(),
                RuntimeError("simulated provider failure after resume delivery"),
                "Recovered from persisted human decision without duplicate delivery.",
            ]
        )
        monkeypatch.setattr(
            service_module,
            "build_scenario1_agent",
            lambda adapter: _build_test_agent(model, proposal_calls),
        )
        sessions = InMemorySessionService()
        runtime = service_module.Scenario1AgentRuntime(
            adapter=object(),
            session_service=sessions,
        )
        tenant_id = "TENANT-6C-RECOVERY"
        run_id = "RUN-6C-RECOVERY"

        try:
            paused = await runtime.invoke(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_signal={"incidents": []},
            )
            assert paused.awaiting_human_decision is True

            with pytest.raises(
                RuntimeError,
                match="simulated provider failure",
            ):
                await runtime.resume_human_decision(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    proposal_id=PROPOSAL_ID,
                    decision_payload=_decision_payload(),
                )

            session = await get_run_session(
                sessions,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            assert len(
                _function_responses(session, WAIT_FOR_HUMAN_DECISION_TOOL)
            ) == 1

            correlation = await runtime.find_human_decision_correlation(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=PROPOSAL_ID,
            )
            assert correlation is not None
            assert correlation.response_delivered is True
            assert correlation.completed is False

            recovered = await runtime.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=PROPOSAL_ID,
                decision_payload=_decision_payload(),
            )
            assert recovered.already_resumed is False
            assert "without duplicate delivery" in (
                recovered.final_answer or ""
            ).lower()

            session = await get_run_session(
                sessions,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            assert len(
                _function_responses(session, WAIT_FOR_HUMAN_DECISION_TOOL)
            ) == 1
        finally:
            await runtime.close()

    asyncio.run(scenario())


def test_persisted_pause_resumes_after_new_engine_and_runtime(monkeypatch):
    async def scenario() -> None:
        tenant_id = f"TENANT-6C-RESTART-{uuid4().hex[:8]}"
        run_id = f"RUN-6C-RESTART-{uuid4().hex[:10]}"
        proposal_calls: list[str] = []

        engine1 = create_engine(DatabaseSettings(url=_database_url()))
        sessions1 = create_database_session_service(engine1)
        await sessions1.prepare_tables()
        first_model = _ScriptedModel(
            steps=[
                _proposal_call(),
                _wait_call(),
            ]
        )
        monkeypatch.setattr(
            service_module,
            "build_scenario1_agent",
            lambda adapter: _build_test_agent(first_model, proposal_calls),
        )
        runtime1 = service_module.Scenario1AgentRuntime(
            adapter=object(),
            session_service=sessions1,
        )

        paused_invocation_id: str
        try:
            paused = await runtime1.invoke(
                tenant_id=tenant_id,
                run_id=run_id,
                operational_signal={"incidents": []},
            )
            assert paused.awaiting_human_decision is True
            assert paused.invocation_id is not None
            paused_invocation_id = paused.invocation_id
        finally:
            await runtime1.close()
            await engine1.dispose()

        engine2 = create_engine(DatabaseSettings(url=_database_url()))
        sessions2 = create_database_session_service(engine2)
        await sessions2.prepare_tables()
        second_model = _ScriptedModel(
            steps=["Approved field visit was registered; repair is not confirmed."]
        )
        monkeypatch.setattr(
            service_module,
            "build_scenario1_agent",
            lambda adapter: _build_test_agent(second_model, proposal_calls),
        )
        runtime2 = service_module.Scenario1AgentRuntime(
            adapter=object(),
            session_service=sessions2,
        )
        try:
            resumed = await runtime2.resume_human_decision(
                tenant_id=tenant_id,
                run_id=run_id,
                proposal_id=PROPOSAL_ID,
                decision_payload=_decision_payload(
                    decision="APPROVED",
                    proposal_status="EXECUTED",
                )
                | {
                    "incident_status": "ESCALATED",
                    "executed_action": {
                        "action_id": "ACTION-1",
                        "action_type": "ONSITE_FIELD_VISIT",
                    },
                    "work_order": {
                        "work_order_id": "WORKORDER-1",
                        "site_id": "SITE-KZN-017",
                        "device_id": "POS-KZN17-02",
                        "switch_id": "SW-KZN17-01",
                        "port_id": "Gi1/0/18",
                    },
                },
            )
            assert resumed.invocation_id == paused_invocation_id
            assert "repair is not confirmed" in (
                resumed.final_answer or ""
            ).lower()

            session = await get_run_session(
                sessions2,
                tenant_id=tenant_id,
                run_id=run_id,
            )
            assert session is not None
            assert len(
                _function_responses(session, WAIT_FOR_HUMAN_DECISION_TOOL)
            ) == 1
        finally:
            await runtime2.close()
            await engine2.dispose()

    asyncio.run(scenario())


class _RecordingRuntime:
    model = "phase6c-recording"
    gemini_configured = True
    resumability_wired = True

    def __init__(self, *, fail_resume: bool = False) -> None:
        self.fail_resume = fail_resume
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def resume_human_decision(
        self,
        *,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
        decision_payload: dict[str, Any],
    ) -> AgentResumeResult:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "run_id": run_id,
                "proposal_id": proposal_id,
                "decision_payload": decision_payload,
            }
        )
        if self.fail_resume:
            raise RuntimeError("simulated post-commit ADK outage")
        return AgentResumeResult(
            invocation_id="INV-6C-RECORDED",
            function_call_id="CALL-6C-RECORDED",
            final_answer="Human decision reflected by the resumed agent.",
            already_resumed=False,
        )

    async def close(self) -> None:
        self.closed = True


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-ID": tenant_id}


def _start_and_seed(client: TestClient, tenant_id: str) -> tuple[str, str]:
    started = client.post(
        "/api/v1/scenario-1/runs",
        headers=_headers(tenant_id),
    )
    assert started.status_code == 201, started.text
    run_id = started.json()["run"]["run_id"]
    seeded = asyncio.run(
        seed_pending_proposal(
            tenant_id=tenant_id,
            run_id=run_id,
        )
    )
    return run_id, str(seeded["proposal_id"])


def _replace_runtime(client: TestClient, runtime: _RecordingRuntime) -> None:
    container = client.app.state.product_container
    original = container.agent_runtime
    if original is not None:
        asyncio.run(original.close())
    container.agent_runtime = runtime


def test_health_exposes_phase6c_native_resumability():
    with TestClient(create_app()) as client:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["phase"] == 6
        assert body["checkpoint"] == "6C"
        assert body["adk_wired"] is True
        assert body["adk_session_persistence_wired"] is True
        assert body["adk_resumability_wired"] is True


def test_product_commit_survives_resume_failure_and_replay_reconciles():
    tenant_id = f"TENANT-6C-DEFER-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id, proposal_id = _start_and_seed(client, tenant_id)
        runtime = _RecordingRuntime(fail_resume=True)
        _replace_runtime(client, runtime)

        approved = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert approved.status_code == 200, approved.text
        first = approved.json()
        assert first["replayed"] is False
        assert first["approval"]["decision"] == "APPROVED"
        assert first["proposal"]["status"] == "EXECUTED"
        assert first["incident"]["status"] == "ESCALATED"
        assert first["executed_action"] is not None
        assert first["work_order"] is not None
        assert first["agent_resume"] == {
            "status": "deferred",
            "invocation_id": None,
            "function_call_id": None,
            "final_answer": None,
            "retryable": True,
        }

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        assert state.status_code == 200
        snapshot = state.json()
        assert len(snapshot["approvals"]) == 1
        assert len(snapshot["executed_actions"]) == 1
        assert len(snapshot["work_orders"]) == 1

        runtime.fail_resume = False
        replayed = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert replayed.status_code == 200, replayed.text
        second = replayed.json()
        assert second["replayed"] is True
        assert second["approval"]["approval_id"] == first["approval"]["approval_id"]
        assert (
            second["executed_action"]["action_id"]
            == first["executed_action"]["action_id"]
        )
        assert (
            second["work_order"]["work_order_id"]
            == first["work_order"]["work_order_id"]
        )
        assert second["agent_resume"]["status"] == "resumed"
        assert second["agent_resume"]["retryable"] is False

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        )
        snapshot = state.json()
        assert len(snapshot["approvals"]) == 1
        assert len(snapshot["executed_actions"]) == 1
        assert len(snapshot["work_orders"]) == 1
        assert len(runtime.calls) == 2
        assert runtime.calls[0]["decision_payload"]["repair_confirmed"] is False
        assert runtime.calls[1]["decision_payload"]["replayed"] is True


def test_reject_result_is_returned_to_resume_without_execution():
    tenant_id = f"TENANT-6C-REJECT-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id, proposal_id = _start_and_seed(client, tenant_id)
        runtime = _RecordingRuntime()
        _replace_runtime(client, runtime)

        rejected = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/reject",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert rejected.status_code == 200, rejected.text
        body = rejected.json()
        assert body["approval"]["decision"] == "REJECTED"
        assert body["proposal"]["status"] == "REJECTED"
        assert body["incident"]["status"] == "OPEN"
        assert body["executed_action"] is None
        assert body["work_order"] is None
        assert body["agent_resume"]["status"] == "resumed"

        assert len(runtime.calls) == 1
        payload = runtime.calls[0]["decision_payload"]
        assert payload["decision"] == "REJECTED"
        assert payload["proposal_status"] == "REJECTED"
        assert payload["executed_action"] is None
        assert payload["work_order"] is None
        assert payload["repair_confirmed"] is False

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        ).json()
        assert len(state["approvals"]) == 1
        assert state["executed_actions"] == []
        assert state["work_orders"] == []


def test_stale_approve_resumes_with_no_execution_and_no_repair_claim():
    tenant_id = f"TENANT-6C-STALE-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id, proposal_id = _start_and_seed(client, tenant_id)
        container = client.app.state.product_container
        original_diagnostic = container.fixture.run_diagnostic

        async def recovered_access_link(**kwargs):
            result = await original_diagnostic(**kwargs)
            assert result is not None
            return replace(result, operational_state=OperationalState.UP)

        container.fixture.run_diagnostic = recovered_access_link

        runtime = _RecordingRuntime()
        _replace_runtime(client, runtime)

        approved = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert approved.status_code == 200, approved.text
        body = approved.json()
        assert body["approval"]["decision"] == "APPROVED"
        assert body["proposal"]["status"] == "STALE"
        assert body["incident"]["status"] == "OPEN"
        assert body["executed_action"] is None
        assert body["work_order"] is None
        assert body["agent_resume"]["status"] == "resumed"

        assert len(runtime.calls) == 1
        payload = runtime.calls[0]["decision_payload"]
        assert payload["decision"] == "APPROVED"
        assert payload["proposal_status"] == "STALE"
        assert payload["executed_action"] is None
        assert payload["work_order"] is None
        assert payload["repair_confirmed"] is False

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        ).json()
        assert len(state["approvals"]) == 1
        assert state["executed_actions"] == []
        assert state["work_orders"] == []


def test_retryable_revalidation_failure_consumes_no_decision_and_does_not_resume():
    tenant_id = f"TENANT-6C-RETRYABLE-{uuid4().hex[:8]}"

    with TestClient(create_app()) as client:
        run_id, proposal_id = _start_and_seed(client, tenant_id)
        container = client.app.state.product_container

        async def unavailable_diagnostic(**kwargs):
            del kwargs
            raise RuntimeError("simulated monitoring outage")

        container.fixture.run_diagnostic = unavailable_diagnostic

        runtime = _RecordingRuntime()
        _replace_runtime(client, runtime)

        approved = client.post(
            f"/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
            headers=_headers(tenant_id),
            json={"decided_by": "human-operator"},
        )
        assert approved.status_code == 503, approved.text
        body = approved.json()
        assert body["error"]["code"] == "DIAGNOSTIC_UNAVAILABLE"
        assert body["error"]["retryable"] is True
        assert runtime.calls == []

        state = client.get(
            f"/api/v1/runs/{run_id}",
            headers=_headers(tenant_id),
        ).json()
        assert state["run"]["status"] == "WAITING_APPROVAL"
        assert state["proposals"][0]["status"] == "PENDING_APPROVAL"
        assert state["approvals"] == []
        assert state["executed_actions"] == []
        assert state["work_orders"] == []
