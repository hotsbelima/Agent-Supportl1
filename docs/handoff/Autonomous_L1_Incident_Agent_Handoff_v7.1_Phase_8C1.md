# Autonomous L1 Incident Agent — cumulative handoff v7.1

Updated after **Phase 8C1 PASS**.

This document supersedes the Phase 8C1 execution state in
`Autonomous_L1_Incident_Agent_Handoff_v7.0_Phase_8AB.md`. The Phase 8A/8B
Scenario 3 design remains authoritative except where this file records the now
implemented 8C1 result.

## Current exact checkpoint

- Last live-managed acceptance baseline before Scenario 3:
  `2f8dae61c06afd0f134c58e90aba0591a013a31e`
- Phase 8C1 branch: `phase-8c1-scenario3-product`
- Phase 8C1 verified code SHA: `e9d7fcc8ed2adc523d213cd14b9d89369615df29`
- Phase 8C1 CI: GitHub Actions run `37485523359` — **success**
- Alembic head: `20261006_0006`
- Current roadmap position: **8C1 DONE / 8C2 NEXT**

Do not describe Scenario 3 as end-to-end or live-accepted yet. No Scenario 3
Gemini/ADK invocation exists at this checkpoint.

## Retained architecture invariants

Product remains the source of truth for business/operational state, evidence,
application events, durable outbox, proposals, approvals, and actions.

Google ADK remains the owner of native agent execution, Session/Event history,
tool-call lifecycle, and native HITL wait/resume.

Do not add:

- a second generic agent loop;
- a second custom session framework;
- frontend orchestration of model/tool steps;
- hidden root-cause or final-action truth in the Scenario 3 initial signal;
- a third dispatch topic/worker merely for Scenario 3;
- Scenario 3 business tables unless a later requirement proves they are needed.

Scenario 2 remains isolated on its already implemented Scenario 2 path. Do not
rewrite `Scenario2ReadToolService` to make Scenario 3 fit.

## Scenario 3 canonical Product facts

Scenario ID: `scenario-3`.

Initial incident context:

- incident: `INC-S3-KZN-001`;
- site: `SITE-KZN-017`;
- affected device: `POS-KZN17-02`;
- service key: `payment_gateway`;
- symptom key: `payment_gateway_timeout`.

Provider truth exposed only through provider reads:

- dependency ID: `DEP-ACMEPAY-PAYMENTS`;
- dependency name: `AcmePay`;
- provider state: `HEALTHY`;
- detail: `operating_normally`.

Local physical truth is intentionally the same Scenario 1 world and is reached
through the existing local/device tools rather than being copied into the
initial signal.

## Phase 8C1 — DONE

### Product bootstrap/API

Public endpoint:

`POST /api/v1/scenario-3/runs`

It reuses the existing device-incident Run/Incident lifecycle. The initial
`external.signal` now supports optional safe provider-context identifiers
`service_key` and `symptom_key`. Scenario 1 leaves those fields unset.

The start transaction persists the Run, Incident, events, and one outbox record
on the existing `AGENT_DISPATCH_TOPIC`.

No schema change was required.

### Provider reads and Evidence

`Scenario3ProviderReadService` provides the Product application boundary for:

- service -> dependency mapping;
- external dependency status.

Authorization/grounding order is mandatory:

1. service must be established by the same Run's persisted initial signal;
2. dependency mapping is observed and persisted as
   `SERVICE_DEPENDENCY_MAPPING` Evidence;
3. provider status may be read only for a dependency established by same-Run
   mapping Evidence;
4. provider state is persisted as `EXTERNAL_DEPENDENCY_STATUS` Evidence.

The source adapter returns provider observations only. It does not encode the
model's hypothesis change or final diagnosis.

### Transitional worker safety

Because Scenario 1 and Scenario 3 intentionally share the generic
`agent.dispatch.operational-event` topic, Phase 8C1 adds a temporary fail-closed
guard to `Scenario1DispatchWorker`.

Until 8C2:

- Scenario 1 still dispatches normally;
- Scenario 3 envelopes are never passed to Scenario 1 runtime;
- those envelopes remain durable and retryable, not marked delivered.

This guard must be replaced/generalized by the 8C2 scenario-aware router; do not
create a separate Scenario 3 topic as a shortcut.

### Verification evidence

Final verified code SHA: `e9d7fcc8ed2adc523d213cd14b9d89369615df29`.

GitHub Actions run: `37485523359`.

Results:

- focused 8C1: 4 passed;
- Alembic clean, no new operations;
- full Python: 199 passed;
- Node regression: PASS;
- frontend typecheck/lint/build: PASS;
- frontend: 42 tests passed;
- Product Docker build: PASS.

## Phase 8C2 — NEXT

Implement only the agent-dependent half now that Product grounding exists.

Required direction:

1. Build Scenario 3 native ADK composition by reusing the existing Scenario 1
   device-incident tool/HITL architecture plus the new Scenario 3 provider-read
   Product service. Do not fork generic runtime/session infrastructure.
2. Generalize the existing generic-topic dispatch path by **persisted
   `scenario_id`** so `scenario-1` reaches Scenario 1 runtime and
   `scenario-3` reaches Scenario 3 runtime. Preserve one durable topic and one
   device-incident dispatch mechanism.
3. Preserve one native persistent ADK Session per Run and the existing
   event-identity/redelivery guarantees.
4. Keep trusted `tenant_id` / `run_id` out of model-visible arguments.
5. The model must discover provider mapping/status through tools. The fact that
   AcmePay is healthy must disconfirm an upstream-provider hypothesis; the code
   must not hard-code the pivot or final local diagnosis.
6. Reuse the existing local/device Evidence path and existing field-visit
   proposal/HITL semantics. Any dangerous action remains Product-owned and
   approval-gated.
7. Add deterministic native-ADK tests proving the Scenario 3 tool surface,
   trusted context, sequential tool use, no Scenario 1 cross-routing, durable
   session/event correlation, and a real proposal wait point when the model/tool
   sequence reaches that state.
8. Do not call Phase 8C2 PASS merely because unit tests compile. Record exact
   branch/SHA and full regression evidence in implementation notes before moving
   to the later managed/live acceptance phase defined by the Scenario 3 roadmap.

### 8C2 stop condition

Stop after deterministic 8C2 implementation/verification and update this handoff
again. Do not silently roll managed/live Scenario 3 acceptance into 8C2 unless
the roadmap explicitly assigns it there.

## Files introduced/changed in 8C1

Core implementation:

- `product_backend/contracts/run_state.py`
- `product_backend/application/run_lifecycle.py`
- `product_backend/application/scenario3_read_tools.py`
- `product_api/scenario3_fixture.py`
- `product_api/app.py`
- `product_api/dispatch.py`

Verification:

- `tests/test_phase8c1_scenario3_product.py`
- `tests/test_phase5d1_release_candidate.py`
- `.github/workflows/phase8c1-scenario3-product.yml`

Detailed implementation record:

- `docs/phase8c1_scenario3_product_implementation_notes.md`
