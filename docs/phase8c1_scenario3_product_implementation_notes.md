# Phase 8C1 implementation notes

Status: **PASS — Scenario 3 Product foundation and provider reads are implemented
and deterministically verified.**

Baseline:

- Phase 7E live-accepted code: `2f8dae61c06afd0f134c58e90aba0591a013a31e`
- branch: `phase-8c1-scenario3-product`
- verified code SHA: `e9d7fcc8ed2adc523d213cd14b9d89369615df29`
- GitHub Actions: run `37485523359` — success

## Scope implemented

Phase 8C1 deliberately implements only the Product-owned half of Scenario 3.
There is no Scenario 3 Gemini/ADK composition yet; that remains Phase 8C2.

Scenario 3 reuses the existing device-incident Product model and Scenario 1 local
fixture instead of adding parallel tables or a second lifecycle framework.

`POST /api/v1/scenario-3/runs` now creates:

- one persisted `scenario-3` Run;
- one real device Incident for `POS-KZN17-02` at `SITE-KZN-017`;
- `simulation.started`, `external.signal`, and `run.status_changed` events;
- one durable outbox envelope on the existing
  `agent.dispatch.operational-event` topic.

The initial safe Product signal persists only the provider-context identifiers
needed later by the model:

- `service_key=payment_gateway`;
- `symptom_key=payment_gateway_timeout`.

No dependency status, root cause, diagnosis, switch/port answer, action, or replan
conclusion is pre-seeded into the initial event.

## Bootstrap compatibility

The historical `Scenario1Bootstrap` contract gained two optional fields:

- `service_key`;
- `symptom_key`.

They must be provided together when used. Scenario 1 leaves both unset, so its
persisted signal shape and lifecycle remain unchanged. Scenario 3 supplies both.

`Scenario1RunStartService` remains the single device-incident start service; it
is not duplicated for Scenario 3.

## Provider-domain reads

New `Scenario3ProviderReadService` reuses the existing provider-domain request,
result, source-port, snapshot, and Evidence contracts. It does **not** modify or
route through `Scenario2ReadToolService`.

The deterministic Scenario 3 source truth is:

- service: `payment_gateway`;
- external dependency: `DEP-ACMEPAY-PAYMENTS` / `AcmePay`;
- provider state: `HEALTHY`;
- status detail: `operating_normally`.

The adapter returns observations only. It contains no conclusion such as
"provider healthy => terminal fault" and no hard-coded replan.

Context is fail-closed:

1. `get_service_dependencies(service_key)` is allowed only when that service key
   is established by the same Run's persisted initial `external.signal`;
2. the read persists typed `SERVICE_DEPENDENCY_MAPPING` Evidence;
3. `get_external_dependency_status(dependency_id)` is allowed only after that
   exact dependency ID has been established by same-Run mapping Evidence;
4. the status read persists typed `EXTERNAL_DEPENDENCY_STATUS` Evidence with a
   freshness TTL.

Wrong tenant, wrong Run, unknown service, status-before-mapping, and unknown
dependency are rejected.

## Transitional dispatch safety

The Phase 8C1 Product start must persist the generic outbox envelope even though
Scenario 3 native runtime routing is intentionally deferred to Phase 8C2.

A review found that the pre-existing Scenario 1 worker consumes that same topic.
Without a guard, a Gemini-enabled deployment could claim a Scenario 3 envelope
and incorrectly invoke Scenario 1 semantics.

Phase 8C1 therefore adds only a fail-closed transitional guard:

- Scenario 1 envelopes still invoke Scenario 1 runtime normally;
- a non-`scenario-1` envelope is not delivered to Scenario 1 runtime;
- it is rescheduled and remains undelivered/recoverable for Phase 8C2 routing.

This is **not** the Phase 8C2 router. No Scenario 3 runtime, tool composition, or
model invocation has been added here.

## Persistence and schema

No Product business table or migration was added.

Verified schema state:

- Alembic head remains `20261006_0006`;
- `alembic check`: `No new upgrade operations detected.`

Scenario 3 provider context is grounded in existing persisted application events
and typed Evidence.

## Verification

Final code gate before this documentation commit:

- focused Phase 8C1 tests: **4 passed**;
- Alembic upgrade/current/check: PASS, no schema delta;
- full Python regression: **199 passed**;
- retained historical Node regression: PASS;
- frontend typecheck: PASS;
- frontend lint: PASS;
- frontend tests: **42 passed**;
- frontend production build: PASS;
- Product Docker image build: PASS.

During the first full regression, the historical public-route allowlist correctly
failed because it did not yet include the intentional
`/api/v1/scenario-3/runs` endpoint. The allowlist was updated; no hidden seed or
acceptance endpoint was made public.

## Explicitly deferred

Not implemented in Phase 8C1:

- Scenario 3 native ADK agent/runtime;
- Scenario 3 model-visible tool composition;
- scenario-aware generic-topic runtime routing to Scenario 3;
- native Scenario 3 multi-step reasoning/replan behavior;
- live Gemini acceptance;
- frontend Scenario 3 demo flow.

Next: **Phase 8C2 — native Scenario 3 ADK composition and scenario-aware dispatch
routing on the existing generic device-incident topic.**
