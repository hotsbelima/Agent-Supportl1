# Phase 5B operational UI

This package is the Next.js App Router operational console for Scenario 1.

Public browser configuration:

- `NEXT_PUBLIC_API_BASE_URL` — direct Product API origin.
- `NEXT_PUBLIC_DEMO_TENANT_ID` — trusted demo tenant context, not a secret.

The browser talks directly to FastAPI. SSE is read with streaming `fetch` so
`X-Tenant-ID` remains a request header. No Vercel proxy is used.

Phase 5B intentionally does not implement the Phase 5C gap-recovery and
exponential reconnect state machine. If a stream closes, the UI preserves the
persisted snapshot/timeline already on screen and reports the connection as
unavailable.
