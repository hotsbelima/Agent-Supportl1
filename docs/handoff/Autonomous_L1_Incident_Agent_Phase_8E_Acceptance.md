# Phase 8E — Scenario 3 live acceptance

**Result: PASS — managed live acceptance completed.**

Date: 2026-10-06

## Deployment under test

- Repository: `hotsbelima/Agent-Supportl1`
- Branch: `phase-8d-scenario3-ui`
- Live code checkpoint: `ebb84fe6da3b4003bbe20888f7d014c0d9bf7e7a`
- Branch head deployed and live-validated: `7232df9554aa15037a52a4051d5ae9939eb5799a`
- GitHub Actions: [run 37512371216](https://github.com/hotsbelima/Agent-Supportl1/actions/runs/37512371216) — SUCCESS
- Northflank build/deployment: `offbeat-belief-6823`
- Managed Product API: <https://p01--product-api--yxz5y8myjdln.code.run/>
- Service/pod: `product-api` / `product-api-d8585bb94-l2ftt`; Running, 1/1 passing
- Managed PostgreSQL: reachable; live `alembic_version` head `20261006_0006`
- Product health confirmed before acceptance: database reachable, native ADK persistence/resume available, Scenario 3 provider reads and native tools wired, Gemini configured as `gemini-3.5-flash-lite`.
- No production code was changed for Phase 8E.

## Canonical live run

- Run: `RUN-126e81e8badd4ab39ffe6f93a2618009`
- Tenant: `TENANT-8OCT`
- Scenario: `scenario-3`
- Incident: `INC-S3-KZN-001`
- Persistent Google ADK session: `RUN-126e81e8badd4ab39ffe6f93a2618009` (`session_id == run_id`)
- Native invocation: `e-4285c430-1356-4d02-9e26-e1cf85f7d040`
- The same invocation contains the provider investigation, local diagnosis, proposal, and exact native HITL wait.

## Observed native tool sequence

The persisted ADK `events` trace for the run/session shows the following calls in the same invocation, in order. Tool-call IDs are included for direct correlation:

1. `get_service_dependencies` — `call_141565`
2. `get_external_dependency_status` — `call_123166`
3. `get_device` — `call_173261`
4. `get_site_health` — `call_175623`
5. `run_diagnostic` — `call_80432`
6. `search_kb` — `call_173527`
7. `propose_field_visit` — `call_213438`
8. `await_human_decision` — `call_139942`

The provider investigation preceded all local/device diagnostic calls. Product evidence and independent local evidence establish the domain switch: AcmePay was HEALTHY, while the affected access link was operationally DOWN and its site/network/payment service plus healthy peer remained healthy. Provider health is treated only as disconfirmation of the provider-outage hypothesis, not as proof of the local root cause.

## Product evidence

| Evidence | ID | Observed result |
| --- | --- | --- |
| `SERVICE_DEPENDENCY_MAPPING` | `EVIDENCE-8251e20e01ff4b06a8e42c8d3cf4bd5f` | `payment_gateway` maps to `DEP-ACMEPAY-PAYMENTS` |
| `EXTERNAL_DEPENDENCY_STATUS` | `EVIDENCE-1af783ad7a594c099c0fb760e7ff1679` | AcmePay `HEALTHY` |
| `CMDB_SNAPSHOT` | `EVIDENCE-ff245ec764f6460bb58141fa3fae75e1` | `POS-KZN17-02`, `SITE-KZN-017`, `ATT-KZN17-POS02`, `SW-KZN17-01`, `Gi1/0/18` |
| `SITE_HEALTH` | `EVIDENCE-79b34912c04c440fac92d08236c054b9` | Site and payment service healthy; peer `POS-KZN17-01` reachable; affected terminal unreachable |
| `ACCESS_LINK_DIAGNOSTIC` | `EVIDENCE-34ddf1e1fd19481e850d40ca88604d47` | Expected configuration, admin UP, operational DOWN, security NORMAL, switch reachable |
| approved `KB_ARTICLE` | `EVIDENCE-d45e700fac404dfcaa71dc06e25f933b` | `KB-LOCAL-LINK` |

The local evidence independently supports `LOCAL_ACCESS_LINK_FAILURE` and `ONSITE_FIELD_VISIT`.

## Proposal, HITL, approval, and execution

- Proposal: `PROPOSAL-28765e0e56cf4c18a2a3a32e797d0136`
- Diagnosis/action: `LOCAL_ACCESS_LINK_FAILURE` / `ONSITE_FIELD_VISIT`
- Initial state: `PENDING_APPROVAL`; the run paused at `WAITING_APPROVAL`.
- Native ADK wait: exact function `await_human_decision`, call ID `call_139942`; matching function response is persisted in the same invocation.
- Approval: `APPROVAL-33dfa054a4f44b3982796446b1c6a4aa` (`APPROVED`)
- Executed action: `ACTION-dae30a34cfe54358b3bb4e8386a2c1be`
- Field Service work order: `WORKORDER-0a4ce5a8e3814b299b859cf7b79b36df`
- Work order targets `SITE-KZN-017`, `ATT-KZN17-POS02`, `SW-KZN17-01`, port `Gi1/0/18`.
- Resume response: `resumed`; same invocation `e-4285c430-1356-4d02-9e26-e1cf85f7d040`, same function call `call_139942`, `retryable=false`.

## Product event sequence

| Seq | Event ID | Event | Result |
| ---: | --- | --- | --- |
| 12 | `EVENT-80bc6ac8151b46179cea726e1f13c0ae` | `approval.decided` | Approved; proposal became `EXECUTED` |
| 13 | `EVENT-fc21dacd37fe42f68e5825a650abf266` | `action.executed` | Exactly one `ACTION-dae30a34cfe54358b3bb4e8386a2c1be` and one work order; incident `ESCALATED` |
| 14 | `EVENT-ab6de7747ae94f0c9c71791e1a72ee1` | `run.status_changed` | Cause `approval_executed`; previous state `WAITING_APPROVAL`; lifecycle resumed as `ACTIVE` while field work is outstanding |

## Idempotent replay and final cardinality

Repeating the identical Approve request returned `replayed=true`; resume returned `already_resumed`. The existing approval, action, work order, invocation, and call IDs were returned. Replay created no additional approval, action, work order, native function response, session, or invocation.

Final records for the run: **1 proposal, 1 approval, 1 executed action, 1 Field Service work order**.

## Quota handling and conclusion

Two earlier fresh runs stopped on Gemini HTTP 429 rate limits. They were not treated as product failures. After waiting for the provider quota window, a third fresh run completed the full acceptance, including approval, same-invocation resume, and idempotent replay.

**Phase 8E — PASS.** The managed Gemini + Google ADK run produced an observable evidence-driven domain switch, local diagnosis, exact native HITL pause, human approval, exactly-once execution, same-invocation resume, and idempotent replay. No production code changes were required.
