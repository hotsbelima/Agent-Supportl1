"""HTTP boundary for the Phase 2 runtime check; intentionally not a product API."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from phase1_adk_spike.contracts import MODEL

from .service import Phase2ProbeService


class FollowUpRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1_000)


def create_app(service: Phase2ProbeService | None = None) -> FastAPI:
    app = FastAPI(
        title="ALP ITSM Phase 2 Probe",
        version="0.1.0",
        description="Ephemeral FastAPI + ADK runtime check. No DB, UI, SSE or approvals.",
    )
    app.state.probe_service = service or Phase2ProbeService()

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "phase": 2,
            "model": MODEL,
            "google_api_key_configured": app.state.probe_service.api_key_available(),
        }

    @app.post("/spike/runs", status_code=status.HTTP_201_CREATED)
    async def start_run() -> dict[str, object]:
        if not app.state.probe_service.api_key_available():
            raise HTTPException(status_code=503, detail="GOOGLE_API_KEY is not configured")
        return (await app.state.probe_service.start()).as_dict()

    @app.get("/spike/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, object]:
        probe = app.state.probe_service.get(run_id)
        if not probe:
            raise HTTPException(status_code=404, detail="Probe run not found")
        return probe.as_dict()

    @app.post("/spike/runs/{run_id}/messages")
    async def follow_up(run_id: str, request: FollowUpRequest) -> dict[str, object]:
        if not app.state.probe_service.api_key_available():
            raise HTTPException(status_code=503, detail="GOOGLE_API_KEY is not configured")
        probe = await app.state.probe_service.follow_up(run_id, request.text)
        if not probe:
            raise HTTPException(status_code=404, detail="Probe run not found")
        return probe.as_dict()

    return app


app = create_app()
