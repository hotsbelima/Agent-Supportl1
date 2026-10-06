# Phase 9B — Simplified Public Demo Hardening — Implementation Notes

**Status:** PASS  
**Date:** 7 October 2026  
**Repository:** `hotsbelima/Agent-Supportl1`  
**Implementation branch:** `phase-9b-public-demo-hardening`  
**Base:** `phase-9a-ui-polish`  
**Validated implementation SHA:** `5147057689bc44ec5722317e0fdf6aeb0aa5ab11`  
**GitHub Actions:** Phase 9B run `37538822286` — SUCCESS

## Scope decision

Phase 9B was deliberately reduced to portfolio-grade public-demo hardening.

The implementation does **not** add enterprise authentication, RBAC/SSO,
Redis, distributed rate limiting, a tracing platform, or a new multi-mode
runtime framework.

## Delivered

### One public-demo switch

`PUBLIC_DEMO=true` enables the public boundary.

When disabled, the existing development/acceptance behavior remains intact.

### Fixed server-side demo tenant

In public-demo mode the server uses `PUBLIC_DEMO_TENANT_ID` as the Product
tenant context.

The browser may continue sending `X-Tenant-ID` for compatibility, but the
server ignores that value in public mode. The header may also be absent or
invalid without changing server-side tenant selection.

When `PUBLIC_DEMO=true`, `PUBLIC_DEMO_TENANT_ID` must be explicitly configured.

This is a demo isolation rule, not authentication.

### Internal routes hidden

Public-demo middleware returns safe `404 NOT_FOUND` before request/body
validation for:

- `/api/v1/runs/{run_id}/agent/invoke`;
- direct Scenario 2 `/signals` ingestion;
- Scenario 2 dependency-status acceptance control;
- Scenario 2 matching-major-incident acceptance control;
- Phase 6D acceptance access-link hook.

The Phase 6D route remains usable outside public-demo mode under its existing
enable/token protection.

### Simple Gemini/run-start protection

New public demo runs share one small process-local cooldown.

Configuration:

- `PUBLIC_DEMO_COOLDOWN_SECONDS`, default `8`;
- blocked starts return `429 PUBLIC_DEMO_COOLDOWN`;
- response includes `Retry-After`;
- no Redis/distributed limiter was introduced.

The frontend distinguishes this local demo cooldown from a real Gemini/provider
quota error.

### CORS

The existing exact-origin CORS implementation is reused.

When `PUBLIC_DEMO=true`, `FRONTEND_ORIGINS` must resolve to at least one valid
exact http(s) origin. Wildcards, malformed origins and an empty origin list are
rejected.

### Secret/static audit

The existing browser/static-bundle audit remains part of the gate and was
extended to reject Phase 6D acceptance-token names in shipped frontend code.

It already rejects database credentials, Gemini keys, database URLs and hidden
reasoning markers.

### Safe errors

The existing generic Product API exception boundary remains unchanged in
principle: raw exceptions, provider payloads, stack traces and credentials are
not returned to the browser.

### Lightweight release identity

`/health` now includes:

- `phase: 9`;
- `checkpoint: 9B-lite`;
- `release_version: 0.9.0`;
- `release_sha`;
- `public_demo`;
- `tenant_policy`;
- the existing database, Gemini, ADK and scenario readiness fields.

Release SHA can be supplied through `RELEASE_SHA` (preferred) or supported
deployment commit-SHA environment variables.

## Public deployment environment

For the eventual Phase 9E deployment, the backend needs the following
portfolio-demo settings in addition to the existing database/Gemini config:

```text
PUBLIC_DEMO=true
PUBLIC_DEMO_TENANT_ID=TENANT-8OCT
PUBLIC_DEMO_COOLDOWN_SECONDS=8
FRONTEND_ORIGINS=https://<final-vercel-origin>
RELEASE_SHA=<deployed-git-sha>
```

The exact final Vercel origin and deployed SHA are intentionally deferred to
Phase 9E.

## Verification

Phase 9B run `37538822286` passed on implementation SHA
`5147057689bc44ec5722317e0fdf6aeb0aa5ab11`:

- Python dependency consistency;
- Python compile;
- Alembic upgrade/current/check;
- focused Phase 9B tests;
- Product API regression;
- Phase 6D acceptance-hook regression;
- Scenario 2 ingestion and HITL regressions;
- frontend typecheck;
- frontend lint;
- frontend tests;
- production Next.js build;
- source + built-bundle secret/static audit.

The Phase 9B tests specifically prove:

- public mode requires explicit CORS origins;
- browser tenant input cannot choose another Product tenant;
- public APIs work without a tenant header;
- rapid second run start receives typed `429` + `Retry-After`;
- internal/acceptance routes return `404` even with malformed JSON;
- non-public tenant behavior is preserved;
- health exposes release/public-demo identity safely.

## Second audit corrections

The second Phase 9B audit found and fixed five issues:

- direct Scenario 2 raw signal ingestion could bypass the new-run cooldown; it
  is now hidden in public-demo mode while the finite simulator remains public;
- browser tenant-header validation could run before fixed server-side tenant
  selection; public mode now ignores that header before tenant validation;
- exact-origin CORS validation now applies to both environment and injected
  configuration, including rejection of an empty public-demo origin list;
- public-demo startup now requires an explicit `PUBLIC_DEMO_TENANT_ID`;
- the frontend `HealthResponse` type now includes the Phase 9B release fields.

The audit also confirmed that proposal decision replay is idempotent and that
the Scenario 2 simulator has a finite canonical sequence, so no larger
rate-limiting subsystem was added.

## Regression compatibility correction

Opening the Phase 9B PR exposed one stale historical assertion:
`test_phase8d_health_reports_current_checkpoint` permanently required
`phase == 8` / `checkpoint == 8D`. Phase 9 legitimately advances global
release metadata, so the Phase 8D test was corrected to verify the Scenario 3
readiness guarantees it actually owns instead of freezing the repository's
future release number.

After that correction, the current code SHA passed all automatically triggered
historical PR gates:

- Phase 6A;
- Phase 6B;
- Phase 7A;
- Phase 7B;
- Phase 7C;
- Phase 7D;
- Phase 8C1;
- Phase 8C2;
- Phase 8D;
- Phase 9B.

No Product/ADK business semantics were changed to make those regressions pass.

## Files of note

- `product_api/public_demo.py`
- `product_api/app.py`
- `tests/test_phase9b_public_demo.py`
- `frontend/lib/api.ts`
- `frontend/spec/phase9b-public-demo.spec.ts`
- `scripts/phase5d1_static_audit.py`
- `.github/workflows/phase9b-public-demo.yml`
- `docs/Phase_9_Final_Polish_Hardening_Public_Demo_Spec.md`

## Explicitly not added

- user accounts/login;
- RBAC/SSO;
- enterprise tenant authorization;
- Redis;
- distributed/global rate limiting;
- API gateway;
- new observability/tracing infrastructure;
- separate local/managed/public runtime policy framework.

Those are unnecessary for the stated portfolio-demo goal.
