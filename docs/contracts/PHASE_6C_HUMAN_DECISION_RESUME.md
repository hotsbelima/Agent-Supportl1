# Phase 6C — native ADK human decision pause/resume

Status: **IMPLEMENTED, NOT YET TESTED**.

Baseline: Phase 6B PASS commit
`cc7e6be3cb5ffa967839520451fefd5d65cc5ee5`.

Development branch:
`phase-6c-human-decision-resume`.

## Goal

Complete the Scenario 1 human-in-the-loop boundary without moving Product
approval semantics into Google ADK:

```text
Gemini / native ADK
  -> Product propose_field_visit
  -> Product persists PENDING_APPROVAL and Run WAITING_APPROVAL
  -> native ADK long-running wait point pauses the invocation
  -> human Approve/Reject through the existing Product API/UI
  -> Product revalidates and commits the durable decision / side effect
  -> actual Product result is returned to the same ADK invocation
  -> native ADK resumes and produces an honest final response
```

## Why propose_field_visit is not LongRunningFunctionTool

Pinned Google ADK 2.10.0 marks a long-running function call on the model
function-call Event. In a resumable app, ADK pauses immediately after that Event,
before the long-running callable is executed.

Therefore wrapping `propose_field_visit` itself in
`LongRunningFunctionTool` would pause before Product creates the proposal.
That violates the canonical Product semantics: the proposal must already exist
as `PENDING_APPROVAL` before a human sees it.

Phase 6C instead preserves `propose_field_visit` as the ordinary Product tool,
then exposes one integration control tool:

`await_human_decision(proposal_id)`

It is a native ADK `LongRunningFunctionTool`. The agent instruction requires
calling it exactly once immediately after a successful pending proposal. At that
point the Product proposal is already durable, and ADK can pause natively.

The six Scenario 1 Product tools remain unchanged and Product-backed. The wait
tool is not a seventh Product/business tool; it is the ADK runtime integration
point for external human input.

## Native resumability

The ADK `App` now uses:

`ResumabilityConfig(is_resumable=True)`

The existing persistent `DatabaseSessionService` remains the source of truth
for ADK Session/Events/runtime state. No custom session store or pause/resume
engine was added.

Resume uses the pinned ADK native contract:

- same `user_id = tenant_id`;
- same `session_id = run_id`;
- original `invocation_id`;
- original `await_human_decision` function-call id;
- user-authored `FunctionResponse` carrying the committed Product result.

## Persistent correlation

No new Product table is used for agent-runtime correlation.

The minimal durable correlation already exists in the native persistent ADK
Event stream:

- Product `proposal_id` is the argument of `await_human_decision`;
- ADK Event owns `invocation_id`;
- ADK FunctionCall owns the function-call id;
- the established Phase 6A relation keeps `session_id = run_id`.

The runtime resolves the proposal-to-invocation link by reading those persisted
ADK Events. Product business entities are not moved into ADK session state.

## Human decision ownership

The existing Product Approve/Reject endpoints and
`FieldVisitApprovalService` remain authoritative.

The order is intentionally:

1. Product validates/revalidates and **commits** the human decision.
2. Product idempotency/business side effects complete.
3. Only then does the API attempt ADK resume.

This preserves all Phase 4 semantics:

- Reject: Approval REJECTED, proposal REJECTED, Run ACTIVE, zero execution.
- Valid Approve: exactly one ExecutedAction + one WorkOrder, proposal EXECUTED,
  incident ESCALATED, Run ACTIVE.
- Stale Approve: Approval APPROVED + proposal STALE, zero execution.
- Retryable upstream revalidation failure consumes no human decision.
- Identical replay returns the stored Product result.
- Conflicting human decision does not execute a second side effect.

Approve/Reject are still not model tools.

## Result returned to ADK

The resume FunctionResponse contains only a safe, minimal Product result:

- human decision;
- proposal id/status;
- incident id/status;
- executed action id/type when one exists;
- work-order id and operational target references when one exists;
- `repair_confirmed=false`;
- whether the Product decision was replayed.

The agent instruction forbids further tool calls after resume and requires the
final answer to distinguish rejection, stale/no-execution, and registered
execution/work-order state. A work order is never reported as proof of repair.

## Crash/retry reconciliation

ADK 2.10 resumability is best-effort and at-least-once, so Phase 6C preserves
Product idempotency and explicitly handles the commit-to-resume gap.

### Product committed, ADK decision response not yet delivered

If the process/provider fails after Product commit but before the matching ADK
FunctionResponse is persisted, the existing Approve/Reject endpoint can be
replayed. Product returns the same stored decision and the API attempts native
resume again.

### ADK FunctionResponse persisted, continuation did not complete

If the FunctionResponse is already present in native ADK Events but the resumed
invocation did not finish (for example provider quota fails afterward), replay
does **not** inject the decision response a second time. It calls native
resumability for the same invocation with `new_message=None`, continuing from
persisted history.

### ADK continuation already completed

If the persisted event stream proves the decision response was delivered and
the invocation subsequently completed, replay does not resume it again. The API
returns `agent_resume.status = already_resumed`.

### Resume failure at the HTTP boundary

A resume/provider failure after Product commit does not turn the durable
business decision into an HTTP business failure. The approval response is
returned with:

`agent_resume.status = deferred`

and `retryable = true`.

Replaying the same idempotent Approve/Reject operation is the explicit
reconciliation path.

Because there is already a concrete replay/reconciliation strategy, Phase 6C
does **not** activate the legacy `application_outbox`. A dedicated durable
resume outbox/consumer should be added only if testing proves endpoint replay is
insufficient for the product reliability target.

## Product API changes

Health moves to checkpoint `6C` and reports native ADK resumability readiness.

Initial agent invocation additionally reports:

- `awaiting_human_decision`;
- `pending_proposal_id`.

Approve/Reject responses additionally report `agent_resume`:

- `resumed`;
- `already_resumed`;
- `deferred`.

The frontend/SSE Product business timeline remains unchanged.

## Explicit non-goals / preserved boundaries

Phase 6C does not add:

- a custom generic session store;
- a custom pause/resume framework;
- a second agent execution engine;
- a custom generic retry loop;
- a Product-owned copy of ADK runtime state;
- a generic application-event outbox producer;
- Approve/Reject as model tools;
- Phase 6D E2E acceptance logic.

## Verification status

Per project-owner instruction, Phase 6C was implemented **without tests**.

At this checkpoint:

- no Phase 6C test was added;
- no pytest/regression suite was run for Phase 6C;
- no live Gemini pause/resume run was performed;
- no Northflank Phase 6C acceptance was performed.

Therefore Phase 6C must **not** be called PASS yet.

The next step is review + deterministic/integration tests + real managed
pause/Approve-or-Reject/resume acceptance, including restart/replay failure
windows.
