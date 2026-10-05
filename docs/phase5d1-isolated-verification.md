# Phase 5D1 — Isolated pre-release verification

## Purpose

5D1 proves that the exact Phase 5 release candidate is internally green before
any Vercel/Northflank managed acceptance.

Starting checkpoint:

- branch: `phase-5d1-isolated-verification`
- baseline: `cd220d8eefaebfe2bebc63a0ab858f1d639859ff`
- Phase 5A: PASS
- Phase 5B: PASS
- Phase 5C: PASS

5D1 does **not** declare Phase 5 PASS.

## Browser acceptance delta from handoff v6.2

The v6.2 handoff originally listed a committed Playwright suite as a D1
deliverable. That requirement is superseded for this checkpoint.

The external D2 executor is Codex with its own built-in browser, so the release
candidate does not add Playwright as a package/dependency merely to drive D2.
Real URL-based browser acceptance remains mandatory, but it is executed in
5D2 with the built-in browser against actual Vercel/Northflank infrastructure.

No mock browser test may be presented as equivalent proof.

## D1 isolated gate

Backend:

- pinned requirements install;
- `pip check`;
- compileall;
- Alembic upgrade/current/check;
- Phase 3 regression;
- Phase 4A/B/C regression;
- Phase 5A persisted SSE regression;
- Phase 5D1 controlled release-candidate integration;
- full Python regression.

Historical Node:

- retained root `npm test`.

Frontend:

- source public-surface audit;
- `npm ci` from committed lockfile;
- typecheck;
- lint;
- all unit/recovery/API/SSE tests;
- production `next build`;
- built `.next/static` browser-bundle audit.

Packaging:

- `Dockerfile.product` image build.

## Controlled proposal setup for D2

D2 must not create a public test endpoint.

Use the existing non-HTTP helper included in the product image:

```bash
python scripts/phase4d_seed_proposal.py \
  --tenant-id TENANT-8OCT \
  --run-id <RUN_ID_FROM_UI>
```

The helper:

- uses Scenario 1 fixture reads;
- persists four real typed Evidence records;
- creates the proposal through `FieldVisitProposalService`;
- emits the real persisted proposal/status/tool events;
- returns only safe identifiers/status;
- does not print `DATABASE_URL`.

D1 integration tests verify this helper against PostgreSQL and the existing
Approve/Reject API.

## Public browser security contract

Only these browser-visible configuration variables are allowed:

- `NEXT_PUBLIC_API_BASE_URL`;
- `NEXT_PUBLIC_DEMO_TENANT_ID`.

The runtime frontend source and built static browser bundle are audited for
forbidden server-side tokens/credential families.

## D1 completion status

D1 is complete only when the workflow
`Phase 5D1 isolated release verification` is green on the exact candidate
commit.

Completion wording:

> READY FOR MANAGED ACCEPTANCE

Do not write `Phase 5 PASS` until 5D2 completes real deployment, browser
acceptance and managed restart/reconnect proof.
