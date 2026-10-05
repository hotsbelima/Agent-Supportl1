# Phase 5D2 — Codex built-in browser managed acceptance runbook

This runbook is prepared by 5D1. Execute it only from the exact D1 release
candidate that passed the isolated gate.

## Boundary

Use Codex built-in browser / managed browser capabilities for real website
interaction. Do not require Playwright installation in this repository.

D2 is acceptance/deployment work, not feature development. If a functional
defect is found:

1. record the reproduction;
2. fix it in development/D1;
3. rerun the full D1 gate;
4. use the new exact candidate;
5. repeat D2.

## Existing managed infrastructure

Northflank:

- project: `agent-l1-support`;
- PostgreSQL: `DB1`;
- PostgreSQL version: 16;
- region: London;
- private networking;
- backend service: `product-api`;
- product port: `8080`;
- runtime DB secret: managed `DATABASE_URL`;
- image entrypoint: `Dockerfile.product`.

Do not create a second database.
Do not use or expose an admin DB URI.

## 1. Deploy exact backend candidate

Deploy the exact D1 release-candidate commit to the existing
`product-api` service.

Keep:

- same `DB1`;
- same private networking;
- same managed runtime `DATABASE_URL`;
- `PORT=8080`;
- `Dockerfile.product`.

Run/verify migrations only if required by the candidate. Do not invent a new
migration when Alembic is already at head.

Confirm:

- service healthy;
- `GET /health` returns ok;
- `adk_wired=false`;
- `sse_wired=true`.

## 2. Deploy frontend to Vercel

Deploy the repository `frontend/` package.

Production public env:

- `NEXT_PUBLIC_API_BASE_URL=<public product-api HTTPS origin>`;
- `NEXT_PUBLIC_DEMO_TENANT_ID=TENANT-8OCT`.

No DB/Google/Northflank credential belongs in Vercel browser env.

After Vercel gives the production URL:

1. add its exact HTTPS origin to backend `FRONTEND_ORIGINS`;
2. retain any explicitly needed local/dev origin only if intentional;
3. do not use `*`;
4. controlled redeploy/restart backend config;
5. confirm CORS from the real browser.

Record:

- exact D1 commit;
- backend production origin;
- Vercel production URL.

## 3. Browser acceptance — base run

With the Codex built-in browser:

1. Open the Vercel production `/`.
2. Confirm Product API readiness is visible.
3. Click **Start Scenario 1**.
4. Confirm navigation to `/runs/<run_id>`.
5. Record `run_id`.
6. Confirm authoritative Run and Incident fields render.
7. Confirm initial persisted timeline renders in ascending seq order.
8. Confirm connection reaches **Live**.
9. Record current last event seq.
10. Reload the browser page.
11. Confirm the same run is reconstructed from the URL.
12. Confirm no duplicate timeline rows after reload.
13. Open the same `/runs/<run_id>` as a direct/deep link and confirm it works.

Expected initial Phase 5 behavior: no fake tools/proposal are rendered before
controlled persisted proposal creation.

## 4. Controlled real persisted proposal

Using Northflank one-off execution/shell for the deployed candidate, run:

```bash
python scripts/phase4d_seed_proposal.py \
  --tenant-id TENANT-8OCT \
  --run-id <run_id>
```

Do not expose this operation as HTTP.

Capture only its safe output:

- tenant_id;
- run_id;
- proposal_id;
- proposal_status;
- evidence_count.

Back in the already-open browser, without manual page reload:

1. confirm timeline receives the new persisted events;
2. confirm Evidence panel refreshes;
3. confirm Proposal card appears;
4. confirm proposal is `PENDING_APPROVAL`;
5. confirm diagnosis/action/evidence IDs/rationale are shown.

## 5. Approve path

1. Click **Approve**.
2. Confirm both decision buttons are disabled while request is in flight.
3. Confirm proposal becomes `EXECUTED`.
4. Confirm incident becomes `ESCALATED`, not `RESOLVED`.
5. Confirm exactly one registered WorkOrder.
6. Confirm Action ID/type/executed timestamp are visible.
7. Confirm switch/port/site/device/work-order timestamp are visible.
8. Confirm UI explicitly does not claim repair.
9. Confirm timeline includes persisted approval/action/status events.
10. Reload.
11. Confirm the same result is reconstructed.
12. Repeat Approve through the same API/action path if available.
13. Confirm idempotent replay and no second Action/WorkOrder.

## 6. Reject path

Start a separate Scenario 1 run and seed a separate proposal through the same
controlled helper.

1. Click **Reject**.
2. Confirm proposal becomes `REJECTED`.
3. Confirm run returns to `ACTIVE`.
4. Confirm incident remains `OPEN`.
5. Confirm zero ExecutedAction.
6. Confirm zero WorkOrder.
7. Reload and confirm the same persisted result.

## 7. Real backend restart/reconnect proof

Use an approved run with visible timeline/result and leave its Vercel page open.

Then perform a real restart/redeploy of the existing Northflank
`product-api` service.

In the open browser verify:

1. existing timeline stays visible;
2. connection changes to `Reconnecting` and may reach
   `Offline/Unavailable` during longer downtime;
3. no browser tight-loop flood appears;
4. backend returns;
5. authoritative state is reread;
6. persisted events after the cursor are backfilled;
7. connection returns to **Live**;
8. no seq gap exists;
9. no duplicate timeline rows exist;
10. run/incident/proposal/action/work-order persist.

Record before/after last seq values.

## 8. Security acceptance

Inspect with the built-in browser/devtools capabilities where available:

Browser:

- console;
- network requests/responses;
- loaded public JS assets.

Northflank:

- service logs;
- deploy/job output;
- controlled seed output.

Vercel:

- deployment/build logs and public env configuration.

Must not expose:

- `DATABASE_URL`;
- PostgreSQL password;
- Google API key;
- Northflank admin URI;
- other server credentials;
- raw backend exception/stack/DSN;
- hidden model reasoning / chain-of-thought.

Expected browser-visible public configuration is limited to:

- Product API public origin;
- demo tenant identifier.

## 9. Final Phase 5 decision

Only after all D2 checks succeed, mark:

> Phase 5 DONE / PASS

If any real-browser/deployment/restart requirement is unproven, status remains:

> READY FOR MANAGED ACCEPTANCE

or

> MANAGED ACCEPTANCE FAILED — FIX REQUIRED

Do not start live Phase 6 ADK/Gemini product wiring before Phase 5 PASS.
