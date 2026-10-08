"""Diagnostics must correlate concurrent calls and never log prompt/credential data."""

import asyncio
import logging

import pytest
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from agent_runtime.gemini_keys import (
    InstrumentedGemini, diagnostic_invocation, error_metadata, update_diagnostic_context,
)


def test_success_failure_and_concurrent_run_metadata(monkeypatch, caplog):
    secret = "PRIVATE-PROMPT-AND-KEY-DO-NOT-LOG"

    async def scripted(self, request, stream=False):
        await asyncio.sleep(0)
        if request.contents[0].parts[0].text == secret + "fail":
            error = RuntimeError(secret)
            error.code = 503
            raise error
        yield LlmResponse(usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=42, candidates_token_count=5, total_token_count=47,
        ))

    monkeypatch.setattr(Gemini, "generate_content_async", scripted)

    @diagnostic_invocation
    async def invoke(*, run_id, operational_fact, fail=False):
        update_diagnostic_context(provider="primary", attempt=2, invocation_id=run_id + "-inv")
        model = InstrumentedGemini(model="gemini-test")
        request = LlmRequest(model="gemini-test", contents=[types.Content(
            role="user", parts=[types.Part(text=secret + ("fail" if fail else ""))],
        )], config=types.GenerateContentConfig(http_options=types.HttpOptions(
            headers={"Authorization": secret},
        )))
        async for _ in model.generate_content_async(request):
            pass

    async def scenario():
        results = await asyncio.gather(
            invoke(run_id="RUN-success", operational_fact={"event": {"event_seq": 4}}),
            invoke(run_id="RUN-failure", operational_fact={"event": {"event_seq": 4}}, fail=True),
            return_exceptions=True,
        )
        assert results[0] is None
        assert isinstance(results[1], RuntimeError)

    caplog.set_level(logging.INFO)
    asyncio.run(scenario())
    assert secret not in caplog.text
    success = next(record.getMessage() for record in caplog.records if "Gemini request success" in record.message)
    failure = next(record.getMessage() for record in caplog.records if "Gemini request error" in record.message)
    assert "run_id=RUN-success" in success
    assert "prompt_tokens=42" in success
    assert "call_seq=1" in success
    assert "run_id=RUN-failure" in failure
    assert "status_code=503" in failure
    assert "attempt=2" in failure


def test_wrapped_error_status_is_preserved_without_error_text():
    underlying = RuntimeError("sensitive provider payload")
    underlying.code = 503
    wrapped = RuntimeError("sensitive wrapper")
    wrapped.__cause__ = underlying
    assert error_metadata(wrapped) == {
        "error_types": "RuntimeError>RuntimeError", "status_code": 503, "code": 503,
    }


def test_scenario2_adapter_does_not_log_raw_exception(caplog):
    from product_backend.adapters.scenario2_tool_adapters import DefaultScenario2ToolAdapter

    async def broken():
        raise RuntimeError("PRIVATE-DATABASE-ERROR-DO-NOT-LOG")

    adapter = DefaultScenario2ToolAdapter(read_service=None, proposal_service=None)
    caplog.set_level(logging.INFO)
    result = asyncio.run(adapter._invoke(
        operation=broken, unexpected_reason="propose_major_incident_unexpected_failure",
    ))
    assert result.ok is False
    assert "error_type=RuntimeError" in caplog.text
    assert "PRIVATE-DATABASE-ERROR-DO-NOT-LOG" not in caplog.text
