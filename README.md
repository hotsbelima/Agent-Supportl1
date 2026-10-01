# Autonomous L1 Incident Agent

This repository begins with the Phase 1 Dify/Gemini technical spike from the v4.1 handoff. The scope is intentionally limited to two dependent read-only HTTP tools. It does not include the full Scenario 1 backend, UI, persistence, approvals, MCP, or n8n.

## Tool contracts

The source contracts and agent prompt are retained in [`docs/handoff`](docs/handoff). After a Vercel Preview deployment, replace `https://REPLACE_WITH_PUBLIC_SPIKE_BASE_URL` in `docs/handoff/dify_spike_openapi_v1_1.yaml` with that preview origin and import it into Dify.

| Tool | Endpoint | Input | Dependency |
| --- | --- | --- | --- |
| `spike_get_device` | `GET /api/spike/cmdb/devices/{device_id}` | `POS-KZN17-03` | Initial event supplies `device_id` |
| `spike_get_site_health` | `GET /api/spike/monitoring/sites/{site_id}` | `SITE-KZN-17` | The agent must learn `site_id` from the first tool result |

Known values respond with `200` and `ok: true`. Unknown values intentionally respond with `200` and `ok: false`, so the Dify experiment can observe a structured domain failure instead of a transport failure. Each response has a server-generated `observed_at` timestamp.

## Dify acceptance gate

1. Use `docs/handoff/agent_system_prompt_v1_1.txt` as the agent system prompt.
2. Import the deployed OpenAPI document as the only tool source.
3. Send an initial event with `device_id: POS-KZN17-03` and no `site_id`.
4. Run the same input five times, without entering tool arguments or prompting the model between calls.
5. Pass only if all five runs call `spike_get_device`, then call `spike_get_site_health` using the observed `SITE-KZN-17`.
6. Record the exact Gemini model/version, Dify version and settings, maximum iterations, and Dify handling of `200` plus `ok:false`.

Do not implement full Scenario 1 until this result is 5/5.
