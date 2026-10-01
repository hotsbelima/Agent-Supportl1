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

| Run | Model | Device tool | Dependent health tool | Result |
| --- | --- | --- | --- | --- |
| 1 | Gemini 3.5 Flash | Passed | Passed with returned `SITE-KZN-17` | Incomplete: the final model turn failed with Google `429 RESOURCE_EXHAUSTED` |

The first run demonstrates the required autonomous dependency: the agent called the device tool, observed `SITE-KZN-17`, then called the health tool with that exact returned ID. It did not receive a hand-entered site ID.

The run does **not** count as a success because the agent could not produce its terminal result. Dify Agent Beta spent the current Flash free-tier quota on intermediate reasoning and sandbox commands, then Google returned `429 RESOURCE_EXHAUSTED` for `gemini-3.5-flash`, with a limit of 5 requests per minute.

## Remaining acceptance gate

The spike remains pending. It passes only after five independent end-to-end runs each complete successfully with:

1. no initial `site_id`;
2. autonomous `spike_get_device` before `spike_get_site_health`;
3. health call using the device-tool result; and
4. a completed terminal response, without a model or tool error.

Do not start full Scenario 1 until this is 5/5.

## Required decision before rerunning at scale

Repeated runs under the current quota are not useful until the extra model turns are addressed. Preserve the handoff prompt and tool contracts unless a deliberate deviation is approved. The next operator must choose one of these paths:

- provide sufficient Gemini 3.5 Flash quota for Agent Beta's multi-turn execution; or
- explicitly approve a narrow spike-prompt amendment that prohibits Linux sandbox commands and requires the two API tools only, recording that deviation; or
- wait for a Dify/product change that makes the Agent Beta execution more efficient.

No provider plugin, MCP, n8n, Scenario 1 action endpoint, approval flow, or UI work is included in this spike.

## Compliance report

- Implemented: two read-only endpoints, `run_id` and evidence envelopes, public temporary preview, Dify tool attachment, and one autonomous dependent tool-chain observation.
- Passing: endpoint contract tests and independent Dify calls for both tools; first autonomous dependency sequence.
- Not passing: five consecutive complete autonomous runs; terminal completion under the current 5 RPM Flash quota.
- Deviation: the test model is Gemini 3.5 Flash rather than Flash-Lite, explicitly reclassified by the project owner as the current acceptance model. Flash-Lite support is deferred as nice-to-have.
