# Phase 8C1 implementation notes

Status: **PASS — Product foundation and Scenario 3 provider reads implemented and deterministically verified.**

Base:
- final Phase 7 / Phase 8 design baseline: `2f8dae61c06afd0f134c58e90aba0591a013a31e`
- branch: `phase-8c1-scenario3-provider-reads`
- reviewed implementation checkpoint: `ceccf0f59950105e71fb35435118d3a26b473497`
- deterministic GitHub Actions run: `37491364260` — **SUCCESS**

## Scope implemented

Phase 8C1 implements only the Product/provider foundation required by the reviewed
Phase 8 plan. It does **not** add the native Scenario 3 ADK agent/runtime routing
owned by Phase 8C2.

Implemented:

- the historical device-Incident bootstrap contract now supports optional
  `service_key` and `symptom_key`;
- Scenario 1 leaves those fields unset and retains its prior signal shape;
- canonical Scenario 3 bootstrap persists:
  - `scenario_id = scenario-3`
  - `INC-S3-KZN-001`
  - `SITE-KZN-017`
  - `POS-KZN17-02`
  - `service_key = payment_gateway`
  - `symptom_key = payment_gateway_timeout`;
- `POST /api/v1/scenario-3/runs` creates one real device Incident through the
  existing atomic Run/Incident/event/outbox start transaction;
- Scenario 3 reuses the existing
  `AGENT_DISPATCH_TOPIC = agent.dispatch.operational-event`;
- the initial safe Product signal does not expose AcmePay status, dependency
  root cause, local topology, final diagnosis, action recommendation or any
  precomputed replanning flag;
- a deterministic Scenario 3 provider source exposes only source observations:
  `payment_gateway -> DEP-ACMEPAY-PAYMENTS -> AcmePay -> EXTERNAL_PROVIDER`
  and authoritative `AcmePay = HEALTHY`;
- a narrow Scenario 3 provider-read application service persists
  `SERVICE_DEPENDENCY_MAPPING` and `EXTERNAL_DEPENDENCY_STATUS` Evidence.

## Provider context guardrails

Provider reads are bound to persisted Product facts, not arbitrary model input.

`get_service_dependencies` accepts only the `service_key` already persisted in
that same Scenario 3 Run's initial `EXTERNAL_SIGNAL`.

`get_external_dependency_status` accepts a dependency only after the same Run
has persisted `SERVICE_DEPENDENCY_MAPPING` Evidence establishing that exact
dependency ID for the persisted service context.

This makes unknown service/dependency enumeration fail closed and preserves
tenant/run isolation.

No Product-side replanning rule was added. In particular, there is no branch
equivalent to:

`if provider_status == HEALTHY: run_local_diagnostics()`

The provider adapter returns facts only; interpretation and later tool choice
remain an agent/runtime concern for Phase 8C2+.

## Persistence and schema

No Scenario 3 table or migration was added.

Existing Product-owned entities are reused:

- `runs`
- `incidents`
- `evidence`
- `application_events`
- `application_outbox`

Alembic remains:

`20261006_0006 (head)`

with a clean autogenerate check.

## Deliberately not implemented in 8C1

The following remain Phase 8C2 scope:

- Scenario 3 ADK tool wrappers;
- Scenario 3 agent instruction/composition;
- shared/parameterized device-Incident runtime;
- worker runtime selection by persisted `scenario_id`;
- human-decision runtime routing;
- field-visit proposal/native-wait correlation hardening.

A third durable worker or dedicated Scenario 3 topic was **not** created.

The Scenario 2 read service was **not** loosened or reused as the Scenario 3
provider service.

The existing Field Service proposal validator was **not** given an artificial
provider-health prerequisite.

## Regression issue found and fixed

The first full regression run correctly failed because the historical release
candidate test asserted the complete public Product API path set and did not yet
include the newly intentional `POST /api/v1/scenario-3/runs` endpoint.

The test contract was updated to include that public route. No production
behavior was weakened to make the regression pass.

## Verification

Final deterministic gate on reviewed implementation checkpoint
`ceccf0f59950105e71fb35435118d3a26b473497`:

- focused Phase 8C1 tests: **5 passed**;
- Alembic: **`20261006_0006 (head)`**;
- Alembic autogenerate check: **No new upgrade operations detected**;
- full Python regression: **200 passed**;
- retained historical Node regression: **5 passed**;
- frontend typecheck: PASS;
- frontend lint: PASS;
- frontend tests: **42 passed**;
- frontend production build: PASS;
- public-bundle static audit: PASS;
- Product Docker image build: PASS.

GitHub Actions:
`https://github.com/hotsbelima/Agent-Supportl1/actions/runs/37491364260`

## Post-implementation review hardening

A second review found a real shared-topic boundary defect that the original
focused tests did not cover.

Scenario 3 correctly reused `AGENT_DISPATCH_TOPIC`, but the existing
`Scenario1DispatchWorker` continuously polls that topic. Therefore merely
omitting `wake()` from the Scenario 3 start endpoint was insufficient: with
Gemini configured, the Phase 7 Scenario 1 worker could claim a Scenario 3
envelope before Phase 8C2 runtime routing existed.

Phase 8C1 now fails closed at that boundary. After reloading Product Run state,
the Scenario 1 worker refuses any envelope whose persisted
`run.scenario_id != "scenario-1"`, reschedules it, and does not invoke the
Scenario 1 native runtime. Phase 8C2 remains responsible for replacing this
temporary guard with real Scenario 1/3 runtime selection.

Additional regression coverage now proves:

- a Scenario 3 envelope on the shared topic is never delivered to Scenario 1
  native runtime;
- normal Scenario 1 envelopes may still be delivered by that worker;
- the Scenario 3 envelope stays pending/undelivered for later 8C2 routing;
- dependency Evidence does not authorize another Run even inside the same
  tenant, in addition to cross-tenant isolation.

Next: **Phase 8C2 — Native Scenario 3 composition + runtime routing**.
