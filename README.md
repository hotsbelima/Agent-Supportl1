# Autonomous L1 Incident Agent

## Current scope — Phase 3 PASS

Phases 1–2 remain a deliberately small **Google ADK function-tool** spike: Phase 1 proved the local ADK/Gemini dependency chain and Phase 2 proved the same runtime on Northflank. Phase 3 now adds a separate `product_backend/` foundation for Scenario 1: domain contracts, deterministic evidence/proposal validation, human approval/execution semantics and concrete integration of the six product tool contracts. It still has no product PostgreSQL implementation, UI, SSE stream, persistent workflow, product HTTP approval endpoint or live six-tool ADK wiring.

The retained `api/`, `public/`, and historical Dify material are evidence only; neither the Phase 1/2 spike nor `product_backend/` uses Dify.

### Pinned runtime

| Component | Pin |
| --- | --- |
| Python | `3.12.14` (`.python-version`) |
| Google ADK | `2.10.0` (`requirements.txt`) |
| Gemini | `gemini-3.5-flash-lite` (stable model ID) |
| FastAPI host probe | `fastapi==0.141.1`, `uvicorn==0.54.0` |
| Test runner | `pytest==8.4.2` |

### Phase 1/2 live ADK spike boundary

The **currently live-wired Phase 1/2 ADK spike** has exactly two ordinary Python function tools and no others. This statement does not describe the six-tool Scenario 1 product contract, which is not wired to live ADK yet.

| Tool | Input | Output / dependency |
| --- | --- | --- |
| `get_device(device_id)` | `POS-KZN17-03` | Returns `attachment_id: ATT-KZN17-POS03-NIC` |
| `run_diagnostic(attachment_id)` | Must use the first result | Returns a read-only `LINK_DOWN` observation |

The complete initial event is in `phase1_adk_spike/contracts.py`; it intentionally includes no `attachment_id`. The application never invokes a tool itself or copies an ID into the second call. Gemini must choose both calls through the native ADK loop.

### Run it

Create an environment with Python 3.12.14, install the pinned dependencies, and create a local `.env` file (ignored by Git) containing exactly `GOOGLE_API_KEY=your_key`. Do not put a key into an issue, chat, trace, or committed file.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m phase1_adk_spike.runner --runs 3
```

Each real attempt uses one new native `InMemorySessionService` session and saves a redacted, audit-safe event trace under `traces/` plus a summary under `results/`. Traces retain only function calls, function results, final answers and failures; they deliberately omit model reasoning/thought fields. Generated run files are ignored by Git so credentials and transient reports are never committed.

The Phase 1 acceptance sample was run successfully on 3 October 2026: all three independent Gemini runs made exactly `get_device` followed by `run_diagnostic`, and each second argument matched the attachment ID returned by the preceding tool result. The updated handoff records the exact run and trace filenames.

The command returns non-zero when any observed call fails the acceptance check. With no `GOOGLE_API_KEY`, it makes no network/model request and records a `not_run` preflight report instead.

### Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The local tests validate the two-tool boundary, absence of `attachment_id` in initial input, the fixture dependency, and rejection of an invented second argument. They do not substitute for live Gemini execution.

For Phase 2 deployment verification, `Dockerfile` runs the minimal `phase2_backend` service on port 8080. Its `/health` endpoint exposes no credential, and `POST /spike/runs` returns audit-safe observed tool calls/results for this temporary runtime check.

For project context, start with the canonical cumulative handoff:
[`docs/handoff/ALP_ITSM_Agent_Handoff_v5.7_Cumulative.md`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.7_Cumulative.md).
The phase documents are retained as deltas/evidence:
[`v5.4 — Phase 1`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.4_Phase_1_Update.md)
and [`v5.5 — Phase 2`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.5_Phase_2_Update.md).
The fixed Phase 2 spike contracts are in
[`docs/contracts/PHASE_2_TOOL_AND_DOMAIN_CONTRACTS.md`](docs/contracts/PHASE_2_TOOL_AND_DOMAIN_CONTRACTS.md).


### Phase 3A contract checkpoint

The Phase 3A design checkpoint is documented in [`docs/contracts/PHASE_3A_DOMAIN_AND_TOOL_CONTRACTS.md`](docs/contracts/PHASE_3A_DOMAIN_AND_TOOL_CONTRACTS.md). It is historical and is superseded by the final Phase 3 contract. The `product_backend/` package is intentionally separate from `phase1_adk_spike/` and `phase2_backend/`; the verified spike code remains unchanged.


### Phase 3B deterministic domain checkpoint

Phase 3B adds:

- typed validation of the four required evidence classes for `LOCAL_ACCESS_LINK_FAILURE`;
- TTL enforcement for dynamic proposal evidence;
- proposal creation only after deterministic validation, with `PENDING_APPROVAL`;
- fresh trusted CMDB + access-link reads on human Approve;
- `APPROVED + stale conditions -> STALE` with zero execution;
- valid Approve -> exactly one `ExecutedAction` and one `FieldServiceWorkOrder`, incident `ESCALATED`;
- Reject -> `REJECTED`, no execution, incident stays open;
- replay of the same human decision returns the stored result and creates no duplicate action/work order.

The work order receives site/link fields derived from trusted CMDB topology; the model never supplies queue/address/engineer/work-order routing fields. Repository ports state the uniqueness requirements that the future PostgreSQL implementation must enforce transactionally.

For the product-domain checkpoint only:

```powershell
python -m pytest -q tests/test_phase3a_contracts.py tests/test_phase3b_domain_logic.py
```

Phase 3B intentionally does not add PostgreSQL, product FastAPI routes, SSE, UI, or six-tool ADK integration.


### Phase 3 final contract and handoff

The final Phase 3 contract is
[`docs/contracts/PHASE_3_DOMAIN_AND_TOOL_CONTRACTS.md`](docs/contracts/PHASE_3_DOMAIN_AND_TOOL_CONTRACTS.md).

Phase 3 completion evidence is recorded in
[`docs/handoff/ALP_ITSM_Agent_Handoff_v5.6_Phase_3_Update.md`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.6_Phase_3_Update.md).

The cumulative source of truth for the next implementation stage is now
[`docs/handoff/ALP_ITSM_Agent_Handoff_v5.7_Cumulative.md`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.7_Cumulative.md). Phase 4 is explicitly defined there as the persistent application backend foundation.

The final Phase 3 audit also moved ownership/provider orchestration out of the
model-facing adapter into `Scenario1ReadToolService`, moved pure type-aware ID/topology rules into `domain/read_model.py`, restored the Phase 2 top-level diagnostic fields, added explicit
JSON-safe tool-result serialization, hardened evidence timestamps and added
architecture tests against layer leakage and hardcoded fixture truth.

The Phase 3 CI gate compiles the product backend, runs the 3A/3B/3C
architecture/domain suite, then installs the pinned runtime dependencies and
runs the full Python and retained Node regression suites.

Final audited checkpoint:

- architecture/domain: **69 passed**;
- full Python regression: **77 passed, 1 dependency deprecation warning**;
- retained Node regression: **5 passed, 0 failed**;
- `pip check`: **No broken requirements found**.

### Phase 4A PostgreSQL persistence checkpoint

Branch `phase-4a-postgres-persistence` adds the first implementation pass of
the Phase 4A persistence layer defined by cumulative handoff v5.7:

- Alembic PostgreSQL schema for product-owned state;
- async SQLAlchemy repositories implementing the Phase 3 ports;
- transactional UoWs with row locking on proposal/approval mutation paths;
- DB uniqueness constraints for approval/action/work-order idempotency;
- typed Evidence <-> JSONB mapping;
- schema reservation for application events/outbox, without Phase 4B lifecycle logic.

Detailed design/status:
[`docs/contracts/PHASE_4A_POSTGRES_PERSISTENCE.md`](docs/contracts/PHASE_4A_POSTGRES_PERSISTENCE.md).

Phase 4A now has a PostgreSQL 16 CI gate covering migrations, repository
round-trip, tenant/run isolation, cross-context FK protection and concurrent
Approve idempotency. The verified result is 7/7 Phase 4A integration tests,
84/84 full Python tests (with the retained dependency warning) and 5/5 Node
tests. Managed Northflank infrastructure acceptance is still separate, and
Phase 4 itself is not PASS until 4B/4C and that final acceptance are complete.
\n

### Phase 4B persisted lifecycle checkpoint

Branch `phase-4b-persisted-lifecycle` adds the persisted lifecycle/audit layer
on top of verified Phase 4A:

- safe closed-set application event contracts;
- server-side UTC timestamps and monotonic per-run sequence;
- transactional one-event/one-outbox persistence;
- timeline cursor reads for the future SSE layer;
- tool start/finish audit;
- proposal, approval, action and run-status events;
- explicit protection against persisting hidden reasoning/credential fields.

PostgreSQL 16 CI is green: Phase 3 **69/69**, Phase 4A **7/7**, Phase 4B
**8/8**, full Python **92/92** (one retained dependency warning), Node
**5/5**.

Detailed checkpoint:
[`docs/contracts/PHASE_4B_PERSISTED_LIFECYCLE.md`](docs/contracts/PHASE_4B_PERSISTED_LIFECYCLE.md).

Phase 4 itself is not complete yet: Product FastAPI boundary 4C and the final
managed Northflank infrastructure acceptance remain.

### Phase 4C Product FastAPI checkpoint

Branch `phase-4c-product-api` adds the product HTTP/application boundary on
top of verified Phase 4A/4B:

- explicit Scenario 1 persistent start without Gemini/ADK;
- tenant/run-scoped current-state read;
- persisted event timeline read with cursor;
- human Approve/Reject delegated to the existing deterministic approval service;
- typed/safe HTTP errors;
- PostgreSQL-aware health endpoint;
- canonical Scenario 1 API composition kept outside `product_backend`.

Detailed checkpoint:
[`docs/contracts/PHASE_4C_PRODUCT_API.md`](docs/contracts/PHASE_4C_PRODUCT_API.md).

**Important:** by explicit instruction, Phase 4C has not been tested in this
implementation pass. No Phase 4C tests or CI verification were run. Current
status is `IMPLEMENTED / NOT TESTED`, not Phase 4 PASS.

