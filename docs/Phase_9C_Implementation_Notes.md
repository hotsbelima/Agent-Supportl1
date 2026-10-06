# Phase 9C — Deterministic Release Gate — Implementation Notes

**Status:** DETERMINISTIC PASS  
**Date:** 7 October 2026  
**Repository:** `hotsbelima/Agent-Supportl1`  
**Implementation branch:** `phase-9c-deterministic-release-gate`  
**Base:** `phase-9b-public-demo-hardening`  
**Validated code SHA:** `a5ca29218206335129dc7b3d8ec8c25e9649e698`  
**GitHub Actions:** run `37540487820` — SUCCESS  
**Live Gemini required:** no

## Scope completed now

This Phase 9C slice implements and runs every final-release check that can be
made deterministically without live Gemini/provider quota.

The live-provider/browser smoke remains intentionally deferred to Phase 9E.

## Final deterministic gate

Added:

- `.github/workflows/phase9c-deterministic-release.yml`
- `frontend/spec/phase9c-release-contract.spec.ts`

The gate explicitly sets `GOOGLE_API_KEY=""` and finishes with an assertion
that no live provider credential was required.

### Scenario 1

Focused deterministic coverage includes:

- human approval;
- rejection;
- idempotent replay;
- stale proposal handling;
- durable dispatch/recovery behavior.

### Scenario 2

Focused deterministic coverage includes:

- persisted multi-event ingestion;
- correlation/tool contracts;
- Product Evidence;
- Major Incident HITL;
- approval/reject/replay behavior;
- durable ADK-dispatch contracts using scripted/non-live test runtimes.

### Scenario 3

Focused deterministic coverage includes:

- provider-first hypothesis;
- HEALTHY provider disconfirmation;
- local diagnostic replanning;
- Evidence;
- Field Service HITL;
- approve/reject/stale/replay;
- restart/redelivery with persisted native ADK session semantics.

No live Gemini request is required by these tests.

## Browser/recovery contract

The Phase 9C frontend contract now guards:

- all three scenario start paths;
- Scenario 2 routing to its Product-state console;
- the correct decision endpoint family for standard vs Major Incident HITL;
- New simulation returning to the launcher rather than deleting old history;
- interrupted decision recovery from authoritative persisted Product state;
- SSE reconnect/backfill behavior;
- public-demo cooldown vs provider-quota error classification.

Existing frontend/API/recovery tests remain part of the same gate.

## Public-demo regression

Phase 9B security tests are mandatory in 9C and prove:

- hidden manual invoke is unavailable in public mode;
- Scenario 2 raw signal/acceptance controls are unavailable;
- the Phase 6D acceptance hook is unavailable publicly;
- fixed server-side tenant behavior;
- typed public-demo cooldown;
- exact CORS policy;
- release-health behavior.

The static source/bundle audit remains mandatory.

## Full release checks

Run `37540487820` passed:

- dependency consistency;
- Python compile;
- Alembic upgrade/current/check;
- Scenario 1 focused regression;
- Scenario 2 focused regression;
- Scenario 3 focused regression;
- Phase 9B public security regression;
- **full Python regression**;
- retained historical Node regression;
- frontend typecheck;
- frontend lint;
- frontend deterministic contract/recovery tests;
- Next.js production build;
- frontend source/bundle secret audit;
- Product Docker build;
- explicit no-live-provider assertion.

## Defect found by the first 9C gate

The first release-gate run `37540133826` correctly failed the full Python
regression after all three focused scenario suites had passed.

The failing historical test was:

`test_phase8c1_scenario1_worker_fails_closed_for_scenario3_envelope`

Its helper attempted to reach the target durable outbox row with a hard-coded
maximum of ten `dispatch_once()` calls. Earlier focused suites in the same
release gate can legitimately leave more than ten due generic-topic envelopes,
so the assertion became order-dependent even though Product behavior was
correct.

The test helper was corrected to drain finite due work until either:

- the exact target row is claimed/rescheduled; or
- no due envelope remains.

Production dispatch code was not changed for this correction.

The second full release run `37540487820` then passed.

## What remains outside this deterministic PASS

Phase 9C does not claim live-provider acceptance.

Still deferred to Phase 9E:

- live Gemini invocation through the final deployed backend;
- public browser smoke of Scenario 1/2/3 against the deployed release;
- final Vercel/Northflank release identity;
- real public CORS/security smoke;
- real SSE refresh/reconnect smoke on the deployed URL.

A live Gemini `429 RESOURCE_EXHAUSTED` remains provider capacity, not a
deterministic Phase 9C product failure.
