# Phase 7D implementation notes

Status: **implementation checkpoint only — tests intentionally not run yet**.

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

## Not done in this checkpoint

No Phase 7D tests, migrations, regression suite, Docker build or live Gemini
acceptance have been run yet, by explicit request. This document therefore does
not claim Phase 7D PASS.

The next step is a separate Phase 7D verification/hardening pass before Phase 7E.
