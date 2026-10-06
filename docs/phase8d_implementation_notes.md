# Phase 8D implementation notes — deterministic Scenario 3 acceptance

**Status:** DONE / PASS  
**Date:** 6 October 2026  
**Branch:** `phase-8d-scenario3-ui`  
**Reviewed code checkpoint:** `ebb84fe6da3b4003bbe20888f7d014c0d9bf7e7a`  
**Deterministic CI:** `37511797425` — SUCCESS

## Implemented

Phase 8D completes deterministic Scenario 3 verification on top of the Phase
8C1/8C2 Product and native-ADK foundation.

Minimal frontend exposure:

- Scenario 1 / Scenario 3 selector in the existing launch card;
- `POST /api/v1/scenario-3/runs` via `startScenario3()`;
- Scenario 3 readiness uses the existing Product health flags;
- both scenarios reuse the same `/runs/{run_id}` console;
- console title and header derive scenario identity from persisted
  `state.run.scenario_id`;
- no separate Scenario 3 console or browser-side ADK orchestration.

The current Product health metadata is now:

- `phase = 8`
- `checkpoint = 8D`

Historical Phase 6 tests no longer own the current global checkpoint; they
verify only their own ADK capability contracts.

## Deterministic Scenario 3 E2E

Added `tests/test_phase8d_scenario3_e2e.py` using:

- real PostgreSQL Product persistence;
- real Scenario 3 provider/local Product services and validators;
- real native ADK runtime/session persistence;
- a scripted/model-double LLM only for deterministic tool selection;
- no Gemini/network dependency.

The canonical trace proves, in one native invocation:

1. `get_service_dependencies(payment_gateway)`;
2. persisted `SERVICE_DEPENDENCY_MAPPING` establishing AcmePay;
3. `get_external_dependency_status(DEP-ACMEPAY-PAYMENTS)`;
4. persisted authoritative `EXTERNAL_DEPENDENCY_STATUS = HEALTHY`;
5. only then local/device investigation;
6. CMDB topology for `POS-KZN17-02`;
7. healthy site/peer context;
8. access-link `OperationalState.DOWN`;
9. approved KB evidence;
10. `LOCAL_ACCESS_LINK_FAILURE` Field Service proposal using the four local
    Evidence classes only;
11. exact native `await_human_decision` correlation for the same proposal;
12. same Product Run, ADK Session and native invocation throughout.

The test injects a hidden-thought marker into the scripted model response and
asserts that it never enters Product Run/Evidence/event state.

## Decision/recovery coverage

Deterministic tests cover:

- Approve -> exactly one ExecutedAction + one FieldServiceWorkOrder;
- replay -> same Approval/action/work order, no duplicates;
- Reject -> decision persisted, zero execution/work order;
- stale Approve after source truth `DOWN -> UP` -> proposal STALE, zero
  execution/work order, native invocation resumes;
- restart/redelivery -> the first runtime is closed, a fresh
  `DatabaseSessionService` and Runner are created over the same PostgreSQL,
  the same event recovers the same native invocation/HITL pause, and resume
  continues that invocation.

## Frontend coverage

Added:

- real API-client test for Scenario 3 start + tenant header;
- Phase 8D UI contract tests for Scenario 3 selection/readiness;
- proof that the shared run console derives scenario identity from Product
  state and contains no browser agent-invoke path.

## Verification

Exact-head GitHub Actions run `37511797425` on
`ebb84fe6da3b4003bbe20888f7d014c0d9bf7e7a`:

- Phase 8C1 focused regression: **5 passed**;
- Phase 8C2 focused regression: **8 passed**;
- Phase 8D deterministic E2E: **5 passed**;
- Alembic: `20261006_0006 (head)`;
- `alembic check`: **No new upgrade operations detected**;
- full Python regression: **213 passed**;
- retained historical Node regression: **5 passed**;
- frontend tests: **46 passed**;
- frontend typecheck: PASS;
- frontend lint: PASS;
- frontend production build: PASS;
- source/bundle public-env audit: PASS;
- Product Docker build: PASS.

## Review result

The Phase 8D review did not uncover a new Scenario 3 production-logic defect.

One test-ownership issue was corrected: historical Phase 6 tests had brittle
assertions for the current global `phase/checkpoint`. Current checkpoint
ownership now belongs to Phase 8D coverage.

No new worker, outbox topic, runtime framework, Product business table,
Product-side replanning rule or provider-health proposal prerequisite was
introduced.

## Current stop point

> Phase 8C1 — DONE / PASS  
> Phase 8C2 — DONE / PASS  
> **Phase 8D — DONE / PASS**  
> **Phase 8E — NEXT: managed live acceptance with real Gemini + ADK + PostgreSQL**
