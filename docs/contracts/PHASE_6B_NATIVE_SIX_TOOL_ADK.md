# Phase 6B — Native six-tool ADK wiring

Status: IMPLEMENTED, NOT YET TESTED.

Baseline: Phase 6A final commit
`f0c2f9c8f3c37656146155ecbcf7f90fbae872a9`.

## Runtime composition

- one native Google ADK `LlmAgent`;
- model: `gemini-3.5-flash-lite`;
- one native ADK `Runner`;
- persistent Phase 6A `DatabaseSessionService`;
- one Product-backed tool adapter;
- exactly six model-visible ADK function tools.

No second executor, session store, retry loop or runtime trace store is introduced.

## Native tools

The registered callables are:

1. `get_device(device_id)`
2. `get_site_health(site_id)`
3. `run_diagnostic(diagnostic_type, target_id)`
4. `search_incidents(scope, entity_id)`
5. `search_kb(query)`
6. `propose_field_visit(incident_id, device_id, diagnosis, evidence_ids, rationale)`

ADK builds the model-visible function declarations from the Python callables,
docstrings and type hints. `ToolContext` is framework-injected and is not a
model-visible argument.

Trusted Product context is derived as:

- Product `tenant_id = ToolContext.user_id`;
- Product `run_id = ToolContext.session.id`.

The model never chooses tenant or run identifiers.

## Product boundary

The wrappers adapt ADK arguments into the existing typed Product contracts and
delegate to `DefaultScenario1ToolAdapter`.

Evidence creation, provenance, TTL/currentness checks, proposal validation and
business transitions remain in the existing Product application/domain layer.

Tool results are serialized through the existing `to_tool_payload` boundary.
No Product business entity is copied into ADK session state.

## Retry policy

`ProductRetryableToolPlugin` subclasses ADK's native
`ReflectAndRetryToolPlugin` only to extract Product policy from returned
`DomainError.retryable`.

- `retryable=true`: ADK owns retry/reflection lifecycle;
- `retryable=false`: the plugin does not trigger automatic retry;
- source-system/network transport retry remains outside the agent-level plugin.

The agent instruction also explicitly forbids automatic repetition of
non-retryable Product failures.

## Tool order and downstream arguments

No tool order is encoded in Python. The agent instruction tells Gemini to choose
tools and order from observed evidence.

The instruction explicitly forbids inventing downstream identifiers and requires
attachment/evidence/etc. identifiers to come from the operational signal or
previous tool results.

This is implemented structurally but has **not yet been empirically verified**
with Gemini in Phase 6B testing.

## Product API integration

New endpoint:

`POST /api/v1/runs/{run_id}/agent/invoke`

The endpoint:

- requires the existing trusted `X-Tenant-ID` context;
- requires an existing Product Run in `ACTIVE` state;
- requires `GOOGLE_API_KEY`;
- sends a safe operational signal containing Scenario 1 incident facts;
- invokes the native ADK Runner in the persistent Run-correlated ADK Session;
- returns only safe top-level invocation metadata and the non-thought final
  answer;
- refreshes and returns the Product run status after the invocation.

No raw ADK event stream, prompt internals or hidden reasoning are copied into
Product `application_events`.

## Phase 6C boundary

`propose_field_visit` remains an ordinary Phase 6B FunctionTool and still only
creates a Product `PENDING_APPROVAL` proposal.

Phase 6B does **not** implement:

- `LongRunningFunctionTool`;
- persisted proposal -> invocation/function-call correlation;
- ADK pause after proposal creation;
- Approve/Reject -> ADK resume;
- durable outbox resume dispatch.

Those belong to Phase 6C.

## Verification status

Per explicit project-owner instruction, no Phase 6B tests have been added or
run yet.

Therefore this branch must not be called Phase 6B PASS until a later test step
verifies at minimum:

- the six tool declarations produced by ADK;
- a real Gemini invocation;
- model-selected (not scripted) tool order;
- downstream arguments derived from previous tool results;
- retryable vs non-retryable behavior;
- evidence persistence through Product services;
- proposal creation semantics;
- Phase 3/4/5/6A regression.
