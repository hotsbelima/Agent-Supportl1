# Phase 6A — Native ADK Persistence Boundary

Status: implementation contract for the Phase 6A gate.

## Ownership

| Concern | Owner after Phase 6A | Implementation |
| --- | --- | --- |
| ADK Session / runtime Event / runtime state | Google ADK | `DatabaseSessionService` |
| PostgreSQL engine / pool | shared infrastructure | ADK receives the existing Product `AsyncEngine` via `db_engine=` |
| Product Run / Incident / Evidence | Product | existing application/domain/persistence services |
| ActionProposal / Approval / ExecutedAction / WorkOrder | Product | existing Phase 4 services and idempotency constraints |
| Business audit events | Product | `application_events` |
| Generic tool execution lifecycle | ADK | Product adapters no longer emit `tool.started/tool.finished` |
| UI runtime projection | future integration glue | may project safe ADK events into Product timeline, never a source of execution truth |

## Run to ADK Session correlation

Correlation is deterministic and stores references rather than Product entities in
ADK state:

- ADK `app_name = autonomous-l1-incident-agent`;
- ADK `user_id = Product tenant_id`;
- ADK `session_id = Product run_id`.

`ensure_run_session` is idempotent and handles concurrent deterministic-create
races by re-reading the winning native ADK session.

## Database ownership

ADK runtime tables are created and managed by `DatabaseSessionService`:

- `adk_internal_metadata`;
- `sessions`;
- `events`;
- `app_states`;
- `user_states`.

Product Alembic explicitly excludes these reflected tables from Product schema
autogeneration/checks. No Product migration defines them.

## application_outbox decision

The Phase 4 `application_outbox` table is retained because already-applied
migrations are forward-only. Phase 6A **deprecates and disables the old generic
`application.event` producer** because it had no consumer and therefore was
unused runtime plumbing.

No new generic outbox rows are created in Phase 6A.

For Phase 6C there are only two permitted outcomes:

1. once persisted `session_id / invocation_id / function-call id` correlation
   exists, add a **dedicated** approval-commit -> ADK-resume outbox topic plus an
   idempotent consumer/reconciliation path; or
2. if durable resume does not need the table, keep it deprecated and remove it
   later only through a new forward Alembic migration after regression and
   managed verification.

The generic `application.event` producer must not be restored.

## Phase 6A gate evidence

Automated gate must prove:

- native ADK Session persists across a fresh engine/process boundary;
- ADK runtime event/state persists across the same boundary;
- the Product container and ADK session service share the same `AsyncEngine`;
- Product metadata does not claim ADK runtime tables;
- repeated/concurrent `ensure_run_session` resolves to one native ADK Session;
- no generic Product tool lifecycle events are manufactured;
- Product approval/idempotency regressions remain green;
- Product Alembic remains clean after ADK creates its runtime tables;
- Phase 3/4/5 Python/frontend regressions and Product Docker build remain green.

Phase 6B may start only from a commit for which this gate is green.
