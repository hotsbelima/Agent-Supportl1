# Phase 8D implementation notes — code/UI portion only

**Status:** CODE IMPLEMENTED / TESTS DEFERRED / NOT YET PASS

**Date:** 6 October 2026  
**Branch:** `phase-8d-scenario3-ui`

## Scope completed in this pass

The user explicitly requested implementation of Phase 8D while deferring the
Phase 8D tests. This pass therefore implements only the production/UI portion
that remained after Phase 8C1/8C2.

Phase 8C1/8C2 already provide the Scenario 3 Product foundation, provider
Evidence reads, Scenario 3 native ADK composition, shared device-Incident
runtime, persisted scenario routing and native Field Service HITL.

No additional Scenario 3 backend workflow/state machine was added in 8D.

### Minimal Scenario 3 frontend exposure

The existing console is reused.

Added:

- `startScenario3()` in the browser API client using
  `POST /api/v1/scenario-3/runs`;
- Scenario 3 readiness fields in the frontend health contract;
- a Scenario 1 / Scenario 3 selector in the existing launch card;
- Scenario 3 launch is enabled only when the shared Product/ADK readiness is
  healthy and both Scenario 3 provider/native wiring flags are present;
- Scenario 1 remains the default selection and preserves the historical
  `Start simulation` path;
- after start, both scenarios navigate to the same existing
  `/runs/{run_id}` console;
- the run console derives its title from persisted `state.run.scenario_id`;
- the header shows the persisted scenario ID explicitly;
- the failed-run navigation now returns to the shared scenario launcher rather
  than referring specifically to Scenario 1.

No separate Scenario 3 console, browser-side ADK invocation path or duplicate
decision UI was introduced.

### UI architecture retained

The existing generic console still renders:

- Incident;
- Product Evidence/Observations;
- Proposal;
- Approval;
- ExecutedAction;
- FieldServiceWorkOrder;
- persisted Product timeline;
- SSE reconnect/recovery.

Scenario 3 provider Evidence is rendered through the same generic Evidence
surface. No Scenario 3-specific Product state model was added to the frontend.

## Baseline health metadata maintenance

Immediately before Phase 8D, `/health` was intentionally updated to:

- `phase = 8`
- `checkpoint = 8C2`

Two historical Phase 6 tests still asserted the old `7 / 7A` metadata. Their
existing assertions were aligned with the intentional current metadata so the
baseline is not red for an obsolete expectation.

These are maintenance edits to historical tests, not new Phase 8D tests.

## Explicitly NOT done in this pass

Per user instruction, **Phase 8D tests were not implemented**.

Not added:

- deterministic scripted/model-double Scenario 3 E2E;
- provider-first -> AcmePay HEALTHY -> local-domain trace assertion;
- Approve E2E;
- replay E2E;
- Reject E2E;
- stale E2E;
- restart/redelivery E2E;
- hidden-CoT persistence audit test;
- new Scenario 1/2 regression assertions for Phase 8D;
- new frontend Scenario 3 test coverage.

Therefore Phase 8D must **not** be marked DONE/PASS yet.

The next Phase 8D task is to add the deferred deterministic verification and
prove the acceptance trace. Only after that verification passes should Phase 8D
be closed and Phase 8E managed/live acceptance begin.

## Non-test validation

A dedicated Phase 8D code-validation workflow was added. It intentionally does
not run pytest or Vitest.

It checks only:

- production Python compilation;
- frontend dependency install;
- TypeScript typecheck;
- frontend lint;
- frontend production build;
- public-bundle/static audit;
- Product Docker image build.

This is a build/syntax/security sanity gate, not Phase 8D acceptance proof.

## Current stop point

> Phase 8C1 — DONE / PASS  
> Phase 8C2 — DONE / PASS  
> Phase 8D production/UI code — IMPLEMENTED  
> Phase 8D deterministic tests/acceptance — DEFERRED  
> Phase 8D overall — NOT YET PASS  
> Phase 8E — BLOCKED until deferred 8D verification is completed
