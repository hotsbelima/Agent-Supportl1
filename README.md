# Autonomous L1 Incident Agent

A portfolio-grade autonomous L1 incident-management agent built with
**Google ADK + Gemini**, a persistent Product backend, PostgreSQL, HITL and a
three-scenario operational console.

The agent does not own business truth. It investigates through typed Product
tools, persists Evidence, proposes an action, waits for a human decision and
resumes against authoritative Product state.

## What this project demonstrates

- native Google ADK agent/tool execution;
- Gemini-driven tool selection and replanning;
- persisted Product state and Evidence;
- PostgreSQL-backed native ADK session continuity;
- durable outbox dispatch and restart recovery;
- human approval/rejection with native wait/resume;
- stale revalidation before execution;
- idempotent/exactly-once business effects;
- persisted SSE timeline and reconnect/backfill;
- final browser UI for three distinct scenarios;
- portfolio-grade public-demo hardening.

This is an **agent**, not a hard-coded workflow: the model chooses investigation
tools and can change its plan when Evidence contradicts a hypothesis. Product
code still owns validation, approval and execution boundaries.

## Three demo scenarios

| Scenario | Demonstrates | Human decision |
| --- | --- | --- |
| **1 — Local device incident** | CMDB + monitoring + local access-link diagnosis | Field Service visit |
| **2 — Multi-event service incident** | Multi-signal correlation, dependency/provider investigation | Major Incident |
| **3 — Evidence-driven replanning** | Provider hypothesis is disproved, then investigation switches to local diagnostics | Field Service visit |

See [docs/scenarios.md](docs/scenarios.md) for the observable flows.

## Architecture

```text
Next.js operational console
        |
        | HTTPS + persisted SSE
        v
FastAPI Product API
        |
        +--> Product application/domain services
        |       |
        |       +--> PostgreSQL business state + Evidence + events
        |       +--> durable outbox
        |       +--> HITL / stale / idempotency rules
        |
        +--> Google ADK runtimes
                |
                +--> Gemini
                +--> typed Product tools
                +--> native persistent ADK sessions
```

The key ownership rule is:

> **Product owns business truth; ADK owns generic agent runtime continuity.**

Detailed architecture: [docs/architecture.md](docs/architecture.md).

## Product flow

```text
operational event
    -> persisted Product state
    -> durable agent dispatch
    -> investigation / typed tools
    -> Evidence
    -> proposal
    -> human Approve / Reject
    -> deterministic Product execution
    -> persisted recovery/audit timeline
```

Hidden chain-of-thought is neither Product state nor UI content.

## Technology stack

| Layer | Technology |
| --- | --- |
| Agent runtime | Google ADK 2.10.0 |
| Model integration | Gemini |
| Backend | Python 3.12.14, FastAPI 0.141.1 |
| Persistence | PostgreSQL 16, SQLAlchemy 2.0.54, Alembic 1.20.0 |
| Frontend | Next.js 16.3.8, React 19.3.0, TypeScript 6.0.3 |
| Frontend tests | Vitest 5.0.3 |
| Packaging | Docker |

## Repository map

- `agent_runtime/` — native ADK agent/runtime/session integration.
- `product_backend/` — domain, application services, adapters and persistence.
- `product_api/` — FastAPI composition, HTTP/SSE boundary and dispatch workers.
- `frontend/` — final three-scenario operational console.
- `alembic/` — Product schema migrations.
- `tests/` — deterministic backend/integration regression.
- `docs/` — architecture, scenarios, phase notes and handoffs.

## Local backend

Requirements:

- Python 3.12.14;
- PostgreSQL;
- a Gemini API key only when running the live model path.

Install:

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Set at minimum:

```text
DATABASE_URL=postgresql+psycopg://...
FRONTEND_ORIGINS=http://localhost:3000
GOOGLE_API_KEY=<only for live Gemini execution>
```

Apply migrations and start the Product API:

```bash
python -m alembic upgrade head
python -m product_api
```

The default local API port is `8000` unless `PORT` is set.

## Local frontend

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

The frontend environment expects:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_DEMO_TENANT_ID=TENANT-8OCT
```

## Verification

Backend:

```bash
python -m pytest -q
python -m alembic current
python -m alembic check
docker build -f Dockerfile.product -t agent-supportl1 .
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
```

The final Phase 9C release gate combines the three scenarios, public-demo
security regression, full Python regression, frontend recovery/contracts,
static secret audit, Alembic and Docker build **without requiring a live Gemini
credential**.

## Public-demo guardrails

When `PUBLIC_DEMO=true`:

- the backend uses one server-side demo tenant;
- browser tenant input cannot select arbitrary tenant context;
- internal/manual/acceptance mutation routes are hidden;
- direct Scenario 2 raw signal ingestion is hidden;
- new demo runs use a simple server-side cooldown;
- CORS must use explicit exact origins;
- browser assets are audited for server secrets.

This is intentionally not an enterprise auth/RBAC implementation.

## Portfolio limitations

The demo uses controlled source adapters instead of real customer integrations
for monitoring, CMDB, ITSM, knowledge, provider health and operational side
effects.

Field Service work orders and Major Incidents are demo Product records; the
project does not change real customer infrastructure.

Gemini availability/quota is an external runtime dependency when the live model
path is used.

## Development status

> **PROJECT DEVELOPMENT COMPLETE**

All planned product functionality is implemented through Phase 9C and the
final deterministic release gate is green. Phase 9D packages the completed
system for portfolio review.

Deployment/publication can be performed separately and does not change the
development-completion boundary.

## Start here

- [Architecture](docs/architecture.md)
- [Three scenarios](docs/scenarios.md)
- [Final development handoff](docs/handoff/Autonomous_L1_Incident_Agent_Handoff_v8.0_Phase_9C_Final_Development.md)
- [Phase 9C deterministic release notes](docs/Phase_9C_Implementation_Notes.md)
