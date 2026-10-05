"""Persistent Product API boundary with Phase 6C native ADK resumability.

Product business state and human decisions remain in the existing
application/domain layer. Google ADK owns agent execution, persistent runtime
sessions/events, the long-running wait point and invocation resume mechanics.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
import logging
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
from google.adk.sessions import DatabaseSessionService

from agent_runtime.service import Scenario1AgentRuntime
from agent_runtime.sessions import create_database_session_service
from agent_runtime.sessions import ensure_run_session
from product_backend.adapters.tool_adapters import DefaultScenario1ToolAdapter
from product_backend.application.field_visit import (
    FieldVisitApprovalService,
    FieldVisitProposalService,
)
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.read_tools import (
    EvidenceTtlPolicy,
    Scenario1ReadToolService,
)
from product_backend.application.results import ApprovalProcessed, OperationFailure
from product_backend.application.run_lifecycle import Scenario1RunStartService
from product_backend.application.run_state import RunStateService
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import ApprovalDecision, RunStatus
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
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyRunStartUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)

from .scenario1_fixture import Scenario1FixtureSources
from .schemas import (
    AgentInvocationResponse,
    AgentResumeView,
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


logger = logging.getLogger(__name__)


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
    adk_session_service: DatabaseSessionService | None = None
    agent_runtime: Scenario1AgentRuntime | None = None

    async def close(self) -> None:
        if self.agent_runtime is not None:
            await self.agent_runtime.close()
        if self.engine is not None:
            await self.engine.dispose()


def build_container_from_env() -> ProductApiContainer:
    settings = DatabaseSettings.from_env()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    fixture = Scenario1FixtureSources()
    adk_session_service = create_database_session_service(engine)

    read_service = Scenario1ReadToolService(
        read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(session_factory),
        cmdb=fixture,
        monitoring=fixture,
        itsm=fixture,
        kb=fixture,
        ttl_policy=EvidenceTtlPolicy(
            site_health=timedelta(minutes=5),
            access_link_diagnostic=timedelta(minutes=2),
        ),
    )
    proposal_service = FieldVisitProposalService(
        lambda: SqlAlchemyProposalCreationUnitOfWork(session_factory)
    )
    tool_adapter = DefaultScenario1ToolAdapter(
        read_service=read_service,
        proposal_service=proposal_service,
    )
    agent_runtime = Scenario1AgentRuntime(
        adapter=tool_adapter,
        session_service=adk_session_service,
    )

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
        adk_session_service=adk_session_service,
        agent_runtime=agent_runtime,
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


def _agent_decision_payload(result: ApprovalProcessed) -> dict[str, Any]:
    """Build the minimal safe Product result returned to the paused ADK call."""
    executed_action = (
        {
            "action_id": result.executed_action.action_id,
            "action_type": result.executed_action.action_type.value,
        }
        if result.executed_action is not None
        else None
    )
    work_order = (
        {
            "work_order_id": result.work_order.work_order_id,
            "site_id": result.work_order.site_id,
            "device_id": result.work_order.device_id,
            "switch_id": result.work_order.switch_id,
            "port_id": result.work_order.port_id,
        }
        if result.work_order is not None
        else None
    )
    return {
        "status": "human_decision_committed",
        "decision": result.approval.decision.value,
        "proposal_id": result.proposal.proposal_id,
        "proposal_status": result.proposal.status.value,
        "incident_id": result.incident.incident_id,
        "incident_status": result.incident.status.value,
        "executed_action": executed_action,
        "work_order": work_order,
        "repair_confirmed": False,
        "replayed": result.replayed,
    }


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
            if active.adk_session_service is not None:
                await active.adk_session_service.prepare_tables()
            yield
        finally:
            if container is None:
                await active.close()

    app = FastAPI(
        title="Autonomous L1 Incident Agent Product API",
        version="0.6.2",
        description=(
            "Phase 6C product boundary with native Google ADK resumability: "
            "six Product-backed Scenario 1 tools plus one long-running human "
            "decision wait point."
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
            "phase": 6,
            "checkpoint": "6C",
            "database_configured": bool(os.environ.get("DATABASE_URL")),
            "database_reachable": True,
            "adk_wired": services.agent_runtime is not None,
            "adk_session_persistence_wired": services.adk_session_service is not None,
            "adk_resumability_wired": (
                services.agent_runtime.resumability_wired
                if services.agent_runtime is not None
                else False
            ),
            "gemini_configured": (
                services.agent_runtime.gemini_configured
                if services.agent_runtime is not None
                else False
            ),
            "adk_model": (
                services.agent_runtime.model
                if services.agent_runtime is not None
                else None
            ),
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
        if services.adk_session_service is not None:
            await ensure_run_session(
                services.adk_session_service,
                tenant_id=tenant_id,
                run_id=started.run.run_id,
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

    @app.post(
        "/api/v1/runs/{run_id}/agent/invoke",
        response_model=AgentInvocationResponse,
        responses=_ERROR_RESPONSES,
    )
    async def invoke_scenario1_agent(
        run_id: Annotated[str, _ID_PATH],
        request: Request,
        tenant_id: TenantId,
    ) -> AgentInvocationResponse:
        services = _container(request)
        if services.agent_runtime is None:
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="AGENT_RUNTIME_UNAVAILABLE",
                message="Google ADK agent runtime is not configured.",
                retryable=True,
            )
        if not services.agent_runtime.gemini_configured:
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="GEMINI_NOT_CONFIGURED",
                message="Gemini credentials are not configured for the agent runtime.",
                retryable=False,
            )

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
        if snapshot.run.status is not RunStatus.ACTIVE:
            _raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="RUN_NOT_ACTIVE",
                message="Agent invocation requires an ACTIVE run.",
            )

        operational_signal = {
            "scenario_id": snapshot.run.scenario_id,
            "incidents": [
                {
                    "incident_id": incident.incident_id,
                    "site_id": incident.site_id,
                    "reported_device_id": incident.reported_device_id,
                    "symptom": incident.symptom,
                    "status": incident.status.value,
                }
                for incident in snapshot.incidents
            ],
        }

        result = await services.agent_runtime.invoke(
            tenant_id=tenant_id,
            run_id=run_id,
            operational_signal=operational_signal,
        )

        refreshed = await services.state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if refreshed is None:
            _raise_api_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STATE_PERSISTENCE_FAILED",
                message="Run state is unavailable after agent invocation.",
                retryable=True,
            )

        return AgentInvocationResponse(
            run_id=run_id,
            session_id=result.session_id,
            invocation_id=result.invocation_id,
            model=services.agent_runtime.model,
            run_status=refreshed.run.status.value,
            final_answer=result.final_answer,
            awaiting_human_decision=result.awaiting_human_decision,
            pending_proposal_id=result.pending_proposal_id,
        )

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

        # Product commits the human decision and any idempotent business side
        # effect first. ADK resume is intentionally post-commit: a provider or
        # runtime failure must never make the durable Product decision appear
        # rolled back to the caller.
        result = await services.approval_service.decide(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            proposal_id=proposal_id,
            decision=decision,
            decided_by=decided_by,
        )
        if isinstance(result, OperationFailure):
            _raise_domain_error(result.error)

        agent_resume = AgentResumeView(
            status="deferred",
            retryable=True,
        )
        if services.agent_runtime is not None:
            try:
                resumed = await services.agent_runtime.resume_human_decision(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    proposal_id=proposal_id,
                    decision_payload=_agent_decision_payload(result),
                )
            except Exception:
                # The Product decision is already committed. Returning it with
                # deferred resume preserves business truth. Replaying the same
                # existing Approve/Reject endpoint is the reconciliation path:
                # Product idempotency replays the stored decision, while native
                # ADK event history prevents duplicate FunctionResponse delivery.
                logger.warning(
                    "Native ADK resume deferred for run=%s proposal=%s",
                    run_id,
                    proposal_id,
                )
            else:
                agent_resume = AgentResumeView(
                    status=(
                        "already_resumed"
                        if resumed.already_resumed
                        else "resumed"
                    ),
                    invocation_id=resumed.invocation_id,
                    function_call_id=resumed.function_call_id,
                    final_answer=resumed.final_answer,
                    retryable=False,
                )

        return approval_response(result, agent_resume=agent_resume)

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
