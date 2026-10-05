"""Persistent Product FastAPI boundary with Phase 5A SSE transport.

The API composes the persistent Phase 4 application services and exposes a
persisted server-sent event stream. Google ADK and the operational UI remain
out of scope until later checkpoints.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import os
import re
from typing import Annotated, Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, Path, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from product_backend.application.field_visit import FieldVisitApprovalService
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.results import OperationFailure
from product_backend.application.run_lifecycle import Scenario1RunStartService
from product_backend.application.run_state import RunStateService
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import ApprovalDecision
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
)
from product_backend.persistence.run_state import SqlAlchemyRunStateQuery
from product_backend.persistence.uow import (
    SqlAlchemyApprovalExecutionUnitOfWork,
    SqlAlchemyLifecycleUnitOfWork,
    SqlAlchemyRunStartUnitOfWork,
)

from .scenario1_fixture import Scenario1FixtureSources
from .schemas import (
    ApiErrorBody,
    ApiErrorResponse,
    ApprovalDecisionResponse,
    HumanDecisionRequest,
    RunStateResponse,
    TimelineResponse,
    approval_response,
    error_response,
    run_state_response,
    timeline_response,
)
from .sse import (
    HEARTBEAT_FRAME,
    SseSettings,
    application_event_sse_frame,
    frontend_origins_from_env,
    resolve_sse_cursor,
)


_TENANT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ID_PATH = Path(
    min_length=1,
    max_length=128,
    pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
)

_ERROR_RESPONSES = {
    status.HTTP_400_BAD_REQUEST: {"model": ApiErrorResponse},
    status.HTTP_404_NOT_FOUND: {"model": ApiErrorResponse},
    status.HTTP_409_CONFLICT: {"model": ApiErrorResponse},
    status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ApiErrorResponse},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ApiErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorResponse},
}


@dataclass(slots=True)
class ProductApiContainer:
    start_service: Scenario1RunStartService
    state_service: RunStateService
    lifecycle_service: ApplicationLifecycleService
    approval_service: FieldVisitApprovalService
    fixture: Scenario1FixtureSources
    engine: AsyncEngine | None = None

    async def close(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


def build_container_from_env() -> ProductApiContainer:
    settings = DatabaseSettings.from_env()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    fixture = Scenario1FixtureSources()

    return ProductApiContainer(
        start_service=Scenario1RunStartService(
            lambda: SqlAlchemyRunStartUnitOfWork(session_factory)
        ),
        state_service=RunStateService(
            SqlAlchemyRunStateQuery(session_factory)
        ),
        lifecycle_service=ApplicationLifecycleService(
            lambda: SqlAlchemyLifecycleUnitOfWork(session_factory)
        ),
        approval_service=FieldVisitApprovalService(
            lambda: SqlAlchemyApprovalExecutionUnitOfWork(session_factory),
            cmdb=fixture,
            monitoring=fixture,
        ),
        fixture=fixture,
        engine=engine,
    )


class ProductApiError(Exception):
    def __init__(self, *, status_code: int, body: ApiErrorResponse) -> None:
        super().__init__(body.error.code)
        self.status_code = status_code
        self.body = body


def _raise_api_error(
    *,
    status_code: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, str] | None = None,
) -> None:
    raise ProductApiError(
        status_code=status_code,
        body=ApiErrorResponse(
            error=ApiErrorBody(
                code=code,
                message=message,
                retryable=retryable,
                details=details or {},
            )
        ),
    )


def _domain_status(error: DomainError) -> int:
    if error.code in {
        ErrorCode.DEVICE_NOT_FOUND,
        ErrorCode.SITE_NOT_FOUND,
        ErrorCode.ATTACHMENT_NOT_FOUND,
        ErrorCode.INCIDENT_NOT_FOUND,
        ErrorCode.EVIDENCE_NOT_FOUND,
        ErrorCode.PROPOSAL_NOT_FOUND,
        ErrorCode.CONTEXT_MISMATCH,
    }:
        return status.HTTP_404_NOT_FOUND

    if error.code in {
        ErrorCode.UPSTREAM_UNAVAILABLE,
        ErrorCode.SITE_HEALTH_UNAVAILABLE,
        ErrorCode.DIAGNOSTIC_UNAVAILABLE,
        ErrorCode.INCIDENT_SEARCH_UNAVAILABLE,
        ErrorCode.KB_UNAVAILABLE,
    }:
        return status.HTTP_503_SERVICE_UNAVAILABLE

    if error.code in {
        ErrorCode.INVALID_PROPOSAL,
        ErrorCode.PROPOSAL_NOT_PENDING,
        ErrorCode.INVALID_STATE_TRANSITION,
        ErrorCode.EVIDENCE_EXPIRED,
        ErrorCode.EVIDENCE_CONTEXT_MISMATCH,
        ErrorCode.INSUFFICIENT_OR_INVALID_EVIDENCE,
    }:
        return status.HTTP_409_CONFLICT

    return status.HTTP_400_BAD_REQUEST


def _raise_domain_error(error: DomainError) -> None:
    raise ProductApiError(
        status_code=_domain_status(error),
        body=error_response(error),
    )


def _container(request: Request) -> ProductApiContainer:
    container = getattr(request.app.state, "product_container", None)
    if container is None:
        _raise_api_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="SERVICE_UNAVAILABLE",
            message="Product backend is not ready.",
            retryable=True,
        )
    return container


def _require_tenant_id(
    x_tenant_id: Annotated[
        str,
        Header(
            alias="X-Tenant-ID",
            min_length=1,
            max_length=128,
            description=(
                "Trusted demo tenant context. This is not an authentication "
                "mechanism; production auth must bind identity to tenant."
            ),
        ),
    ],
) -> str:
    tenant_id = x_tenant_id.strip()
    if not _TENANT_PATTERN.fullmatch(tenant_id):
        _raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_TENANT_CONTEXT",
            message="Tenant context is invalid.",
        )
    return tenant_id


TenantId = Annotated[str, Depends(_require_tenant_id)]


def create_app(
    container: ProductApiContainer | None = None,
    *,
    sse_settings: SseSettings | None = None,
    frontend_origins: tuple[str, ...] | None = None,
) -> FastAPI:
    resolved_sse_settings = sse_settings or SseSettings.from_env()
    resolved_frontend_origins = (
        frontend_origins
        if frontend_origins is not None
        else frontend_origins_from_env()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active = container or build_container_from_env()
        app.state.product_container = active
        try:
            yield
        finally:
            if container is None:
                await active.close()

    app = FastAPI(
        title="Autonomous L1 Incident Agent Product API",
        version="0.5.0",
        description=(
            "Phase 5A persistent application boundary with persisted SSE. "
            "No live Google ADK wiring yet."
        ),
        lifespan=lifespan,
    )
    app.state.sse_settings = resolved_sse_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_frontend_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "X-Tenant-ID",
            "Content-Type",
            "Accept",
            "Last-Event-ID",
        ],
    )

    @app.exception_handler(ProductApiError)
    async def product_api_error_handler(
        request: Request,
        exc: ProductApiError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.body.model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code="INVALID_ARGUMENT",
                message="Request validation failed.",
                retryable=False,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code="DATABASE_UNAVAILABLE",
                message="Persistent product state is temporarily unavailable.",
                retryable=True,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=body.model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        # Deliberately do not expose repr(exc), provider payloads, stack traces
        # or credentials at the HTTP boundary.
        body = ApiErrorResponse(
            error=ApiErrorBody(
                code="INTERNAL_ERROR",
                message="Unexpected server error.",
                retryable=True,
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=body.model_dump(mode="json"),
        )

    @app.get(
        "/health",
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ApiErrorResponse}
        },
    )
    async def health(request: Request) -> dict[str, Any]:
        services = _container(request)
        if services.engine is not None:
            async with services.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "phase": 5,
            "checkpoint": "5A",
            "database_configured": bool(os.environ.get("DATABASE_URL")),
            "database_reachable": True,
            "adk_wired": False,
            "sse_wired": True,
        }

    @app.post(
        "/api/v1/scenario-1/runs",
        response_model=RunStateResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
    )
    async def start_scenario1_run(
        request: Request,
        tenant_id: TenantId,
    ) -> RunStateResponse:
        services = _container(request)
        started = await services.start_service.start(
            tenant_id=tenant_id,
            bootstrap=services.fixture.bootstrap(),
        )

        snapshot = await services.state_service.get(
            tenant_id=tenant_id,
            run_id=started.run.run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STATE_PERSISTENCE_FAILED",
                message="Scenario 1 run state is unavailable after start.",
                retryable=True,
            )
        return run_state_response(snapshot)

    @app.get(
        "/api/v1/runs/{run_id}",
        response_model=RunStateResponse,
        responses=_ERROR_RESPONSES,
    )
    async def get_run_state(
        run_id: Annotated[str, _ID_PATH],
        request: Request,
        tenant_id: TenantId,
    ) -> RunStateResponse:
        services = _container(request)
        snapshot = await services.state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="RUN_NOT_FOUND",
                message="Run was not found in the current tenant context.",
            )
        return run_state_response(snapshot)

    @app.get(
        "/api/v1/runs/{run_id}/events",
        response_model=TimelineResponse,
        responses=_ERROR_RESPONSES,
    )
    async def get_run_events(
        run_id: Annotated[str, _ID_PATH],
        request: Request,
        tenant_id: TenantId,
        after_seq: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    ) -> TimelineResponse:
        services = _container(request)
        snapshot = await services.state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="RUN_NOT_FOUND",
                message="Run was not found in the current tenant context.",
            )

        events = await services.lifecycle_service.timeline(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            after_seq=after_seq,
            limit=limit,
        )
        return timeline_response(
            run_id=run_id,
            events=events,
            after_seq=after_seq,
        )

    @app.get(
        "/api/v1/runs/{run_id}/events/stream",
        responses=_ERROR_RESPONSES,
    )
    async def stream_run_events(
        run_id: Annotated[str, _ID_PATH],
        request: Request,
        tenant_id: TenantId,
        after_seq: Annotated[
            str | None,
            Query(description="Initial non-negative persisted event cursor."),
        ] = None,
        last_event_id: Annotated[
            str | None,
            Header(
                alias="Last-Event-ID",
                description="Reconnect cursor; takes precedence over after_seq.",
            ),
        ] = None,
    ) -> StreamingResponse:
        try:
            cursor = resolve_sse_cursor(
                last_event_id=last_event_id,
                after_seq=after_seq,
            )
        except ValueError:
            _raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="INVALID_CURSOR",
                message="Event cursor must be a non-negative integer.",
            )

        services = _container(request)
        snapshot = await services.state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="RUN_NOT_FOUND",
                message="Run was not found in the current tenant context.",
            )

        settings: SseSettings = request.app.state.sse_settings
        context = ToolCallContext(tenant_id=tenant_id, run_id=run_id)

        async def persisted_event_stream() -> AsyncIterator[str]:
            current_cursor = cursor
            loop = asyncio.get_running_loop()
            next_heartbeat = loop.time() + settings.heartbeat_interval_seconds

            while True:
                if await request.is_disconnected():
                    return

                try:
                    events = await services.lifecycle_service.timeline(
                        context,
                        after_seq=current_cursor,
                        limit=settings.batch_size,
                    )
                except Exception:
                    # Headers may already be committed. Never stream a raw
                    # DB/provider exception or credentials to the browser.
                    # Close and let the client recover from persisted state.
                    return

                if events:
                    for event in events:
                        if await request.is_disconnected():
                            return
                        yield application_event_sse_frame(event)
                        current_cursor = event.seq
                    next_heartbeat = (
                        loop.time() + settings.heartbeat_interval_seconds
                    )
                    continue

                now = loop.time()
                if now >= next_heartbeat:
                    yield HEARTBEAT_FRAME
                    next_heartbeat = now + settings.heartbeat_interval_seconds

                await asyncio.sleep(settings.poll_interval_seconds)

        return StreamingResponse(
            persisted_event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    async def decide(
        *,
        request: Request,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
        decision: ApprovalDecision,
        decided_by: str,
    ) -> ApprovalDecisionResponse:
        services = _container(request)
        result = await services.approval_service.decide(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            proposal_id=proposal_id,
            decision=decision,
            decided_by=decided_by,
        )
        if isinstance(result, OperationFailure):
            _raise_domain_error(result.error)
        return approval_response(result)

    @app.post(
        "/api/v1/runs/{run_id}/proposals/{proposal_id}/approve",
        response_model=ApprovalDecisionResponse,
        responses=_ERROR_RESPONSES,
    )
    async def approve_proposal(
        run_id: Annotated[str, _ID_PATH],
        proposal_id: Annotated[str, _ID_PATH],
        body: HumanDecisionRequest,
        request: Request,
        tenant_id: TenantId,
    ) -> ApprovalDecisionResponse:
        return await decide(
            request=request,
            tenant_id=tenant_id,
            run_id=run_id,
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by=body.decided_by,
        )

    @app.post(
        "/api/v1/runs/{run_id}/proposals/{proposal_id}/reject",
        response_model=ApprovalDecisionResponse,
        responses=_ERROR_RESPONSES,
    )
    async def reject_proposal(
        run_id: Annotated[str, _ID_PATH],
        proposal_id: Annotated[str, _ID_PATH],
        body: HumanDecisionRequest,
        request: Request,
        tenant_id: TenantId,
    ) -> ApprovalDecisionResponse:
        return await decide(
            request=request,
            tenant_id=tenant_id,
            run_id=run_id,
            proposal_id=proposal_id,
            decision=ApprovalDecision.REJECTED,
            decided_by=body.decided_by,
        )

    return app


app = create_app()


__all__ = [
    "ProductApiContainer",
    "app",
    "build_container_from_env",
    "create_app",
]
