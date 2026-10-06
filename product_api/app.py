"""Persistent Product API boundary through Scenario 2 Phase 7D HITL.

Product owns operational/business state and human decisions. Google ADK owns
agent execution, persistent runtime sessions/events, the long-running wait point
and invocation resume mechanics.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
import logging
import os
import re
import secrets
from typing import Annotated, Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, Path, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from google.adk.sessions import DatabaseSessionService

from agent_runtime.service import DeviceIncidentAgentRuntime, Scenario1AgentRuntime
from agent_runtime.scenario2_service import Scenario2AgentRuntime
from agent_runtime.scenario3_service import Scenario3AgentRuntime
from agent_runtime.sessions import create_database_session_service
from agent_runtime.sessions import ensure_run_session
from product_backend.adapters.tool_adapters import DefaultScenario1ToolAdapter
from product_backend.adapters.scenario3_tool_adapters import (
    DefaultScenario3ToolAdapter,
)
from product_backend.adapters.scenario2_tool_adapters import (
    DefaultScenario2ToolAdapter,
)
from product_backend.application.field_visit import (
    FieldVisitApprovalService,
    FieldVisitProposalService,
)
from product_backend.application.lifecycle import ApplicationLifecycleService
from product_backend.application.major_incident import (
    MajorIncidentApprovalService,
    MajorIncidentProposalService,
)
from product_backend.application.read_tools import (
    EvidenceTtlPolicy,
    Scenario1ReadToolService,
)
from product_backend.application.results import ApprovalProcessed, OperationFailure
from product_backend.application.run_lifecycle import Scenario1RunStartService
from product_backend.application.run_state import RunStateService
from product_backend.application.scenario2_ingestion import (
    Scenario2FixtureTransitionService,
    Scenario2RunStartService,
    Scenario2SignalIngestionService,
)
from product_backend.application.scenario2_state import Scenario2StateService
from product_backend.application.scenario2_read_tools import (
    Scenario2EvidenceTtlPolicy,
    Scenario2ReadToolService,
)
from product_backend.application.scenario3_provider_reads import (
    Scenario3ProviderEvidenceTtlPolicy,
    Scenario3ProviderReadService,
)
from product_backend.application.scenario2_results import (
    MajorIncidentDecisionProcessed,
    Scenario2OperationFailure,
)
from product_backend.contracts.events import ApplicationEventType
from product_backend.contracts.scenario2_ingestion import Scenario2SignalInput
from product_backend.contracts.tools import ToolCallContext
from product_backend.domain.enums import (
    ApprovalDecision,
    HealthState,
    OperationalState,
    ProposalStatus,
    RunStatus,
)
from product_backend.domain.scenario2 import Scenario2SignalSource
from product_backend.domain.errors import DomainError, ErrorCode
from product_backend.persistence.database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
)
from product_backend.persistence.run_state import SqlAlchemyRunStateQuery
from product_backend.persistence.uow import (
    SqlAlchemyApprovalExecutionUnitOfWork,
    SqlAlchemyDispatchUnitOfWork,
    SqlAlchemyLifecycleUnitOfWork,
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyRunStartUnitOfWork,
    SqlAlchemyScenario2FixtureStateUnitOfWork,
    SqlAlchemyScenario2RunStartUnitOfWork,
    SqlAlchemyScenario2SignalIngestionUnitOfWork,
    SqlAlchemyScenario2ToolReadUnitOfWork,
    SqlAlchemyScenario2ProposalUnitOfWork,
    SqlAlchemyScenario2ApprovalUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)
from product_backend.persistence.scenario2_state import (
    SqlAlchemyScenario2StateQuery,
)

from .dispatch import Scenario1DispatchWorker, Scenario2DispatchWorker
from .scenario1_fixture import Scenario1FixtureSources
from .scenario2_simulator import Scenario2SimulatorService
from .scenario2_sources import PersistedScenario2FixtureSources
from .scenario3_fixture import Scenario3FixtureSources
from .scenario3_sources import Scenario3ProviderSources
from .schemas import (
    AcceptanceAccessLinkStateRequest,
    AcceptanceAccessLinkStateResponse,
    AgentInvocationResponse,
    AgentResumeView,
    ApiErrorBody,
    ApiErrorResponse,
    ApprovalDecisionResponse,
    HumanDecisionRequest,
    RunStateResponse,
    Scenario2ApprovalDecisionResponse,
    Scenario2DependencyStatusRequest,
    Scenario2IngestionStateResponse,
    Scenario2MatchingMajorIncidentRequest,
    Scenario2SignalIngestRequest,
    Scenario2SignalIngestResponse,
    Scenario2SimulatorStepResponse,
    TimelineResponse,
    approval_response,
    error_response,
    run_state_response,
    scenario2_approval_response,
    scenario2_signal_response,
    scenario2_simulator_response,
    scenario2_state_response,
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
    dispatch_worker: Scenario1DispatchWorker | None = None
    scenario2_agent_runtime: Scenario2AgentRuntime | None = None
    scenario2_dispatch_worker: Scenario2DispatchWorker | None = None
    scenario2_start_service: Scenario2RunStartService | None = None
    scenario2_ingestion_service: Scenario2SignalIngestionService | None = None
    scenario2_state_service: Scenario2StateService | None = None
    scenario2_fixture_service: Scenario2FixtureTransitionService | None = None
    scenario2_approval_service: MajorIncidentApprovalService | None = None
    scenario2_simulator: Scenario2SimulatorService | None = None
    scenario2_sources: PersistedScenario2FixtureSources | None = None
    scenario3_fixture: Scenario3FixtureSources | None = None
    scenario3_sources: Scenario3ProviderSources | None = None
    scenario3_provider_read_service: Scenario3ProviderReadService | None = None
    scenario3_agent_runtime: Scenario3AgentRuntime | None = None

    async def close(self) -> None:
        if self.scenario3_agent_runtime is not None:
            await self.scenario3_agent_runtime.close()
        if self.scenario2_agent_runtime is not None:
            await self.scenario2_agent_runtime.close()
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
    state_service = RunStateService(
        SqlAlchemyRunStateQuery(session_factory)
    )

    scenario2_state_service = Scenario2StateService(
        SqlAlchemyScenario2StateQuery(session_factory)
    )
    scenario2_ingestion_service = Scenario2SignalIngestionService(
        lambda: SqlAlchemyScenario2SignalIngestionUnitOfWork(session_factory)
    )
    scenario2_simulator = Scenario2SimulatorService(
        state_service=scenario2_state_service,
        ingestion_service=scenario2_ingestion_service,
    )
    scenario2_sources = PersistedScenario2FixtureSources(
        scenario2_state_service,
        session_factory,
    )
    scenario2_read_service = Scenario2ReadToolService(
        read_uow_factory=lambda: SqlAlchemyScenario2ToolReadUnitOfWork(
            session_factory
        ),
        local_health=scenario2_sources,
        dependency_mapping=scenario2_sources,
        dependency_status=scenario2_sources,
        major_incident_directory=scenario2_sources,
        ttl_policy=Scenario2EvidenceTtlPolicy(
            local_service_health=timedelta(minutes=5),
            external_dependency_status=timedelta(minutes=2),
            major_incident_search=timedelta(minutes=2),
        ),
    )
    scenario2_proposal_service = MajorIncidentProposalService(
        lambda: SqlAlchemyScenario2ProposalUnitOfWork(session_factory)
    )
    scenario2_tool_adapter = DefaultScenario2ToolAdapter(
        read_service=scenario2_read_service,
        proposal_service=scenario2_proposal_service,
    )
    scenario2_approval_service = MajorIncidentApprovalService(
        lambda: SqlAlchemyScenario2ApprovalUnitOfWork(session_factory),
        local_health=scenario2_sources,
        dependency_mapping=scenario2_sources,
        dependency_status=scenario2_sources,
        major_incident_directory=scenario2_sources,
    )
    scenario2_agent_runtime = Scenario2AgentRuntime(
        adapter=scenario2_tool_adapter,
        session_service=adk_session_service,
    )
    scenario2_dispatch_worker = Scenario2DispatchWorker(
        uow_factory=lambda: SqlAlchemyDispatchUnitOfWork(session_factory),
        state_service=scenario2_state_service,
        lifecycle_service=ApplicationLifecycleService(
            lambda: SqlAlchemyLifecycleUnitOfWork(session_factory)
        ),
        agent_runtime=scenario2_agent_runtime,
    )

    scenario3_fixture = Scenario3FixtureSources()
    scenario3_sources = Scenario3ProviderSources()
    scenario3_provider_read_service = Scenario3ProviderReadService(
        read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(session_factory),
        dependency_mapping=scenario3_sources,
        dependency_status=scenario3_sources,
        ttl_policy=Scenario3ProviderEvidenceTtlPolicy(
            external_dependency_status=timedelta(minutes=2),
        ),
    )

    scenario3_local_read_service = Scenario1ReadToolService(
        read_uow_factory=lambda: SqlAlchemyToolReadUnitOfWork(session_factory),
        cmdb=scenario3_fixture,
        monitoring=scenario3_fixture,
        itsm=scenario3_fixture,
        kb=scenario3_fixture,
        ttl_policy=EvidenceTtlPolicy(
            site_health=timedelta(minutes=5),
            access_link_diagnostic=timedelta(minutes=2),
        ),
    )
    scenario3_local_adapter = DefaultScenario1ToolAdapter(
        read_service=scenario3_local_read_service,
        proposal_service=proposal_service,
    )
    scenario3_tool_adapter = DefaultScenario3ToolAdapter(
        provider_read_service=scenario3_provider_read_service,
        local_adapter=scenario3_local_adapter,
    )
    scenario3_agent_runtime = Scenario3AgentRuntime(
        adapter=scenario3_tool_adapter,
        session_service=adk_session_service,
    )

    # Scenario 1 and Scenario 3 share one durable device-Incident consumer.
    # The worker reloads Product state and chooses the runtime only from the
    # persisted Run.scenario_id.
    dispatch_worker = Scenario1DispatchWorker(
        uow_factory=lambda: SqlAlchemyDispatchUnitOfWork(session_factory),
        state_service=state_service,
        agent_runtime=agent_runtime,
        scenario3_agent_runtime=scenario3_agent_runtime,
    )

    return ProductApiContainer(
        start_service=Scenario1RunStartService(
            lambda: SqlAlchemyRunStartUnitOfWork(session_factory)
        ),
        state_service=state_service,
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
        dispatch_worker=dispatch_worker,
        scenario2_agent_runtime=scenario2_agent_runtime,
        scenario2_dispatch_worker=scenario2_dispatch_worker,
        scenario2_start_service=Scenario2RunStartService(
            lambda: SqlAlchemyScenario2RunStartUnitOfWork(session_factory)
        ),
        scenario2_ingestion_service=scenario2_ingestion_service,
        scenario2_state_service=scenario2_state_service,
        scenario2_fixture_service=Scenario2FixtureTransitionService(
            lambda: SqlAlchemyScenario2FixtureStateUnitOfWork(session_factory)
        ),
        scenario2_approval_service=scenario2_approval_service,
        scenario2_simulator=scenario2_simulator,
        scenario2_sources=scenario2_sources,
        scenario3_fixture=scenario3_fixture,
        scenario3_sources=scenario3_sources,
        scenario3_provider_read_service=scenario3_provider_read_service,
        scenario3_agent_runtime=scenario3_agent_runtime,
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


def _scenario2_agent_decision_payload(
    result: MajorIncidentDecisionProcessed,
) -> dict[str, Any]:
    """Build safe Product truth returned to the paused Scenario 2 ADK call."""
    execution = (
        {
            "execution_id": result.execution.execution_id,
            "action_type": result.execution.action_type.value,
            "major_incident_id": result.execution.major_incident_id,
        }
        if result.execution is not None
        else None
    )
    major_incident = (
        {
            "major_incident_id": result.major_incident.major_incident_id,
            "status": result.major_incident.status.value,
            "service_key": result.major_incident.service_key,
            "correlation_key": result.major_incident.correlation_key,
            "dependency_id": result.major_incident.dependency_id,
            "affected_site_ids": list(result.major_incident.affected_site_ids),
        }
        if result.major_incident is not None
        else None
    )
    return {
        "status": "human_decision_committed",
        "decision": result.approval.decision.value,
        "proposal_id": result.proposal.proposal_id,
        "proposal_status": result.proposal.status.value,
        "execution": execution,
        "major_incident": major_incident,
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
        worker_started = False
        scenario2_worker_started = False
        try:
            if active.adk_session_service is not None:
                await active.adk_session_service.prepare_tables()
            if active.dispatch_worker is not None:
                active.dispatch_worker.start()
                active.dispatch_worker.wake()
                worker_started = True
            if active.scenario2_dispatch_worker is not None:
                active.scenario2_dispatch_worker.start()
                active.scenario2_dispatch_worker.wake()
                scenario2_worker_started = True
            yield
        finally:
            if (
                scenario2_worker_started
                and active.scenario2_dispatch_worker is not None
            ):
                await active.scenario2_dispatch_worker.close()
            if worker_started and active.dispatch_worker is not None:
                await active.dispatch_worker.close()
            if container is None:
                await active.close()

    app = FastAPI(
        title="Autonomous L1 Incident Agent Product API",
        version="0.8.0",
        description=(
            "Scenario 1 retains its native ADK path. Scenario 2 adds Phase 7D "
            "evidence-backed Product tools and native Major Incident HITL on top "
            "of the durable Phase 7C event/session lifecycle."
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
            "phase": 7,
            "checkpoint": "7A",
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
            "automatic_dispatch_wired": (
                services.dispatch_worker.running
                if services.dispatch_worker is not None
                else False
            ),
            "scenario2_checkpoint": "7C-adk-dispatch",
            "scenario2_phase7d_tools_hitl_wired": (
                services.scenario2_approval_service is not None
                and services.scenario2_agent_runtime is not None
                and services.scenario2_agent_runtime.resumability_wired
            ),
            "scenario2_ingestion_wired": (
                services.scenario2_ingestion_service is not None
                and services.scenario2_state_service is not None
                and services.scenario2_simulator is not None
            ),
            "scenario2_dispatch_consumer_wired": (
                services.scenario2_dispatch_worker.running
                if services.scenario2_dispatch_worker is not None
                else False
            ),
            "scenario2_tools_wired": (
                services.scenario2_agent_runtime is not None
                and services.scenario2_sources is not None
            ),
            "scenario2_hitl_wired": (
                services.scenario2_approval_service is not None
                and services.scenario2_agent_runtime is not None
                and services.scenario2_agent_runtime.resumability_wired
            ),
            "scenario3_phase8c1_provider_reads_wired": (
                services.scenario3_fixture is not None
                and services.scenario3_sources is not None
                and services.scenario3_provider_read_service is not None
            ),
            "scenario3_phase8c2_native_wired": (
                services.scenario3_agent_runtime is not None
                and services.scenario3_agent_runtime.resumability_wired
                and services.dispatch_worker is not None
            ),
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
            try:
                await ensure_run_session(
                    services.adk_session_service,
                    tenant_id=tenant_id,
                    run_id=started.run.run_id,
                )
            except Exception:
                # Product state + external signal + outbox envelope are already
                # committed atomically. A transient ADK-session provisioning
                # failure must not turn a successful simulation start into an
                # ambiguous client error. The durable dispatcher will retry and
                # invoke_operational_event() ensures the same run session.
                logger.warning(
                    "ADK session provisioning deferred for run=%s",
                    started.run.run_id,
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

        # The Product signal/outbox transaction is already committed. Waking the
        # durable consumer is only a latency optimization; restart/poll recovery
        # does not depend on this in-process notification.
        if services.dispatch_worker is not None:
            services.dispatch_worker.wake()

        return run_state_response(snapshot)

    @app.post(
        "/api/v1/scenario-3/runs",
        response_model=RunStateResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
    )
    async def start_scenario3_run(
        request: Request,
        tenant_id: TenantId,
    ) -> RunStateResponse:
        services = _container(request)
        if services.scenario3_fixture is None:
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO3_NOT_CONFIGURED",
                message="Scenario 3 Product foundation is not configured.",
                retryable=False,
            )

        started = await services.start_service.start(
            tenant_id=tenant_id,
            bootstrap=services.scenario3_fixture.bootstrap(),
        )
        if services.adk_session_service is not None:
            try:
                await ensure_run_session(
                    services.adk_session_service,
                    tenant_id=tenant_id,
                    run_id=started.run.run_id,
                )
            except Exception:
                logger.warning(
                    "Scenario 3 ADK session provisioning deferred for run=%s",
                    started.run.run_id,
                )

        snapshot = await services.state_service.get(
            tenant_id=tenant_id,
            run_id=started.run.run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STATE_PERSISTENCE_FAILED",
                message="Scenario 3 run state is unavailable after start.",
                retryable=True,
            )

        if services.dispatch_worker is not None:
            services.dispatch_worker.wake()

        return run_state_response(snapshot)

    @app.post(
        "/api/v1/scenario-2/runs",
        response_model=Scenario2IngestionStateResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
    )
    async def start_scenario2_run(
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2IngestionStateResponse:
        services = _container(request)
        if (
            services.scenario2_start_service is None
            or services.scenario2_state_service is None
        ):
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO2_INGESTION_UNAVAILABLE",
                message="Scenario 2 Product ingestion is not configured.",
                retryable=True,
            )
        started = await services.scenario2_start_service.start(
            tenant_id=tenant_id,
        )
        if isinstance(started, OperationFailure):
            _raise_domain_error(started.error)
        snapshot = await services.scenario2_state_service.get(
            tenant_id=tenant_id,
            run_id=started.run.run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="STATE_PERSISTENCE_FAILED",
                message="Scenario 2 run state is unavailable after start.",
                retryable=True,
            )
        return scenario2_state_response(snapshot)

    @app.get(
        "/api/v1/scenario-2/runs/{run_id}",
        response_model=Scenario2IngestionStateResponse,
        responses=_ERROR_RESPONSES,
    )
    async def get_scenario2_state(
        run_id: Annotated[str, _ID_PATH],
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2IngestionStateResponse:
        services = _container(request)
        if services.scenario2_state_service is None:
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO2_INGESTION_UNAVAILABLE",
                message="Scenario 2 Product state is not configured.",
                retryable=True,
            )
        snapshot = await services.scenario2_state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="RUN_NOT_FOUND",
                message="Scenario 2 run was not found.",
            )
        return scenario2_state_response(snapshot)

    @app.post(
        "/api/v1/scenario-2/runs/{run_id}/signals",
        response_model=Scenario2SignalIngestResponse,
        status_code=status.HTTP_201_CREATED,
        responses=_ERROR_RESPONSES,
    )
    async def ingest_scenario2_signal(
        run_id: Annotated[str, _ID_PATH],
        body: Scenario2SignalIngestRequest,
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2SignalIngestResponse:
        services = _container(request)
        if services.scenario2_ingestion_service is None:
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO2_INGESTION_UNAVAILABLE",
                message="Scenario 2 Product ingestion is not configured.",
                retryable=True,
            )
        result = await services.scenario2_ingestion_service.ingest(
            tenant_id=tenant_id,
            run_id=run_id,
            signal_input=Scenario2SignalInput(
                source=Scenario2SignalSource(body.source),
                site_id=body.site_id,
                service_key=body.service_key,
                symptom_key=body.symptom_key,
                source_ref=body.source_ref,
                safe_payload=body.safe_payload,
            ),
        )
        if isinstance(result, OperationFailure):
            _raise_domain_error(result.error)
        if (
            result.dispatch is not None
            and services.scenario2_dispatch_worker is not None
        ):
            # The durable outbox is the recovery source. This only shortens
            # latency for a committed newly-ingested Product fact.
            services.scenario2_dispatch_worker.wake()
        return scenario2_signal_response(result)

    @app.post(
        "/api/v1/scenario-2/runs/{run_id}/simulator/next",
        response_model=Scenario2SimulatorStepResponse,
        responses=_ERROR_RESPONSES,
    )
    async def advance_scenario2_simulator(
        run_id: Annotated[str, _ID_PATH],
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2SimulatorStepResponse:
        services = _container(request)
        if services.scenario2_simulator is None:
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO2_SIMULATOR_UNAVAILABLE",
                message="Scenario 2 simulator is not configured.",
                retryable=True,
            )
        result = await services.scenario2_simulator.next(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if isinstance(result, OperationFailure):
            _raise_domain_error(result.error)
        if (
            result.ingested is not None
            and result.ingested.dispatch is not None
            and services.scenario2_dispatch_worker is not None
        ):
            services.scenario2_dispatch_worker.wake()
        return scenario2_simulator_response(result)

    @app.post(
        "/api/v1/scenario-2/runs/{run_id}/acceptance/dependency-status",
        response_model=Scenario2IngestionStateResponse,
        responses=_ERROR_RESPONSES,
        include_in_schema=False,
    )
    async def set_scenario2_dependency_status(
        run_id: Annotated[str, _ID_PATH],
        body: Scenario2DependencyStatusRequest,
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2IngestionStateResponse:
        services = _container(request)
        if (
            services.scenario2_fixture_service is None
            or services.scenario2_state_service is None
        ):
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO2_FIXTURE_UNAVAILABLE",
                message="Scenario 2 fixture controls are not configured.",
                retryable=True,
            )
        result = await services.scenario2_fixture_service.set_dependency_status(
            tenant_id=tenant_id,
            run_id=run_id,
            status=HealthState(body.dependency_status),
        )
        if isinstance(result, OperationFailure):
            _raise_domain_error(result.error)
        snapshot = await services.scenario2_state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="RUN_NOT_FOUND",
                message="Scenario 2 run was not found.",
            )
        return scenario2_state_response(snapshot)

    @app.post(
        "/api/v1/scenario-2/runs/{run_id}/acceptance/matching-major-incident",
        response_model=Scenario2IngestionStateResponse,
        responses=_ERROR_RESPONSES,
        include_in_schema=False,
    )
    async def set_scenario2_matching_major_incident(
        run_id: Annotated[str, _ID_PATH],
        body: Scenario2MatchingMajorIncidentRequest,
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2IngestionStateResponse:
        services = _container(request)
        if (
            services.scenario2_fixture_service is None
            or services.scenario2_state_service is None
        ):
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO2_FIXTURE_UNAVAILABLE",
                message="Scenario 2 fixture controls are not configured.",
                retryable=True,
            )
        result = await services.scenario2_fixture_service.set_matching_major_incident(
            tenant_id=tenant_id,
            run_id=run_id,
            major_incident_id=body.major_incident_id,
        )
        if isinstance(result, OperationFailure):
            _raise_domain_error(result.error)
        snapshot = await services.scenario2_state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        if snapshot is None:
            _raise_api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="RUN_NOT_FOUND",
                message="Scenario 2 run was not found.",
            )
        return scenario2_state_response(snapshot)

    @app.post(
        "/api/v1/runs/{run_id}/agent/invoke",
        response_model=AgentInvocationResponse,
        responses=_ERROR_RESPONSES,
        include_in_schema=False,
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

        timeline = await services.lifecycle_service.timeline(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            after_seq=0,
            limit=1000,
        )
        source_event = next(
            (
                event
                for event in reversed(timeline)
                if event.event_type is ApplicationEventType.EXTERNAL_SIGNAL
            ),
            None,
        )
        if source_event is None:
            _raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="OPERATIONAL_EVENT_NOT_FOUND",
                message="No persisted operational signal is available for this run.",
            )

        operational_signal["event_id"] = source_event.event_id
        operational_signal["event_seq"] = source_event.seq
        operational_signal["signal"] = source_event.payload

        result = await services.agent_runtime.invoke_operational_event(
            tenant_id=tenant_id,
            run_id=run_id,
            operational_event_id=source_event.event_id,
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

    async def decide_scenario2(
        *,
        request: Request,
        tenant_id: str,
        run_id: str,
        proposal_id: str,
        decision: ApprovalDecision,
        decided_by: str,
    ) -> Scenario2ApprovalDecisionResponse:
        services = _container(request)
        if services.scenario2_approval_service is None:
            _raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="SCENARIO2_HITL_UNAVAILABLE",
                message="Scenario 2 Major Incident approval is not configured.",
                retryable=True,
            )

        # Product truth commits first. Native ADK resume is a post-commit
        # reconciliation step and may safely be retried through this endpoint.
        result = await services.scenario2_approval_service.decide(
            ToolCallContext(tenant_id=tenant_id, run_id=run_id),
            proposal_id=proposal_id,
            decision=decision,
            decided_by=decided_by,
        )
        if isinstance(result, Scenario2OperationFailure):
            _raise_domain_error(result.error)

        agent_resume = AgentResumeView(
            status="deferred",
            retryable=True,
        )
        if services.scenario2_agent_runtime is not None:
            try:
                resumed = (
                    await services.scenario2_agent_runtime.resume_human_decision(
                        tenant_id=tenant_id,
                        run_id=run_id,
                        proposal_id=proposal_id,
                        decision_payload=_scenario2_agent_decision_payload(result),
                    )
                )
            except Exception:
                logger.warning(
                    "Scenario 2 native ADK resume deferred for run=%s proposal=%s",
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

        return scenario2_approval_response(
            result,
            agent_resume=agent_resume,
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

        # Product truth is committed first. Runtime selection is then derived
        # from the persisted Product Run, never from request/model input.
        snapshot = await services.state_service.get(
            tenant_id=tenant_id,
            run_id=run_id,
        )
        runtime: DeviceIncidentAgentRuntime | None = None
        if snapshot is not None:
            if snapshot.run.scenario_id == "scenario-1":
                runtime = services.agent_runtime
            elif snapshot.run.scenario_id == "scenario-3":
                runtime = services.scenario3_agent_runtime

        if runtime is not None:
            try:
                resumed = await runtime.resume_human_decision(
                    tenant_id=tenant_id,
                    run_id=run_id,
                    proposal_id=proposal_id,
                    decision_payload=_agent_decision_payload(result),
                )
            except Exception:
                # The Product decision is already committed. Replaying the same
                # endpoint reconciles native delivery without duplicating the
                # Product decision or FunctionResponse.
                logger.warning(
                    "Native ADK resume deferred for run=%s proposal=%s scenario=%s",
                    run_id,
                    proposal_id,
                    snapshot.run.scenario_id if snapshot is not None else "unknown",
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
        "/__acceptance/phase6d/runs/{run_id}/access-link-state",
        response_model=AcceptanceAccessLinkStateResponse,
        responses=_ERROR_RESPONSES,
        include_in_schema=False,
    )
    async def set_phase6d_access_link_state(
        run_id: Annotated[str, _ID_PATH],
        body: AcceptanceAccessLinkStateRequest,
        request: Request,
        tenant_id: TenantId,
        acceptance_token: Annotated[
            str | None,
            Header(alias="X-Acceptance-Token"),
        ] = None,
    ) -> AcceptanceAccessLinkStateResponse:
        """Narrow managed-acceptance hook for the Scenario 1 stale path.

        The route is intentionally hidden from OpenAPI and behaves as not found
        unless explicitly enabled with a server-side token. It changes only the
        process-local authoritative monitoring fixture for one tenant/run.
        """
        enabled = os.environ.get("PHASE6D_ACCEPTANCE_HOOKS", "").lower() in {
            "1",
            "true",
            "yes",
        }
        expected_token = os.environ.get("PHASE6D_ACCEPTANCE_TOKEN", "")
        if (
            not enabled
            or not expected_token
            or not acceptance_token
            or not secrets.compare_digest(acceptance_token, expected_token)
        ):
            _raise_api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="NOT_FOUND",
                message="Resource was not found.",
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

        has_pending_proposal = any(
            proposal.status is ProposalStatus.PENDING_APPROVAL
            for proposal in snapshot.proposals
        )
        if (
            snapshot.run.status is not RunStatus.WAITING_APPROVAL
            or not has_pending_proposal
        ):
            _raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="ACCEPTANCE_PRECONDITION_FAILED",
                message=(
                    "Phase 6D access-link override requires a WAITING_APPROVAL "
                    "run with a PENDING_APPROVAL proposal."
                ),
            )

        operational_state = OperationalState(body.operational_state)
        services.fixture.set_access_link_operational_state(
            tenant_id=tenant_id,
            run_id=run_id,
            operational_state=operational_state,
        )
        return AcceptanceAccessLinkStateResponse(
            tenant_id=tenant_id,
            run_id=run_id,
            operational_state=operational_state.value,
        )

    @app.post(
        "/api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/approve",
        response_model=Scenario2ApprovalDecisionResponse,
        responses=_ERROR_RESPONSES,
    )
    async def approve_scenario2_major_incident(
        run_id: Annotated[str, _ID_PATH],
        proposal_id: Annotated[str, _ID_PATH],
        body: HumanDecisionRequest,
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2ApprovalDecisionResponse:
        return await decide_scenario2(
            request=request,
            tenant_id=tenant_id,
            run_id=run_id,
            proposal_id=proposal_id,
            decision=ApprovalDecision.APPROVED,
            decided_by=body.decided_by,
        )

    @app.post(
        "/api/v1/scenario-2/runs/{run_id}/proposals/{proposal_id}/reject",
        response_model=Scenario2ApprovalDecisionResponse,
        responses=_ERROR_RESPONSES,
    )
    async def reject_scenario2_major_incident(
        run_id: Annotated[str, _ID_PATH],
        proposal_id: Annotated[str, _ID_PATH],
        body: HumanDecisionRequest,
        request: Request,
        tenant_id: TenantId,
    ) -> Scenario2ApprovalDecisionResponse:
        return await decide_scenario2(
            request=request,
            tenant_id=tenant_id,
            run_id=run_id,
            proposal_id=proposal_id,
            decision=ApprovalDecision.REJECTED,
            decided_by=body.decided_by,
        )

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
