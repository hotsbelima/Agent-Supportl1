from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from google.adk.tools import FunctionTool

from agent_runtime.agent import AGENT_INSTRUCTION, MODEL, build_scenario1_agent
from agent_runtime.retry import ProductRetryableToolPlugin
from product_backend.contracts.tools import MODEL_VISIBLE_TOOL_NAMES
from scripts.phase6b_live_acceptance import (
    REQUIRED_PROPOSAL_TOOLS,
    _proposal_uses_required_prior_evidence,
)


class _UnusedAdapter:
    async def get_device(self, context, request):
        raise AssertionError("not invoked")

    async def get_site_health(self, context, request):
        raise AssertionError("not invoked")

    async def run_diagnostic(self, context, request):
        raise AssertionError("not invoked")

    async def search_incidents(self, context, request):
        raise AssertionError("not invoked")

    async def search_kb(self, context, request):
        raise AssertionError("not invoked")

    async def propose_field_visit(self, context, request):
        raise AssertionError("not invoked")


def _parameter_schema(tool: FunctionTool) -> dict[str, Any]:
    declaration = tool._get_declaration()
    assert declaration is not None

    if declaration.parameters_json_schema is not None:
        return declaration.parameters_json_schema

    assert declaration.parameters is not None
    return declaration.parameters.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )


def test_agent_uses_expected_model_and_exactly_six_native_function_tools():
    async def scenario() -> None:
        agent = build_scenario1_agent(_UnusedAdapter())
        assert agent.model == MODEL == "gemini-3.5-flash-lite"

        tools = await agent.canonical_tools()
        assert [tool.name for tool in tools] == list(MODEL_VISIBLE_TOOL_NAMES)
        assert all(isinstance(tool, FunctionTool) for tool in tools)

    asyncio.run(scenario())


def test_native_adk_schemas_hide_trusted_context_and_match_contract():
    async def scenario() -> None:
        agent = build_scenario1_agent(_UnusedAdapter())
        tools = {
            tool.name: tool
            for tool in await agent.canonical_tools()
        }

        expected = {
            "get_device": {"device_id"},
            "get_site_health": {"site_id"},
            "run_diagnostic": {"diagnostic_type", "target_id"},
            "search_incidents": {"scope", "entity_id"},
            "search_kb": {"query"},
            "propose_field_visit": {
                "incident_id",
                "device_id",
                "diagnosis",
                "evidence_ids",
                "rationale",
            },
        }

        assert set(tools) == set(expected)
        for name, expected_parameters in expected.items():
            schema = _parameter_schema(tools[name])
            properties = schema.get("properties", {})
            assert set(properties) == expected_parameters
            assert "tool_context" not in properties
            assert "tenant_id" not in properties
            assert "run_id" not in properties

        diagnostic_schema = _parameter_schema(tools["run_diagnostic"])
        assert "ACCESS_LINK" in str(
            diagnostic_schema["properties"]["diagnostic_type"]
        )

        incident_schema = _parameter_schema(tools["search_incidents"])
        scope_schema = str(incident_schema["properties"]["scope"])
        assert "DEVICE" in scope_schema
        assert "SITE" in scope_schema

        proposal_schema = _parameter_schema(tools["propose_field_visit"])
        assert "LOCAL_ACCESS_LINK_FAILURE" in str(
            proposal_schema["properties"]["diagnosis"]
        )

        get_device_description = str(
            _parameter_schema(tools["get_device"])["properties"]["device_id"]
        )
        assert "reported_device_id" in get_device_description
        assert "peer_device_id" in get_device_description
        assert "attachment_id" in get_device_description

        diagnostic_target_description = str(
            diagnostic_schema["properties"]["target_id"]
        )
        assert "attachment_id" in diagnostic_target_description
        assert "device_id" in diagnostic_target_description
        assert "port_id" in diagnostic_target_description

        evidence_description = str(
            proposal_schema["properties"]["evidence_ids"]
        )
        for required_source in (
            "CMDB_SNAPSHOT",
            "SITE_HEALTH",
            "ACCESS_LINK_DIAGNOSTIC",
            "KB_ARTICLE",
        ):
            assert required_source in evidence_description

    asyncio.run(scenario())


def test_agent_instruction_preserves_autonomy_but_requires_valid_dependencies():
    assert "no global tool sequence is prescribed" in AGENT_INSTRUCTION
    assert "reported_device_id" in AGENT_INSTRUCTION
    assert "exact attachment_id" in AGENT_INSTRUCTION
    assert "CMDB_SNAPSHOT" in AGENT_INSTRUCTION
    assert "SITE_HEALTH" in AGENT_INSTRUCTION
    assert "ACCESS_LINK_DIAGNOSTIC" in AGENT_INSTRUCTION
    assert "KB_ARTICLE" in AGENT_INSTRUCTION
    assert "INCIDENT_SEARCH" in AGENT_INSTRUCTION
    assert "do not submit the same proposal again" in AGENT_INSTRUCTION


def test_live_acceptance_requires_only_scenario1_proposal_prerequisites():
    assert REQUIRED_PROPOSAL_TOOLS == {
        "get_device",
        "get_site_health",
        "run_diagnostic",
        "search_kb",
        "propose_field_visit",
    }
    assert "search_incidents" not in REQUIRED_PROPOSAL_TOOLS
    assert REQUIRED_PROPOSAL_TOOLS.issubset(set(MODEL_VISIBLE_TOOL_NAMES))


def test_live_acceptance_requires_all_four_evidence_classes_from_prior_results():
    prior = {
        "E-CMDB": "CMDB_SNAPSHOT",
        "E-SITE": "SITE_HEALTH",
        "E-DIAG": "ACCESS_LINK_DIAGNOSTIC",
        "E-KB": "KB_ARTICLE",
        "E-INC": "INCIDENT_SEARCH",
    }

    assert _proposal_uses_required_prior_evidence(
        ["E-CMDB", "E-SITE", "E-DIAG", "E-KB"],
        prior,
    )
    assert not _proposal_uses_required_prior_evidence(
        ["E-CMDB", "E-SITE", "E-KB", "E-INC"],
        prior,
    )
    assert not _proposal_uses_required_prior_evidence(
        ["E-CMDB", "E-SITE", "E-DIAG", "E-MISSING"],
        prior,
    )
    assert not _proposal_uses_required_prior_evidence(
        ["E-CMDB", "E-SITE", "E-DIAG", "E-DIAG"],
        prior,
    )


def test_retry_plugin_reflects_only_product_retryable_failures():
    async def scenario() -> None:
        async def dummy_tool() -> dict[str, bool]:
            return {"ok": True}

        tool = FunctionTool(dummy_tool)
        context = SimpleNamespace(invocation_id="INV-6B-RETRY")
        plugin = ProductRetryableToolPlugin(
            max_retries=2,
            throw_exception_if_retry_exceeded=False,
        )

        retryable = await plugin.after_tool_callback(
            tool=tool,
            tool_args={},
            tool_context=context,
            result={
                "ok": False,
                "error": {
                    "code": "UPSTREAM_UNAVAILABLE",
                    "message": "Temporary source failure.",
                    "retryable": True,
                    "details": {"reason": "temporary"},
                },
            },
        )
        assert retryable is not None
        assert retryable["response_type"] == "ERROR_HANDLED_BY_REFLECT_AND_RETRY_PLUGIN"
        assert retryable["retry_count"] == 1

        non_retryable = await plugin.after_tool_callback(
            tool=tool,
            tool_args={},
            tool_context=SimpleNamespace(invocation_id="INV-6B-NONRETRY"),
            result={
                "ok": False,
                "error": {
                    "code": "INVALID_ARGUMENT",
                    "message": "Bad input.",
                    "retryable": False,
                    "details": {},
                },
            },
        )
        assert non_retryable is None

    asyncio.run(scenario())
