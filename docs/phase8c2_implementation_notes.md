# Phase 8C2 implementation notes

Status: **PASS — native Scenario 3 composition, shared device-Incident routing and exact Field Service HITL correlation implemented and deterministically verified.**

Base:
- Phase 8C1 final branch head: `73cfefe0659f5a63c0ab57ae8eec70492a551c0b`
- branch: `phase-8c2-scenario3-native-routing`
- reviewed Phase 8C2 code checkpoint: `9d9d6f2a44b709c6d443e9608e4d3e026ccb0470`
- deterministic GitHub Actions run: `37504606915` — **SUCCESS**

## Scope implemented

Phase 8C2 implements the native Scenario 3/runtime-routing layer defined by the
reviewed Phase 8 handoff. It does not yet implement the full deterministic
Scenario 3 E2E/replanning acceptance owned by Phase 8D and does not perform the
managed real-Gemini acceptance owned by Phase 8E.

### Exact Scenario 3 native tool surface

Added Scenario 3 Product adapter, ADK wrappers and a dedicated Scenario 3
`LlmAgent` definition.

The model-visible surface is exactly:

1. `get_service_dependencies`
2. `get_external_dependency_status`
3. `get_device`
4. `get_site_health`
5. `run_diagnostic`
6. `search_kb`
7. `propose_field_visit`
8. native `await_human_decision`

Explicitly absent:

- `search_incidents`
- `get_local_service_health`
- `search_major_incidents`
- `propose_major_incident`

Trusted `tenant_id` and `run_id` are not model arguments. They are derived
from native ADK `ToolContext`:

- tenant = `tool_context.user_id`
- run = `tool_context.session.id`

### Shared device-Incident runtime

The former Scenario 1 native runtime mechanics were generalized into one
`DeviceIncidentAgentRuntime`.

Scenario 1 is now a thin compatibility configuration over that runtime.

Scenario 3 is also a thin configuration over the same runtime with its own root
agent and scenario identity.

The shared runtime retains:

- the same `ADK_APP_NAME`;
- persistent native ADK Session ownership;
- native resumability;
- Product operational-event correlation;
- redelivery continuation of the same native invocation;
- native long-running human-decision pause/resume.

Session ownership remains:

```text
ADK app_name   = autonomous-l1-incident-agent
ADK user_id    = Product tenant_id
ADK session_id = Product run_id
```

Therefore `session_id == run_id` for Scenario 3 as required.

### Shared durable worker routing

No third worker and no Scenario 3 outbox topic were added.

The existing generic device-Incident worker still consumes:

`AGENT_DISPATCH_TOPIC = "agent.dispatch.operational-event"`

After claiming an envelope it reloads Product Run state and selects the native
runtime only from persisted `Run.scenario_id`:

```text
scenario-1 -> Scenario 1 runtime
scenario-3 -> Scenario 3 runtime
```

Unknown/unconfigured scenarios fail closed and are rescheduled rather than
being delivered into the wrong runtime.

Scenario 3 start now provisions/ensures the same persistent native ADK Session
and wakes the existing shared worker only after Product Run/Incident/event/outbox
truth has committed.

### Exact Field Service native HITL correlation

The shared device-Incident runtime was hardened to the safety invariant already
used for Scenario 2.

A native long-running:

`await_human_decision(PROPOSAL-X)`

is accepted only when the same native invocation has already observed a
successful Product `propose_field_visit` response for exactly
`PROPOSAL-X` with status `PENDING_APPROVAL`.

The runtime rejects:

- a wait without a successful Product proposal in that invocation;
- a wait whose proposal ID does not match the successful Product proposal;
- a Product field-visit proposal that finishes without establishing the exact
  native wait correlation.

A proposal created without the matching native wait therefore cannot be treated
as a safely delivered completed HITL point. Durable dispatch remains retryable.

The shared human-decision correlation lookup was also tightened so a bare
model-supplied proposal ID is insufficient for resume correlation.

### Human-decision runtime routing

The existing generic Field Service Approve/Reject endpoints are retained.

Product commits the human decision and any guarded business side effect first.
Only after that commit the API reloads the persisted Product Run and chooses
the native runtime from `Run.scenario_id`.

Scenario 3 does not receive duplicate decision endpoints.

If native runtime selection or native resume fails after Product commit:

- Product truth remains committed;
- the API returns the committed Product decision;
- native resume remains `deferred` and retryable;
- replaying the same Product decision endpoint remains the reconciliation path.

A dedicated regression test proves that even a post-commit Product Run reload
failure does not turn the already committed decision into an HTTP 500.

## Scenario 3 agent boundary

The Scenario 3 agent instruction encodes the reviewed diagnostic boundaries
without adding Product-side workflow logic:

- investigate the upstream-provider hypothesis using Product tools;
- establish dependency mapping before dependency status;
- authoritative provider `HEALTHY` disconfirms the provider-outage hypothesis;
- provider `HEALTHY` does not prove a local root cause;
- after disconfirmation, the model changes diagnostic domain and uses local
  Product tools;
- Field Service still requires the existing four local Evidence classes;
- provider-health evidence is not an artificial Field Service validator
  prerequisite;
- Product does not implement a branch such as
  `if provider_status == HEALTHY: run_local_diagnostics()`.

Phase 8D still owns deterministic proof of the actual observable provider-first
then local-tool sequence.

## Historical regression adjustment

The first full Phase 8C2 regression exposed one intentionally obsolete synthetic
Phase 7A fixture.

That historical test represented a native human-decision pause with no prior
successful Product proposal response. Such a trace is now intentionally invalid
under the Phase 8C2 safety invariant.

The historical fixture was updated to include:

`successful propose_field_visit(PENDING_APPROVAL) -> exact await_human_decision`

before checking redelivery correlation.

Production behavior was not weakened to preserve the obsolete synthetic trace.

## Post-implementation review correction

A second code-level review found one real Scenario 3 stale-path composition
defect that the original 8C2 gate did not exercise.

Scenario 3 local diagnostics used `Scenario3FixtureSources`, while
`FieldVisitApprovalService` revalidated current CMDB/monitoring truth through a
separate `Scenario1FixtureSources` instance. Both instances had the same
canonical topology/default state, but their process-local access-link override
stores were independent. Therefore a Scenario 3 deterministic stale transition
`OperationalState.DOWN -> OperationalState.UP` could be visible to Scenario 3
diagnostic reads while approval revalidation still observed stale DOWN truth.

The composition is now corrected without cloning approval logic or introducing
Scenario 3 business state:

- Scenario 1 and Scenario 3 keep separate bootstrap fixture objects;
- both fixture objects receive one shared authoritative access-link override
  store for the common physical topology;
- Field Service approval revalidation and Scenario 3 diagnostic reads therefore
  observe the same process-local source truth;
- the existing Scenario 1 acceptance override semantics remain intact.

A focused regression test now proves that an override applied through the
Scenario 3 fixture is observed identically through the Scenario 1 source used by
Field Service revalidation.

## Schema / architecture audit

Compared with final Phase 8C1, Phase 8C2 adds no migration or business table.

Alembic remains:

`20261006_0006 (head)`

and:

`No new upgrade operations detected.`

Phase 8C2 also adds:

- no dedicated Scenario 3 outbox topic;
- no third durable worker;
- no second generic session/resume framework;
- no Scenario 2 refactor;
- no Major Incident mutation tool in Scenario 3;
- no Product-side Scenario 3 replanning branch;
- no artificial provider-health requirement in the Field Service validator.

## Verification

Final deterministic code gate on:

`9d9d6f2a44b709c6d443e9608e4d3e026ccb0470`

GitHub Actions run:

`37504606915` — **SUCCESS**

Results:

- focused Phase 8C1 regression: **5 passed**;
- focused Phase 8C2 tests: **8 passed**;
- Alembic: **`20261006_0006 (head)`**;
- Alembic autogenerate check: **No new upgrade operations detected**;
- full Python regression: **208 passed**;
- retained historical Node regression: **5 passed**;
- frontend typecheck: PASS;
- frontend lint: PASS;
- frontend tests: **42 passed**;
- frontend production build: PASS;
- public-bundle static audit: PASS;
- Product Docker image build: PASS.

## Next

**Phase 8D — deterministic Scenario 3 E2E + recovery/regressions + minimal UI exposure.**

Phase 8D must prove the observable replanning trace with scripted/model-double
behavior against the real Product stack:

provider investigation -> dependency mapping -> AcmePay HEALTHY -> only then
local/device diagnostics -> independently supported local access-link failure ->
Field Service proposal -> native HITL, including approve/replay/reject/stale and
restart/redelivery behavior.

Managed real-Gemini acceptance remains Phase 8E.
