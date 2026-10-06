# Autonomous L1 Incident Agent — cumulative handoff v7.5 (Phase 8E + CI cleanup)

**Updated:** 2026-10-06  
**Repository:** `hotsbelima/Agent-Supportl1`  
**Live-validated branch:** `phase-8d-scenario3-ui`  
**Live-validated deployed head:** `7232df9554aa15037a52a4051d5ae9939eb5799a`  
**Live code checkpoint:** `ebb84fe6da3b4003bbe20888f7d014c0d9bf7e7a`  
**Post-8E CI-cleanup checkpoint:** `978cfc9d5bdb557a2bdf4fc2d4642970be07f9f3`

This handoff carries forward the completed Phase 8D record in [Autonomous_L1_Incident_Agent_Handoff_v7.3_Phase_8D.md](Autonomous_L1_Incident_Agent_Handoff_v7.3_Phase_8D.md), the Phase 8E managed live acceptance recorded in v7.4, and the post-8E CI-hygiene cleanup. Historical handoffs remain unchanged.

## Cumulative phase status

- Phase 8C1 — DONE / PASS
- Phase 8C2 — DONE / PASS
- Phase 8D — DONE / PASS
- Phase 8E — DONE / LIVE PASS
- Phase 8 / Scenario 3 — COMPLETE
- Next stage — Phase 9

## Phase 8E live deployment and CI

- GitHub Actions: [run 37512371216](https://github.com/hotsbelima/Agent-Supportl1/actions/runs/37512371216) — SUCCESS
- Northflank deployment/build: `offbeat-belief-6823`
- Managed Product API: <https://p01--product-api--yxz5y8myjdln.code.run/>
- Service `product-api`, pod `product-api-d8585bb94-l2ftt`: Running, 1/1 passing
- Managed PostgreSQL reachable; Alembic head: `20261006_0006`
- Gemini configured in the managed deployment: `gemini-3.5-flash-lite`; native Google ADK session persistence and resume were observed.
- No production code was changed for Phase 8E.

## Phase 8E canonical run and identity chain

- Run: `RUN-126e81e8badd4ab39ffe6f93a2618009`
- Incident: `INC-S3-KZN-001`
- ADK session: `RUN-126e81e8badd4ab39ffe6f93a2618009` (`session_id == run_id`)
- Native invocation: `e-4285c430-1356-4d02-9e26-e1cf85f7d040`
- Proposal: `PROPOSAL-28765e0e56cf4c18a2a3a32e797d0136`
- HITL call: `await_human_decision`, `call_139942`
- Approval: `APPROVAL-33dfa054a4f44b3982796446b1c6a4aa`
- Executed action: `ACTION-dae30a34cfe54358b3bb4e8386a2c1be`
- Field Service work order: `WORKORDER-0a4ce5a8e3814b299b859cf7b79b36df`

## Observable live replanning trace

All eight model-visible Scenario 3 tools were observed in order in the persisted ADK event history for the same invocation:

`get_service_dependencies` (`call_141565`) → `get_external_dependency_status` (`call_123166`) → `get_device` (`call_173261`) → `get_site_health` (`call_175623`) → `run_diagnostic` (`call_80432`) → `search_kb` (`call_173527`) → `propose_field_visit` (`call_213438`) → `await_human_decision` (`call_139942`).

The product recorded provider mapping Evidence `EVIDENCE-8251e20e01ff4b06a8e42c8d3cf4bd5f`, then AcmePay `HEALTHY` Evidence `EVIDENCE-1af783ad7a594c099c0fb760e7ff1679`. Local/device investigation followed the provider result. The local evidence was:

- CMDB: `EVIDENCE-ff245ec764f6460bb58141fa3fae75e1`
- Site health: `EVIDENCE-79b34912c04c440fac92d08236c054b9`
- Access-link diagnostics: `EVIDENCE-34ddf1e1fd19481e850d40ca88604d47`
- Approved knowledge article: `EVIDENCE-d45e700fac404dfcaa71dc06e25f933b`

AcmePay being healthy only disconfirmed the provider-outage hypothesis. The local evidence independently established `LOCAL_ACCESS_LINK_FAILURE` at `POS-KZN17-02` (`SITE-KZN-017`), with `OperationalState.DOWN` at attachment `ATT-KZN17-POS02`, switch `SW-KZN17-01`, port `Gi1/0/18`. The agent proposed one `ONSITE_FIELD_VISIT` and paused on the exact native `await_human_decision` call for that proposal.

## Approval, resume, and replay

The authorized generic Field Service Approve endpoint persisted Approval `APPROVAL-33dfa054a4f44b3982796446b1c6a4aa`, revalidated the proposal, executed one action, and created one work order. Resume returned `resumed` for the same invocation and call ID, with `retryable=false`; it did not create another session or independent invocation.

Replaying the identical approval request returned `replayed=true` and `already_resumed`. The counts remained exactly one proposal, one approval, one executed action, and one work order; no duplicate native FunctionResponse was created.

Product events:

| Seq | Event ID | Type | Outcome |
| ---: | --- | --- | --- |
| 12 | `EVENT-80bc6ac8151b46179cea726e1f13c0ae` | `approval.decided` | Approved; proposal `EXECUTED` |
| 13 | `EVENT-fc21dacd37fe42f68e5825a650abf266` | `action.executed` | One action and work order; incident `ESCALATED` |
| 14 | `EVENT-ab6de7747ae94f0c9c71791e1a72ee1` | `run.status_changed` | Approval-executed lifecycle resumed to `ACTIVE` while onsite work is outstanding |

## Result and detailed evidence

**Phase 8E — DONE / LIVE PASS.** Managed live evidence proves provider-first investigation, evidence-driven domain switch, independent local diagnosis, native HITL, approval, exactly-once execution, same-invocation resume, and idempotent replay. Two earlier fresh runs hit Gemini 429 quota limits; after waiting, a new run completed successfully. No source fix was needed.

Detailed acceptance evidence is recorded in [Autonomous_L1_Incident_Agent_Phase_8E_Acceptance.md](Autonomous_L1_Incident_Agent_Phase_8E_Acceptance.md).

## Post-8E CI hygiene cleanup

After the Phase 8E documentation PR was opened, two historical PR checks exposed CI ownership issues. Neither issue was a Phase 8 product defect and no production code changed.

### Phase 7A current-checkpoint ownership

Historical script `scripts/phase7a_live_acceptance.py` still asserted:

`health_body["checkpoint"] == "7A"`

That assertion was invalid once later phases advanced the repository-wide health checkpoint to `8D`.

The script now verifies only the Phase 7A capabilities it actually owns:

- Gemini configured;
- ADK wired;
- persistent ADK session support;
- ADK resumability;
- automatic dispatch.

It no longer owns or constrains the repository's current global `phase/checkpoint`.

Validation:

- workflow: **Phase 7A event dispatch and operational UI**
- run: `37526236508`
- result: **SUCCESS**
- focused/deterministic/build checks: PASS
- isolated live database setup: **skipped on pull_request**
- isolated live migrations: **skipped on pull_request**
- live Gemini automatic-dispatch acceptance: **skipped on pull_request**

The live Phase 7A acceptance remains available on its historical phase-branch push and through `workflow_dispatch`.

### Historical quota-dependent Gemini PR gate

The historical Phase 6B workflow previously ran three real Gemini calls on every pull request. The Phase 8E documentation PR therefore failed with Gemini `429 RESOURCE_EXHAUSTED` even though all deterministic tests and builds had passed.

The Phase 6B live Gemini step now has:

`if: github.event_name != 'pull_request'`

Therefore pull requests retain the deterministic Phase 6B tests, full regression, frontend checks, static audit and Docker build, but an external free-tier quota cannot turn an unrelated PR red.

Validation:

- workflow: **Phase 6B native six-tool ADK**
- run: `37526236595`
- result: **SUCCESS**
- focused Phase 6B tests: PASS
- full deterministic/build regression: PASS
- live Gemini acceptance: **skipped on pull_request**

For the same reason, the historical Phase 7A live-only setup/migration/Gemini steps are also excluded from pull-request gating. They remain available on the historical branch and through manual workflow dispatch.

### Scope of cleanup

Changed files only:

- `scripts/phase7a_live_acceptance.py`
- `.github/workflows/phase6b-native-adk.yml`
- `.github/workflows/phase7a-event-dispatch-ui.yml`

No Product API, domain, persistence, runtime, Scenario 3, ADK business integration or frontend production code changed.

The **live-validated product SHA remains**
`7232df9554aa15037a52a4051d5ae9939eb5799a`.

The cleanup does not replace or invalidate the Phase 8E live evidence. It only makes historical CI ownership match the project's current phase structure.

## Next stage

Phase 8 / Scenario 3 is complete and the post-8E historical CI cleanup is validated. Proceed to Phase 9 using the Phase 8D and Phase 8E evidence above; do not infer any new implementation scope from this handoff alone.
