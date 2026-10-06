# Phase 7D implementation notes

Status: **PASS — implementation reviewed, hardened and verified.**

Base:
- Phase 7C PASS: `e8f4e667e2ba8f3d7223cf25897f72fcc115e699`
- branch: `phase-7d-scenario2-tools-hitl`

## Implemented

Phase 7D extends the existing Phase 7C durable event/session lifecycle; it does
not introduce a second agent loop or session framework.

Native ADK Scenario 2 now exposes five Product tools:

1. `get_local_service_health`
2. `get_service_dependencies`
3. `get_external_dependency_status`
4. `search_major_incidents`
5. `propose_major_incident`

The four read tools persist typed Product Evidence. Proposal creation remains
deterministic Product logic and requires evidence for cross-site signals, healthy
local sites, common dependency mapping, degraded external dependency and a fresh
negative Major Incident search.

A successful proposal creates only `PENDING_APPROVAL` Product state. The same
native `await_human_decision` LongRunningFunctionTool used by the existing ADK
HITL architecture pauses the Scenario 2 invocation. Product Approve/Reject API
operations commit first; the exact persisted invocation is resumed afterwards.

The runtime treats a proposal without the native wait point as non-recoverable,
so the durable outbox is not marked delivered for a half-complete HITL flow.

## Product persistence

Migration `20261006_0006` adds dedicated Scenario 2 tables:

- `major_incident_proposals`
- `major_incident_approvals`
- `major_incidents`
- `major_incident_executions`

Equivalent Major Incident uniqueness is tenant-wide by
`(service_key, correlation_key, dependency_id)`. Duplicate search also includes
persisted Major Incidents across runs for the tenant.

Scenario 2 public state now includes typed Evidence plus proposal, approval,
execution and Major Incident records. Persisted hidden fixture truth is still not
exposed.

## Product human-decision endpoints

- `POST /api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/approve`
- `POST /api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/reject`

Approve revalidates current local health, dependency mapping, provider status and
duplicate-Major-Incident state before execution. Recovered/changed truth makes
the proposal `STALE`; a valid approval creates one `MajorIncidentRecord` and
one `MajorIncidentExecution`. Reject creates no execution.

Proposal/approval/execution transitions append Product application audit events.
Lock ordering is `Run -> Proposal` for proposal/approval serialization.

## Verification and hardening

The review found and fixed concrete implementation issues rather than only
adding happy-path tests:

- the Scenario 2 runtime now uses the existing native
  `ProductRetryableToolPlugin` for Product failures explicitly marked retryable;
- native `await_human_decision` is accepted only after a successful real
  `propose_major_incident` response and only for that exact proposal ID;
- a created proposal without the native wait point is non-recoverable, so the
  durable outbox cannot be marked delivered for a half-complete HITL flow;
- delivered human FunctionResponse state clears the pending-wait marker on
  later history/redelivery inspection;
- Major Incident persistence explicitly flushes the FK target before inserting
  the dependent execution row;
- Phase 7C sparse/historical ADK event shapes remain compatible with the extended
  Phase 7D correlation logic;
- the Phase 7C health checkpoint remains stable while Phase 7D is exposed as
  additive capability flags;
- the intentional public API contract now includes only the two new Scenario 2
  Approve/Reject routes.

Focused Phase 7D coverage proves:

- exact native ADK tool surface and hidden trusted context;
- fail-closed proposal/wait correlation;
- native ADK pause/resume on the same invocation and redelivery reconciliation;
- PostgreSQL Evidence creation, proposal persistence, Approve and replay;
- Reject with no execution;
- stale-on-provider-recovery;
- tenant-wide duplicate protection/search across runs;
- Product API/HITL wiring.

Verified gate on the implementation before this documentation update:

- focused Phase 7D: **9 passed**;
- Alembic: **`20261006_0006 (head)`**, clean autogenerate check;
- full Python regression: **195 passed**;
- retained Node regression: PASS;
- frontend typecheck/lint/build: PASS;
- frontend tests: **42 passed**;
- static public-bundle audit: PASS;
- Product Docker image build: PASS.

Phase 7D does not require live Gemini acceptance because the roadmap reserves
managed/live acceptance for Phase 7E. Phase 7D uses a scripted real native ADK
Runner test to prove the LongRunningFunctionTool pause/resume mechanics without
making model behavior part of this deterministic gate.

Next: **Phase 7E managed/live acceptance**.
