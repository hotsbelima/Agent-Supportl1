from phase1_adk_spike.agent import root_agent
from phase1_adk_spike.contracts import ATTACHMENT_ID, DEVICE_ID, INITIAL_EVENT
from phase1_adk_spike.runner import validate_tool_dependency
from phase1_adk_spike.tools import get_device, run_diagnostic


def test_initial_input_does_not_leak_attachment_id() -> None:
    assert "attachment_id" not in INITIAL_EVENT
    assert ATTACHMENT_ID not in INITIAL_EVENT.values()


def test_agent_exposes_exactly_two_function_tools() -> None:
    assert [tool.__name__ for tool in root_agent.tools] == [
        "get_device",
        "run_diagnostic",
    ]


def test_fixture_dependency_is_real() -> None:
    device = get_device(DEVICE_ID)
    assert device["ok"] is True
    assert device["attachment_id"] == ATTACHMENT_ID
    diagnostic = run_diagnostic(device["attachment_id"])
    assert diagnostic == {
        "ok": True,
        "attachment_id": ATTACHMENT_ID,
        "diagnostic": "LINK_DOWN",
        "observed_state": "network interface has no carrier",
    }


def test_dependency_validator_rejects_an_invented_second_argument() -> None:
    result = validate_tool_dependency(
        [
            {"name": "get_device", "args": {"device_id": DEVICE_ID}},
            {"name": "run_diagnostic", "args": {"attachment_id": "invented"}},
        ],
        [{"name": "get_device", "response": {"attachment_id": ATTACHMENT_ID}}],
    )
    assert result["passed"] is False
    assert result["second_call_used_returned_attachment_id"] is False


def test_dependency_validator_accepts_observed_dependent_calls() -> None:
    result = validate_tool_dependency(
        [
            {"name": "get_device", "args": {"device_id": DEVICE_ID}},
            {"name": "run_diagnostic", "args": {"attachment_id": ATTACHMENT_ID}},
        ],
        [{"name": "get_device", "response": {"attachment_id": ATTACHMENT_ID}}],
    )
    assert result["passed"] is True
