# Phase 9A — Implementation Notes

**Status:** PASS  
**Date:** 6 October 2026  
**Repository:** `hotsbelima/Agent-Supportl1`  
**Implementation branch:** `phase-9a-ui-polish`  
**Baseline:** `85696a3b34c56b5149da2d83c8d3af65642a9584` (`phase-9-scope-spec`)  
**Validated UI code SHA:** `4c48fbbe3c5845ee48db5239782ceeecc4fcc1c2`  
**GitHub Actions:** run `37533545468` — SUCCESS

## Delivered

Phase 9A now exposes the three already-implemented Product scenarios through
the browser without adding browser-side agent orchestration.

### Three-scenario launcher

The launcher now exposes:

1. Scenario 1 — local terminal connectivity incident.
2. Scenario 2 — correlated multi-event service incident / Major Incident flow.
3. Scenario 3 — evidence-driven provider disconfirmation and replanning.

Scenario 1 remains the default selection. Readiness is derived from Product API
health/wiring state rather than browser-local assumptions.

### Scenario 2 browser integration

Scenario 2 uses the existing Product API and persisted Product state:

- run start: `POST /api/v1/scenario-2/runs`;
- state: `GET /api/v1/scenario-2/runs/{run_id}`;
- simulator progression:
  `POST /api/v1/scenario-2/runs/{run_id}/simulator/next`;
- Major Incident Approve/Reject endpoints;
- existing persisted application-event timeline and SSE stream.

A dedicated presentation component is used because Scenario 2 has a different
Product-state shape (`service_incidents`, `operational_signals`,
`major_incident_*`). It does not create a second source of truth or a
frontend-only simulator.

### Incident navigation

The Incidents window follows the same interaction model as Observations:

- list view inside the panel;
- open one incident in the same panel;
- return to the list without route changes;
- works for the standard Scenario 1/3 console and the Scenario 2 service
  incident console.

### Bounded scrolling

Operational panels no longer grow indefinitely as events/evidence accumulate.

On desktop the console has a viewport-bounded working area and each
`.scroll-panel` owns its vertical scrolling. Tablet/mobile retain bounded
panel heights with native vertical scrolling. No wheel interception or custom
scroll physics were added.

### Themes

The dark interface remains the default.

A persistent user-selectable light theme was added. Theme preference is stored
in browser localStorage. The light theme is an option; it does not replace or
remove the dark design.

### Russian UI

Browser-facing copy is Russian across:

- landing/launcher;
- readiness and configuration states;
- Scenario 1/3 console;
- Scenario 2 console;
- timeline summaries;
- incident/observation drill-down;
- proposal/HITL controls;
- recovery/reconnect notices;
- provider/rate-limit error presentation;
- theme controls.

Wire-level enum values, API fields, event types and technical payloads are not
renamed.

Canonical English domain terminology is preserved in
`docs/phase9a_ui_terminology.md`.

### New simulation

Run consoles expose **Новый запуск**, which returns to the scenario selector.
Starting again creates a new Product Run. Existing run/audit history is not
deleted or mutated.

### Failure and recovery presentation

The frontend distinguishes and/or intentionally represents:

- initial loading;
- Product API unavailable;
- missing run;
- Gemini not configured;
- provider/rate-limit 429;
- empty incidents/evidence/proposals;
- waiting for human decision;
- rejected/stale/executed proposal states;
- SSE reconnect/recovery from persisted state;
- interrupted decision response with authoritative state refresh.

No hidden model chain-of-thought is exposed.

## Re-audit corrections

A second specification/code audit found and fixed issues that were not caught
by the first PASS review:

- two residual English user-facing recovery/not-found strings;
- remaining user-facing `Product API` wording, localized to `API продукта`;
- incomplete light-theme overrides that left some header/card/detail surfaces
  using dark-only colors;
- dynamic readiness/loading regions missing semantic `role="status"` /
  `aria-live="polite"`;
- stale implementation-note SHA/CI metadata.

Regression coverage was extended to guard the Russian UI copy, complete
light-theme surfaces and semantic status regions.

## Verification

A dedicated `.github/workflows/phase9a-ui.yml` deterministic gate was added.

Validated run `37533545468` passed:

- `npm ci`;
- TypeScript typecheck;
- ESLint;
- all frontend unit/API-contract tests, including the new Phase 9A regression;
- Next.js production build.

The new Phase 9A regression explicitly checks:

- all three public scenarios;
- Scenario 2 real Product API wiring;
- no browser `/agent/invoke` orchestration;
- same-panel incident drill-down;
- bounded independent scrolling;
- dark-default / optional-light behavior;
- non-destructive New simulation behavior;
- Russian UI plus the canonical English terminology glossary.

## Files of note

- `frontend/components/start-scenario.tsx`
- `frontend/components/run-console.tsx`
- `frontend/components/scenario2-console.tsx`
- `frontend/components/run-router.tsx`
- `frontend/components/theme-toggle.tsx`
- `frontend/app/globals.css`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `frontend/lib/presentation.ts`
- `frontend/spec/phase9a-ui.spec.ts`
- `docs/phase9a_ui_terminology.md`
- `.github/workflows/phase9a-ui.yml`

## Scope boundary

Phase 9B has **not** been started.

This phase does not claim to have completed the public-demo security boundary,
acceptance/debug endpoint protection, public tenant policy, server-side Gemini
abuse protection, release metadata, or final public deployment. Those remain
Phase 9B+ work under the Phase 9 implementation contract.
