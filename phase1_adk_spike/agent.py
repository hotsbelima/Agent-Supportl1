"""ADK agent definition for the deliberately narrow Phase 1 spike."""

from google.adk.agents import Agent

from .contracts import MODEL
from .tools import get_device, run_diagnostic


root_agent = Agent(
    name="phase_1_dependency_spike",
    model=MODEL,
    instruction="""You are investigating one reported unreachable device.

The user supplies a device_id but no attachment_id. Independently use the
available read-only tools to investigate. You must obtain the attachment_id
from the get_device tool result before using run_diagnostic. Never invent,
infer, or request an attachment_id from the user. After the diagnostic, give a
short factual summary. Do not claim any repair or perform any action.
""",
    tools=[get_device, run_diagnostic],
)
