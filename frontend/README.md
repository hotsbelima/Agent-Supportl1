# Phase 5 operational UI

This package is the Next.js App Router operational console for Scenario 1.

Public browser configuration:

- `NEXT_PUBLIC_API_BASE_URL` — direct Product API origin.
- `NEXT_PUBLIC_DEMO_TENANT_ID` — explicit trusted demo tenant context, not a secret.

The browser talks directly to FastAPI. SSE is read with streaming `fetch` so
`X-Tenant-ID` remains a request header. No Vercel proxy is used.

## Phase 5C recovery model

Browser/React state is not authoritative. A run page reconstructs from:

1. current Product state;
2. the complete persisted timeline, paginated from `after_seq=0`;
3. live persisted SSE after the last accepted sequence.

The client keeps a per-run persisted cursor. Live events are accepted only when
`seq == cursor + 1`; replay/duplicate events are ignored and sequence gaps
force persisted backfill before a new stream is opened.

On disconnect the UI keeps already-loaded state/timeline visible, uses bounded
exponential reconnect delays (0.5s, 1s, 2s, then 5s cap), rereads authoritative
state, backfills persisted events, and reconnects with the persisted cursor.
After repeated failures the transport state is shown as
`Offline/Unavailable` while retry continues.

Approve/Reject response loss is recovered by rereading authoritative state.
The UI does not infer failed execution merely because an HTTP response was
lost; Phase 4 decision idempotency makes an explicit retry safe.

The real Northflank restart/browser proof remains Phase 5D2.
