# Phase 7C native ADK dispatch

## Implemented boundary

Phase 7C now contains a dedicated durable consumer for
`agent.dispatch.scenario2-operational-signal`.

For every claimed envelope, it reloads the persisted Product application event,
`OperationalSignal`, signal-derived `OPERATIONAL_SIGNAL` Evidence and linked
`ServiceIncident` from PostgreSQL. The consumer then invokes the narrow native
Google ADK Scenario 2 agent once with that Product event identity.

The ADK correlation remains the Phase 6 deterministic mapping:

```text
Product (tenant_id, run_id) -> ADK (user_id, session_id)
```

`session_id` is the Product `run_id`. There is no Product-owned session table or
custom conversation store. Redelivery searches the persisted native ADK event
history for `product_event_id`: a settled invocation is returned as-is; an
incomplete invocation resumes through the same native ADK `invocation_id`.

The outbox is marked delivered only after the runtime reports a recoverable
native ADK state. The existing database head-of-line query keeps later events
of the same `(tenant, run, topic)` behind an undelivered/retrying earlier event.

## Scope deliberately retained for Phase 7C

The agent has no Scenario 2 tools and no mutation surface in this checkpoint.
Its instruction explicitly prohibits Major Incident creation and prohibits
inferring cross-site impact from the first or second same-site signal. This
proves event-by-event native Session continuity without moving the Phase 7D
correlation decision into Product ingestion.

## Focused checks added

`tests/test_phase7c_adk_dispatch.py` covers the durable bridge with a
deterministic runtime double plus real `DatabaseSessionService` persistence:

- three persisted facts dispatch in order as three independent runtime turns;
- a retrying first outbox row blocks the second row;
- one Product event identity resolves to one independent invocation identity on
  redelivery;
- a native ADK Session is retrievable after engine/service reconstruction;
- dispatch creates no Scenario 1 proposal or work order.

The test double is intentionally limited to deterministic outbox behavior. It
does not stand in for live Gemini acceptance.

## Acceptance status

This workspace has no `DATABASE_URL`, no PostgreSQL/Docker runtime, and no
`GOOGLE_API_KEY`. Therefore the live Gemini proof of three real invocations in
one persistent native ADK Session could not be performed here. Phase 7C must
not be called full PASS until that credentialed managed acceptance has been
run and recorded.

## Phase 7D remains

Phase 7D adds the read-only Scenario 2 model-visible tools, evidence-backed
correlation, `propose_major_incident`, approval/execution semantics and their
live end-to-end acceptance. The 7C consumer must remain the event delivery
boundary when those tools are added; it must not become a Product correlation
engine.
