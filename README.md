# Autonomous L1 Incident Agent

## Current scope — Phases 1–2, Google ADK + Gemini

This repository contains a deliberately small **Google ADK function-tool** spike. Phase 1 proved the local ADK/Gemini dependency chain; Phase 2 proved the same runtime on Northflank. It is not the Scenario 1 backend: there is no database, UI, SSE stream, approval flow, persistent workflow or production API.

The retained `api/`, `public/`, and `docs/handoff` Dify files are historical evidence only; the current spike does not call them.

### Pinned runtime

| Component | Pin |
| --- | --- |
| Python | `3.12.14` (`.python-version`) |
| Google ADK | `2.10.0` (`requirements.txt`) |
| Gemini | `gemini-3.5-flash-lite` (stable model ID) |
| FastAPI host probe | `fastapi==0.141.1`, `uvicorn==0.54.0` |
| Test runner | `pytest==8.4.2` |

### Exact tool boundary

The ADK agent has exactly two ordinary Python function tools and no others.

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
[`docs/handoff/ALP_ITSM_Agent_Handoff_v5.5_Cumulative.md`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.5_Cumulative.md).
The final-stage entry points are
[`Phase 1 Implementation Notes`](docs/phases/phase-1/final-stage/IMPLEMENTATION_NOTES.md)
and [`Phase 2 Final Stage`](docs/phases/phase-2/final-stage/README.md).
The phase documents are retained as deltas/evidence:
[`v5.4 — Phase 1`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.4_Phase_1_Update.md)
and [`v5.5 — Phase 2`](docs/handoff/ALP_ITSM_Agent_Handoff_v5.5_Phase_2_Update.md).
The fixed Phase 2 spike contracts are in
[`docs/contracts/PHASE_2_TOOL_AND_DOMAIN_CONTRACTS.md`](docs/contracts/PHASE_2_TOOL_AND_DOMAIN_CONTRACTS.md).
