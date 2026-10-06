# Phase 9 — Final Polish, Hardening, Documentation, and Public Demo

**Status:** DESIGN / IMPLEMENTATION CONTRACT  
**Date:** 6 October 2026  
**Repository:** `hotsbelima/Agent-Supportl1`  
**Planning branch:** `phase-9-scope-spec`  
**Planning baseline:** `afadcf6ddde437964a20962ebe8a642b4185ff97`  
**Live-validated product SHA:** `7232df9554aa15037a52a4051d5ae9939eb5799a`  
**Current canonical handoff:** `docs/handoff/Autonomous_L1_Incident_Agent_Handoff_v7.5_Phase_8E_CI_Cleanup.md`

---

## 1. Purpose

Phase 9 is the final productization phase for the portfolio/demo release.

The roadmap already defines Phase 9 as:

> **Polish, hardening, public deploy** — error/empty states, reset/scenario
> selector, security/observability hardening, final documentation,
> architecture diagram and public demo deployment.

Phases 0–8 already proved the core technical claims:

- native Google ADK + Gemini tool selection;
- persisted Product state and audit events;
- durable dispatch and restart recovery;
- native ADK session persistence and resumability;
- human approval/rejection boundaries;
- exactly-once/idempotent execution;
- Scenario 1 local Field Service flow;
- Scenario 2 multi-event / Major Incident flow;
- Scenario 3 evidence-driven replanning after a disconfirmed hypothesis;
- managed PostgreSQL + Northflank runtime;
- live Gemini acceptance.

Phase 9 must **not** invent a fourth business scenario or a new agent
architecture. It must turn the existing verified system into a coherent,
safe, understandable public demonstration.

The target is:

> A recruiter, engineer or hiring manager can open one public URL, understand
> the product, run any of the three scenarios, observe the evidence/tool/HITL
> lifecycle, and inspect truthful architecture/documentation without needing
> the author to explain hidden setup details.

---

## 2. Source priority

If sources conflict during Phase 9, use this order:

1. this Phase 9 implementation contract;
2. `Autonomous_L1_Incident_Agent_Handoff_v7.5_Phase_8E_CI_Cleanup.md`;
3. `Autonomous_L1_Incident_Agent_Handoff_v7.4_Phase_8E.md`;
4. `Autonomous_L1_Incident_Agent_Phase_8E_Acceptance.md`;
5. `Autonomous_L1_Incident_Agent_Handoff_v7.3_Phase_8D.md`;
6. repository code at the actual Phase 9 branch head;
7. earlier cumulative handoffs for historical rationale only.

Completed Phase 0–8 contracts are not reopened without a reproducible defect.

---

## 3. Current repository findings that Phase 9 must close

Phase 9 scope is based on the actual repository, not only the old roadmap.

### 3.1 Public launcher currently exposes only Scenario 1 and Scenario 3

`frontend/components/start-scenario.tsx` currently defines:

`type ScenarioChoice = "scenario-1" | "scenario-3"`

Scenario 2 backend support exists, including run creation, ingestion,
simulator, Product tools, Major Incident proposal/HITL and approval paths, but
it is not exposed in the final browser launcher.

A final three-scenario portfolio demo must make Scenario 2 discoverable.

### 3.2 README is materially stale

The repository root README still presents:

`Current scope — Phase 3 PASS`

and describes PostgreSQL/UI/SSE/live six-tool ADK as future work even though
all of those are already implemented.

This is unacceptable for a final portfolio repository and must be replaced
with a current README.

### 3.3 Known light/white UI debt remains open

The cumulative roadmap explicitly carried this debt forward:

> light / white UI polish must be closed no later than Phase 9.

The existing UI is functional and tested, but it is still a development/demo
console rather than the final polished public presentation.

### 3.4 Demo tenant header is not authentication

The backend explicitly documents `X-Tenant-ID` as:

> Trusted demo tenant context. This is not an authentication mechanism.

Phase 9 must not misrepresent the public demo as authenticated multi-tenant
SaaS. Security hardening must protect the public demo surface while keeping
this limitation explicit.

### 3.5 Historical/acceptance control surfaces exist

The Product API currently contains hidden operational/acceptance routes.

Examples include:

- Scenario 2 dependency-status acceptance control;
- Scenario 2 matching-major-incident acceptance control;
- manual hidden `/agent/invoke`;
- Phase 6D access-link acceptance hook.

The Phase 6D hook already has explicit server-side enable/token protection.
The Scenario 2 acceptance controls and manual invoke path must receive an
equivalent public-demo safety boundary or be disabled in public-demo mode.

`include_in_schema=False` is **not** a security boundary.

### 3.6 Provider quota is a demonstrated operational limitation

Managed runs have observed Gemini free-tier:

`429 RESOURCE_EXHAUSTED`

with a 15 requests/minute project/model quota.

Phase 9 must present this as an external provider-capacity state, not as a
generic broken-agent error, and the public backend must not allow an
unbounded anonymous browser to consume Gemini requests.

### 3.7 API release metadata is still development-oriented

The Product API health response is currently Phase 8 / checkpoint 8D and the
FastAPI description still primarily describes earlier Scenario 1/2
checkpoints.

The public release needs explicit current release/build metadata rather than
historical checkpoint wording being the only version signal.

---

# 4. Phase 9 structure

Phase 9 is divided into five implementation blocks.

- **9A — Final three-scenario UI / UX polish**
- **9B — Public-demo security and observability hardening**
- **9C — Full demo reliability / deterministic release gate**
- **9D — Final portfolio documentation and architecture package**
- **9E — Public deployment and final acceptance**

The blocks should be completed in order unless a reproducible dependency
requires a small adjustment.

---

# 5. Phase 9A — Final three-scenario UI / UX polish

## Goal

Turn the existing operational console into the final browser-facing demo
without changing Product business semantics.

## 9A.1 Final scenario launcher

The landing page must expose all three implemented scenarios:

1. **Scenario 1 — Local terminal connectivity incident**
   - single-device/local failure;
   - Field Service proposal;
   - human approval.

2. **Scenario 2 — Multi-event service incident**
   - multi-event correlation;
   - dependency/provider investigation;
   - Major Incident proposal;
   - human approval.

3. **Scenario 3 — Evidence-driven replanning**
   - provider hypothesis;
   - AcmePay HEALTHY disconfirmation;
   - local diagnostic-domain switch;
   - Field Service proposal;
   - human approval.

The selector must communicate what each scenario demonstrates in product
terms, not internal phase numbers.

Scenario 1/2/3 must each have a clear start action and readiness state.

## 9A.2 Scenario 2 browser path

Scenario 2 must be usable from the public browser.

Reuse the existing Scenario 2 Product API and Product state. Do not create a
parallel frontend-only simulator or fake browser state.

The UI may use a Scenario 2-specific presentation adapter/component if the
existing Scenario 1/3 `RunStateResponse` shape cannot represent Scenario 2
cleanly, but it must reuse the same visual system and product-console shell.

The UI must expose enough of Scenario 2 to demonstrate:

- persisted run;
- incoming signals / correlation progress;
- safe Product Evidence;
- Major Incident proposal;
- human Approve / Reject;
- execution/result;
- persisted timeline/recovery.

No browser-side agent orchestration is allowed.

## 9A.3 New simulation / reset semantics

Add a clear **New simulation** / **Run another scenario** action.

"Reset" must mean:

> leave the historical run intact and start a new run.

Do **not** add a destructive "delete/reset database" endpoint merely for the
UI.

Historical runs remain immutable/auditable Product records.

## 9A.4 Loading, empty, error and recovery states

Every user-visible async surface must have an intentional state for:

- initial loading;
- backend unavailable;
- Gemini not configured;
- Gemini/provider quota/rate limit;
- Product retryable error;
- not found;
- SSE reconnecting;
- SSE offline/unavailable;
- no Incident yet;
- no Evidence yet;
- no proposal yet;
- waiting for human decision;
- stale proposal;
- rejected proposal;
- action/work-order complete.

Provider 429/quota errors must be distinguishable from Product validation
failures.

The UI must never invent successful state while authoritative Product state is
unknown.

## 9A.5 Final visual design

Close the carried-forward light/white UI debt.

Target:

- dark interface remains the default public experience;
- light / white theme is available as an explicit user option and must not replace or remove the dark theme;
- clear enterprise-operations visual language;
- strong hierarchy rather than dashboard clutter;
- readable evidence/timeline/proposal cards;
- desktop-first but functional on normal mobile widths;
- visible focus states;
- semantic headings/buttons/status regions;
- sufficient contrast;
- no decorative animation that obscures operational state.

Do not turn the product into a generic chat UI.

The core mental model remains:

`operational event -> investigation -> Evidence -> proposal -> human decision -> action`

## 9A.6 Russian public UI and canonical terminology

The public browser UI is Russian.

Canonical English entity names and wire-level terminology must remain preserved
in repository documentation/code contracts so UI localization does not rename
domain concepts, API fields, event types or persistence semantics.

At minimum keep a Russian-to-English entity glossary in the repository.

## 9A.7 Reasoning privacy

The UI may show:

- model-visible function/tool calls;
- safe tool results;
- Product Evidence;
- persisted application events;
- concise agent final/status text.

It must not display, infer or request hidden chain-of-thought.

---

# 6. Phase 9B — Simplified public-demo hardening

## Goal

Apply portfolio-grade safety before publication without turning the pet project
into an enterprise security/observability platform.

The owner explicitly simplified the original Phase 9B scope. The project must
show sensible public-demo boundaries, but it does **not** need production auth,
RBAC, distributed rate limiting, Redis, a tracing platform, or a multi-mode
operations framework.

## 9B.1 One public-demo switch

Use one explicit server-side switch:

`PUBLIC_DEMO=true`

When it is off, existing local/acceptance behavior remains available under its
existing controls. Do not build a new local/managed/public environment
framework solely for this portfolio demo.

## 9B.2 Hide internal controls

When `PUBLIC_DEMO=true`, anonymous callers must receive safe `404 NOT_FOUND`
for:

- hidden manual `/agent/invoke`;
- Scenario 2 dependency-status acceptance control;
- Scenario 2 matching-major-incident acceptance control;
- the Phase 6D acceptance hook, even if its old enable/token variables are
  accidentally present.

These routes may remain available outside public-demo mode for controlled
acceptance/regression testing.

## 9B.3 Fixed demo tenant

The public deployment uses one server-configured demo tenant.

The browser's `X-Tenant-ID` value is compatibility metadata only in public
mode; it must not be able to select another tenant. The server uses
`PUBLIC_DEMO_TENANT_ID` as Product context.

This is intentionally **not** authentication. Full accounts/RBAC/SSO remain
out of scope.

## 9B.4 Simple run-start cooldown

Protect the Gemini-backed demo from rapid repeated new-run creation with a
small server-side cooldown.

Requirements:

- process-local/in-memory is sufficient for this pet project;
- no Redis, API gateway or distributed limiter is required;
- return typed `429 PUBLIC_DEMO_COOLDOWN`;
- include `Retry-After`;
- keep Gemini/provider quota errors distinct in the UI.

## 9B.5 CORS and frontend secret audit

Reuse the existing exact-origin CORS implementation.

In public-demo mode, `FRONTEND_ORIGINS` must be explicitly configured; do not
fall back to a wildcard or silently expose all origins.

Retain the frontend static audit proving that database credentials, Gemini
keys, acceptance tokens and similar server secrets are not shipped in browser
source or the built static bundle.

## 9B.6 Safe errors

Keep the existing generic Product API exception boundary:

- no stack traces;
- no raw provider payloads;
- no credentials;
- no hidden model reasoning.

Do not add a new logging/observability platform for Phase 9B.

## 9B.7 Lightweight release identity

Extend `/health` with only the information useful for a portfolio deployment:

- current API version;
- release/commit SHA supplied by environment;
- whether public-demo mode is active;
- tenant policy label;
- existing DB/Gemini/scenario readiness fields.

Do not build a separate release registry or tracing service.

## Explicitly removed from 9B

The following original ideas are no longer required:

- a three-mode runtime-policy framework;
- enterprise tenant/auth policy;
- RBAC/SSO/user accounts;
- Redis/distributed rate limiting;
- mandatory correlation of every outbox/event/session/invocation ID in a new
  observability layer;
- a large standalone security regression suite;
- any infrastructure redesign unrelated to making the portfolio demo safe.

The intended result is a small, understandable public-demo boundary that an
employer can inspect quickly.

---

# 7. Phase 9C — Full demo reliability and release gate

## Goal

Prove the final public-demo code path deterministically before public release.

## 9C.1 Mandatory deterministic coverage

The final release gate must retain:

- Phase 8C1 regression;
- Phase 8C2 regression;
- Phase 8D Scenario 3 deterministic E2E;
- Scenario 1 approval/replay/stale/recovery coverage;
- Scenario 2 correlation/tools/HITL coverage;
- full Python regression;
- historical Node regression where still retained;
- frontend tests;
- typecheck;
- lint;
- production frontend build;
- static/public-env audit;
- Product Docker build;
- Alembic current/check.

## 9C.2 Three browser scenarios

Add final browser-level contract/integration coverage proving:

- Scenario 1 can be started and viewed;
- Scenario 2 can be started, progressed through its supported simulator/event
  flow and viewed;
- Scenario 3 can be started and viewed;
- correct approval endpoint is used for each proposal type;
- "New simulation" creates a new run instead of mutating old history.

Tests should exercise real Product/API contracts where practical rather than
snapshotting static JSX only.

## 9C.3 Public security regression

Add tests proving public-demo mode:

- rejects/disables internal manual invoke;
- rejects/disables Scenario 2 acceptance controls;
- leaves explicitly enabled acceptance mode functional for controlled tests;
- rejects arbitrary public tenant context according to the selected demo
  policy;
- rate limit returns the intended safe/typed response;
- does not leak configured secrets to health/API/frontend bundle.

## 9C.4 Recovery UX regression

Prove user-facing behavior for:

- SSE reconnect;
- backend temporarily unavailable;
- interrupted approval response with authoritative replay;
- Gemini quota/rate-limit error;
- stale proposal;
- refresh/reopen of an existing run.

The UI must recover from Product truth, not from local optimistic state.

## 9C.5 Live provider checks

Deterministic PR gates must not require Gemini quota.

Live Gemini smoke tests remain explicit/manual or managed acceptance gates.

A provider 429 must be classified as provider capacity/quota, not a
deterministic product regression.

---

# 8. Phase 9D — Final documentation and architecture package

## Goal

Make the repository understandable as a portfolio artifact without reading
historical handoffs.

## 9D.1 Replace the stale root README

The final README must describe the actual completed product.

Minimum contents:

- one-paragraph product statement;
- why this is an agent rather than a scripted workflow;
- architecture overview;
- technology stack and pinned runtime;
- three scenario summaries;
- tool / Evidence / HITL model;
- persistence and recovery model;
- security/guardrail model;
- local development instructions;
- test commands;
- managed/public deployment links;
- known limitations;
- pointer to detailed handoff/acceptance evidence.

Remove statements claiming PostgreSQL/UI/SSE/live ADK are still future work.

## 9D.2 Architecture diagram

Add a maintainable architecture diagram, preferably source-controlled Mermaid
or equivalent text-based representation.

It must show at minimum:

- public Next.js frontend;
- FastAPI Product boundary;
- Product application/domain services;
- durable dispatch/outbox;
- PostgreSQL Product state;
- native Google ADK runtime/session persistence;
- Gemini;
- scenario fixture/source adapters;
- human approval boundary;
- SSE/event read path.

The diagram must preserve ownership:

- Product owns business truth;
- ADK owns generic runtime/session continuity;
- model does not own approval/execution truth.

## 9D.3 Scenario flow documentation

Document the three scenarios in a compact comparison matrix and provide
observable flow diagrams for:

- Scenario 1 local diagnosis;
- Scenario 2 multi-event/Major Incident;
- Scenario 3 provider disconfirmation/replanning.

Do not document hidden CoT.

## 9D.4 Portfolio honesty

Explicitly state that:

- ServiceNow/Zabbix/CMDB/provider integrations are controlled mock/source
  adapters for the demo;
- actions/work orders are demo Product actions, not production changes in a
  customer's infrastructure;
- the public demo access model is not full enterprise auth/RBAC;
- Gemini availability/quota remains an external dependency.

The project should look strong because its boundaries are clear, not because
limitations are hidden.

## 9D.5 Final handoff

Create a cumulative Phase 9 handoff containing:

- final release SHA;
- CI;
- public frontend URL;
- Product API deployment;
- Alembic head;
- live smoke Run/Session/invocation IDs for all scenarios as appropriate;
- known residual limitations;
- project completion status.

---

# 9. Phase 9E — Public deployment and final acceptance

## Goal

Publish the final portfolio demo and prove that the deployed artifact matches
the verified release.

## 9E.1 Deployment target

Expected topology remains:

```text
Public browser
    |
    v
Vercel / Next.js
    |
    | HTTPS + SSE
    v
Northflank / FastAPI Product API
    |
    +--> PostgreSQL
    |
    +--> native Google ADK
             |
             v
          Gemini
```

Changing hosting architecture is not a Phase 9 objective unless the current
providers cannot satisfy a reproducible requirement.

## 9E.2 Exact-release identity

Before final acceptance, record:

- Git branch;
- release commit SHA;
- GitHub Actions run;
- Vercel deployment ID/URL;
- Northflank deployment/build/revision;
- Product API URL;
- Alembic head.

The browser and backend must be demonstrably tied to the intended release.

## 9E.3 Browser smoke

From the public frontend:

### Scenario 1

Prove:

- run start;
- agent investigation;
- Evidence;
- Field Service proposal;
- HITL;
- Approve or Reject;
- correct final Product state.

### Scenario 2

Prove:

- run start;
- supported event/simulator progression;
- correlation/provider evidence;
- Major Incident proposal;
- HITL;
- human decision;
- correct Product result.

### Scenario 3

Prove:

- provider-first investigation;
- AcmePay HEALTHY;
- local tools only after provider disconfirmation;
- local diagnosis;
- Field Service proposal;
- HITL;
- human decision;
- exactly-once result.

The final public acceptance does not need to repeat every exhaustive recovery
case already deterministically proven, but it must demonstrate each scenario
through the actual deployed browser/API path.

## 9E.4 Public hardening smoke

Verify against the real deployment:

- CORS accepts the intended frontend and rejects unrelated origins where
  applicable;
- acceptance/debug mutation routes are unavailable anonymously;
- manual invoke is unavailable anonymously;
- no secrets are present in frontend static assets;
- rate limit/cooldown returns safe behavior;
- health/release metadata shows the intended release;
- page refresh/SSE reconnect preserves run state.

## 9E.5 Final status

Phase 9 can be declared PASS only when:

- final deterministic release gate is green;
- all three scenarios are usable from the public demo;
- public security checks pass;
- README and architecture package are current;
- deployed release identity is recorded;
- no known blocker prevents a normal portfolio walkthrough.

Final project status:

> **Autonomous L1 Incident Agent — PORTFOLIO DEMO COMPLETE / PUBLICLY DEPLOYED**

---

# 10. Hard invariants carried into Phase 9

1. Product business event is persisted before agent dispatch.
2. One Product Run maps to one persistent native ADK Session where defined by
   the scenario contract.
3. Product owns business truth and Evidence.
4. ADK owns generic runtime/session/invocation continuity.
5. Hidden chain-of-thought is not Product state, audit state or UI.
6. Trusted tenant/run context is not selected by the model.
7. Tool/provider failure is not Evidence.
8. Human approval remains authoritative for side effects.
9. Product revalidates stale/current truth before execution where required.
10. Replay/retry cannot duplicate business execution.
11. Restart/reconnect recovers from persisted Product/ADK state.
12. Scenario 1/2/3 business semantics are not rewritten for UI convenience.
13. No browser-side agent orchestration.
14. No second generic runtime/session framework.
15. Public-demo hardening must not weaken deterministic acceptance semantics.

---

# 11. Explicit out of scope

Phase 9 does **not** include unless a reproducible release blocker proves it
necessary:

- Scenario 4;
- new diagnostic/business tools merely for breadth;
- real ServiceNow integration;
- real Zabbix integration;
- real CMDB integration;
- real payment-provider integration;
- production field-service dispatch;
- multi-agent orchestration;
- replacing Google ADK;
- replacing Gemini;
- replacing PostgreSQL;
- changing Northflank/Vercel only for aesthetics;
- full enterprise authentication platform;
- user registration/login;
- enterprise RBAC/SSO;
- billing;
- analytics warehouse;
- distributed tracing platform;
- Kubernetes migration;
- horizontal-scale redesign;
- generic workflow engine;
- Product-side hardcoded agent planning;
- storing hidden model reasoning.

If one of these becomes necessary, document the blocking requirement before
changing scope.

---

# 12. Recommended implementation sequence

## 9A

Frontend/product presentation:

- add Scenario 2 public launcher/view;
- final three-scenario selector;
- new simulation flow;
- light/white visual redesign;
- complete user-visible states;
- frontend tests.

## 9B

Public safety/ops:

- explicit public-demo environment;
- acceptance/manual-invoke protection;
- demo tenant policy;
- server-side Gemini start-rate protection;
- release metadata;
- structured safe logging;
- security tests.

## 9C

Release gate:

- full deterministic regression;
- all three browser paths;
- recovery/error behavior;
- public-mode security regression;
- build/audit/Docker/Alembic gate.

## 9D

Portfolio package:

- rewrite README;
- architecture diagram;
- scenario comparison/flows;
- local/deployment docs;
- final limitations;
- cumulative handoff draft.

## 9E

Release:

- deploy exact SHA;
- public browser smoke of all three scenarios;
- public security smoke;
- record deployment evidence;
- finalize cumulative handoff;
- declare portfolio demo complete.

---

# 13. Phase 9 acceptance matrix

| Requirement | 9A | 9B | 9C | 9D | 9E |
| --- | :---: | :---: | :---: | :---: | :---: |
| Three-scenario launcher | X |  | X | X | X |
| Scenario 2 browser demo | X |  | X | X | X |
| Dark-default UI + optional light theme | X |  | X |  | X |
| Loading/empty/error/reconnect states | X |  | X |  | X |
| New simulation without deleting history | X |  | X | X | X |
| Acceptance/debug routes protected |  | X | X | X | X |
| Honest demo tenant policy |  | X | X | X | X |
| Server-side Gemini abuse/rate protection |  | X | X | X | X |
| Explicit CORS/env hardening |  | X | X | X | X |
| Release SHA/version observability |  | X | X | X | X |
| Full deterministic regression |  |  | X |  | X |
| Current README |  |  |  | X | X |
| Architecture diagram |  |  |  | X | X |
| Public Vercel/Northflank release |  |  |  |  | X |
| Live browser smoke Scenario 1/2/3 |  |  |  |  | X |

---

# 14. Definition of DONE

Phase 9 is DONE only when all of the following are true:

1. all three completed scenarios are available through the final browser
   experience;
2. the carried light/white UI debt is closed by an optional light theme while the dark theme remains the default;
3. user-visible failure/recovery states are intentional;
4. a new simulation never destroys previous audit history;
5. public deployment does not expose acceptance/debug mutation controls;
6. public demo cannot freely select arbitrary tenant identity;
7. Gemini-triggering actions have server-side public-demo rate protection;
8. CORS/public env/static secret audits pass;
9. release SHA/version is observable;
10. deterministic Scenario 1/2/3 and full regression gates pass;
11. README reflects the actual completed architecture;
12. architecture/scenario diagrams exist;
13. final Vercel + Northflank deployment runs the verified release;
14. public smoke passes for Scenario 1, Scenario 2 and Scenario 3;
15. final cumulative handoff records exact release/deployment evidence.

---

# 15. Next executor instruction

Start **Phase 9A only**.

Do not simultaneously redesign backend security, documentation and deployment
while doing the UI slice.

Phase 9A should first deliver:

1. three-scenario public launcher;
2. Scenario 2 browser integration using existing Product APIs;
3. final dark-default visual system with an optional light/white theme;
4. New simulation / return-to-scenarios behavior without destructive reset;
5. complete loading/empty/error/reconnect states;
6. deterministic frontend/API coverage for the new UI behavior.

Preserve all Phase 0–8 business/runtime invariants.

After Phase 9A passes, issue implementation notes and begin 9B.
