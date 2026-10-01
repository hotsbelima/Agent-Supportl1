# Phase 1 — Dify/Gemini Technical Spike Handoff

## Current scope decision

The current acceptance model is **Gemini 3.5 Flash** in Dify Agent Beta. `gemini-3.5-flash-lite` is a future nice-to-have, not a gate for this milestone.

Do not implement a custom Dify provider plugin for Flash-Lite as part of the current spike. If Flash-Lite is needed later, it will require a provider-level Dify plugin because the official OpenAI-compatible model is stored but appears only as incompatible in the Agent Beta selector. The related public Dify report is [dify-official-plugins#3993](https://github.com/langgenius/dify-official-plugins/issues/3993).

## Deployed spike interface

The Dify agent has exactly these two attached read-only tools:

| Tool | Input | Expected dependent result |
| --- | --- | --- |
| `spike_get_device` | `POS-KZN17-03` | Returns `site_id: SITE-KZN-17` with evidence `EVD-SPIKE-CMDB-001` |
| `spike_get_site_health` | `SITE-KZN-17` | Returns site-health evidence `EVD-SPIKE-SITE-001` |

Both tools were individually invoked successfully from Dify. They use the temporary public Vercel preview and do not expose actions or secrets.

## Acceptance test record

Test input, deliberately without `site_id`:

```json
{"incident_id":"INC-SPIKE-001","device_id":"POS-KZN17-03","run_id":"RUN-SPIKE-001"}
```

| Run | Temporary spike constraint | Device tool | Dependent health tool | Terminal JSON | Result |
| --- | --- | --- | --- | --- | --- |
| Baseline | No | Passed | Passed with returned `SITE-KZN-17` | No | Incomplete: final model turn failed with Google `429 RESOURCE_EXHAUSTED` |
| 1 | Yes | Passed | Passed with returned `SITE-KZN-17` | Yes | Passed |
| 2 | Yes | Passed | Passed with returned `SITE-KZN-17` | Yes | Passed |
| 3 | Yes | Passed | Passed with returned `SITE-KZN-17` | Yes | Passed |
| 4 | Yes | Passed | Passed with returned `SITE-KZN-17` | Yes | Passed |
| 5 | Yes | Passed | Not invoked | No | Incomplete: after the successful device response, Agent Beta neither invoked the health tool nor returned an error or terminal JSON during repeated observations |

The baseline run demonstrates the required autonomous dependency: the agent called the device tool, observed `SITE-KZN-17`, then called the health tool with that exact returned ID. It did not receive a hand-entered site ID. It did not count as a success because Dify Agent Beta spent the current Flash free-tier quota on intermediate reasoning and sandbox commands, then Google returned `429 RESOURCE_EXHAUSTED` for `gemini-3.5-flash`, with a limit of 5 requests per minute.

For runs 1–5, the project owner explicitly approved a narrow, temporary spike-prompt amendment: no Linux sandbox, shell, file-system, skill, or command tools; only the two attached read-only spike API tools. This did not prescribe a tool-call sequence. Runs 1–4 completed successfully with the required autonomous dependency and terminal JSON. Run 5 stalled after receiving the valid device result, without an exposed Dify or Google error.

## Remaining acceptance gate

The spike remains pending. It passes only after five independent end-to-end runs each complete successfully with:

1. no initial `site_id`;
2. autonomous `spike_get_device` before `spike_get_site_health`;
3. health call using the device-tool result; and
4. a completed terminal response, without a model or tool error.

The present result is **4 completed passes out of 5 attempted constrained runs**. Because the requirement is five consecutive successes, the stalled fifth run means the acceptance sequence cannot be marked passed; a future attempt must establish a new 5/5 sequence. Do not start full Scenario 1 until that is complete.

## Required decision before rerunning at scale

Repeated runs under the current quota were not useful until the extra model turns were addressed. The temporary prompt amendment fixed the quota waste, but run 5 exposed a separate Agent Beta continuation stall. Preserve the handoff prompt and tool contracts unless a deliberate deviation is approved. The next operator must first diagnose or obtain an explanation for that stall, then establish a fresh five-run sequence. Options include:

- provide sufficient Gemini 3.5 Flash quota for Agent Beta's multi-turn execution;
- retain the already approved, temporary sandbox prohibition while investigating the Agent Beta continuation stall; or
- wait for a Dify/product change that makes the Agent Beta execution more reliable.

No provider plugin, MCP, n8n, Scenario 1 action endpoint, approval flow, or UI work is included in this spike.

## Mandatory final-stage decision with the project owner

At the final stage of development, before declaring the implementation ready for production, **ask the project owner explicitly** whether to include either of the following. Do not add either automatically:

1. Production resilience for an Agent Beta continuation that stalls after a successful tool response: bounded timeouts, backend-owned retry/resume policy, and `run_id`-based operational logging.
2. A standalone Dify provider plugin for `gemini-3.5-flash-lite`, with a provider-level credential and declared tool-call capability. This remains a nice-to-have workaround for the current Agent Beta model-selector limitation, not a Phase 1 gate.

The answer must be recorded as an explicit scope decision. These concerns were observed in the temporary spike only and must not silently alter the production architecture, approval flow, guardrails, or tool contracts.

## Compliance report

- Implemented: two read-only endpoints, `run_id` and evidence envelopes, public temporary preview, Dify tool attachment, and five observed autonomous runs.
- Passing: endpoint contract tests and independent Dify calls for both tools; four complete constrained autonomous runs with correct dependent calls and terminal JSON.
- Not passing: five consecutive complete autonomous runs. The original baseline failed on 5 RPM quota; after the prompt amendment, the fifth run stalled after the device tool without an exposed error.
- Deviation: the temporary prompt amendment prohibits sandbox/command exploration only in this spike agent, explicitly approved by the project owner and not applicable to production. The test model is Gemini 3.5 Flash rather than Flash-Lite; Flash-Lite support is deferred as nice-to-have.
