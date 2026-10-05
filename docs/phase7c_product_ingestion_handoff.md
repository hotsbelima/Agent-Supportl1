# Phase 7C Product ingestion — handoff to ADK implementer

This checkpoint intentionally implements the **agent-free Product half of 7C**.
It must not be described as full Phase 7C PASS until the ADK continuity work below
is completed and live-tested.

## Baseline

- Parent checkpoint: Phase 7B PASS.
- Parent exact commit: `a7e83f04c1cd5ac419bbe032c0c1c254ac763854`.
- Working branch: `phase-7c-product-ingestion`.

## What is already implemented

### Product run and state

`POST /api/v1/scenario-2/runs`

Creates one `scenario-2` Run in `ACTIVE`, a persisted deterministic fixture-state
row, and a `simulation.started` Product audit event.

Scenario 2 Product state is available through:

`GET /api/v1/scenario-2/runs/{run_id}`

The state contains:

- Run;
- typed `ServiceIncident` records;
- typed persisted `OperationalSignal` facts;
- persisted Scenario 2 fixture state;
- latest Product application-event sequence.

No ADK state is required for this read model.

### Typed ingestion

`POST /api/v1/scenario-2/runs/{run_id}/signals`

The caller supplies source/site/service/symptom/source reference and a safe JSON
payload. Product assigns `received_at` from the server UTC clock. The API does not
accept a caller-controlled received timestamp.

Each first delivery atomically:

1. locks the owning Run;
2. creates/reuses one site/service `ServiceIncident`;
3. persists one `OperationalSignal`;
4. appends one safe `external.signal` application event;
5. enqueues one durable outbox record;
6. commits all Product facts together.

Redelivery identity is `(tenant, run, source, source_ref)`.

An identical replay returns the existing persisted signal and creates no second
application event or outbox record. A conflicting replay is rejected.

### Dedicated Scenario 2 dispatch topic

The Product outbox topic is:

`agent.dispatch.scenario2-operational-signal`

Constant:

`SCENARIO2_AGENT_DISPATCH_TOPIC`

The envelope contains only Product identifiers:

- `event_id`;
- `event_seq`;
- `scenario_id=scenario-2`;
- `signal_id`.

**There is deliberately no consumer on this branch.**

The existing Phase 7A Scenario 1 worker consumes only
`agent.dispatch.operational-event`; it must not consume the Scenario 2 topic.

### Canonical simulator

`POST /api/v1/scenario-2/runs/{run_id}/simulator/next`

It emits only the next canonical **fact** from the Phase 7B fixture:

1. KZN monitoring;
2. KZN ITSM ticket;
3. SAM monitoring.

Progress is derived from persisted `(source, source_ref)` identities, so it survives
process restart and also works if a canonical fact arrived through the generic
`/signals` endpoint first.

The simulator contains no correlation conclusion and no threshold such as
`if event_count >= N: propose_major_incident`.

After the first two events only one KZN `ServiceIncident` exists. The SAM fact
creates the second independent site/service incident. Product ingestion itself
creates no Major Incident proposal, execution, or WorkOrder.

### Restart-safe stale fixture controls

Hidden acceptance-only endpoints:

- `POST /api/v1/scenario-2/runs/{run_id}/acceptance/dependency-status`
- `POST /api/v1/scenario-2/runs/{run_id}/acceptance/matching-major-incident`

Fixture state is persisted in PostgreSQL, not process memory.

This supports controlled later acceptance transitions:

- AcmePay `DEGRADED -> HEALTHY`;
- matching Major Incident appears/disappears.

`PersistedScenario2FixtureSources` is already available as the provider-neutral
source adapter for future Scenario 2 tools. It reads this persisted fixture state.

## PostgreSQL schema added

Migration:

`20261006_0005_phase7c_fixture_state.py`

Adds `scenario2_fixture_states`.

The Phase 7B tables remain the Product sources of truth for:

- `service_incidents`;
- `operational_signals`.

## Explicit remaining ADK work

The next implementer owns the **agent-dependent half of 7C**.

### 1. Add a Scenario 2 durable outbox consumer

Consume only:

`SCENARIO2_AGENT_DISPATCH_TOPIC`

Do not route these records through `Scenario1AgentRuntime`.

For each outbox row:

1. load the persisted Product event/signal;
2. ensure/get one persistent native ADK Session for
   `(tenant_id, run_id)`;
3. invoke the Scenario 2 agent exactly once for that Product event identity;
4. mark the outbox row delivered only after the native ADK invocation reaches a
   recoverable persisted point;
5. use durable redelivery + ADK history correlation for crash recovery.

### 2. One Run must map to one persistent ADK Session

Required proof:

- event 1 -> invocation 1;
- event 2 -> invocation 2 in the **same Session**;
- event 3 -> invocation 3 in the **same Session**;
- process/service reconstruction between events preserves Product facts and Session
  continuity.

Do not concatenate all three facts into one prompt.

### 3. Preserve Product/ADK ownership

Product owns:

- operational signals;
- ServiceIncidents;
- application events;
- outbox;
- fixture/source truth;
- later Major Incident proposal/approval/execution business state.

ADK owns:

- Session;
- invocation lifecycle;
- model conversation/runtime history;
- later native wait/resume.

Do not create a second generic agent loop or a second custom session framework.

### 4. No premature escalation

After event 1 and after event 2, the agent must not create a Major Incident proposal
from event count/order.

The SAM event may cause the model to investigate a common dependency, but final
correlation still has to come from persisted facts + Scenario 2 tool evidence.

Full Scenario 2 model-visible tools and HITL belong to Phase 7D. Reuse the contracts
already defined in:

- `product_backend/contracts/scenario2_tools.py`;
- `product_backend/ports/scenario2_sources.py`;
- `product_api/scenario2_sources.py`.

### 5. Health/readiness

Current health intentionally reports:

- `scenario2_checkpoint = 7C-product-ingestion`;
- `scenario2_ingestion_wired = true`;
- `scenario2_dispatch_consumer_wired = false`.

Only set the last field true when a real durable Scenario 2 ADK consumer is running.

## What not to do

- Do not make `simulator/next` invoke Gemini directly.
- Do not let frontend orchestrate ADK calls.
- Do not use Scenario 1 field-visit tools as fake Scenario 2 tools.
- Do not fabricate `device_id`, diagnosis or WorkOrder.
- Do not hard-code the correlation conclusion in the ingestion backend.
- Do not use process-memory fixture mutations for stale acceptance.
- Do not merge all incoming events into one giant prompt.

## Acceptance still required before full 7C PASS

At minimum:

- sequential events create separate ADK invocations;
- all invocations use the same persistent Session;
- first/same-site events do not prematurely escalate;
- process restart between events preserves Product and ADK state;
- outbox redelivery is idempotent;
- no duplicate independent agent invocation for one Product event.
