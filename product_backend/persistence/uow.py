"""Transactional SQLAlchemy Units of Work implementing Phase 3 ports."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .events import (
    SqlAlchemyApplicationEventRepository,
    SqlAlchemyApplicationOutboxRepository,
)
from .scenario2 import (
    SqlAlchemyOperationalSignalRepository,
    SqlAlchemyScenario2FixtureStateRepository,
    SqlAlchemyServiceIncidentRepository,
)
from .repositories import (
    SqlAlchemyApprovalRepository,
    SqlAlchemyEvidenceRepository,
    SqlAlchemyExecutedActionRepository,
    SqlAlchemyIncidentRepository,
    SqlAlchemyProposalRepository,
    SqlAlchemyRunRepository,
    SqlAlchemyWorkOrderRepository,
)


class _SqlAlchemyUnitOfWorkBase:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session = session_factory()
        self._finished = False

    async def __aenter__(self):
        if self._session.in_transaction():
            raise RuntimeError("Unit of Work session already has a transaction")
        await self._session.begin()
        return self

    async def commit(self) -> None:
        await self._session.commit()
        self._finished = True

    async def rollback(self) -> None:
        if self._session.in_transaction():
            await self._session.rollback()
        self._finished = True

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None or not self._finished:
                await self.rollback()
        finally:
            await self._session.close()


class SqlAlchemyScenario2RunStartUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Create a Scenario 2 run and persisted fixture state atomically."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(self._session)
        self.fixture_states = SqlAlchemyScenario2FixtureStateRepository(self._session)
        self.events = SqlAlchemyApplicationEventRepository(self._session)


class SqlAlchemyScenario2SignalIngestionUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Serialize one Scenario 2 operational fact on its owning run."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(
            self._session,
            lock_for_update=True,
        )
        self.service_incidents = SqlAlchemyServiceIncidentRepository(self._session)
        self.signals = SqlAlchemyOperationalSignalRepository(self._session)
        self.evidence = SqlAlchemyEvidenceRepository(self._session)
        self.events = SqlAlchemyApplicationEventRepository(self._session)
        self.outbox = SqlAlchemyApplicationOutboxRepository(self._session)


class SqlAlchemyScenario2FixtureStateUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Controlled persisted fixture transitions for stale-path acceptance."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(
            self._session,
            lock_for_update=True,
        )
        self.fixture_states = SqlAlchemyScenario2FixtureStateRepository(
            self._session,
            lock_for_update=True,
        )


class SqlAlchemyRunStartUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Create one Scenario 1 run, initial incident and start events atomically."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(self._session)
        self.incidents = SqlAlchemyIncidentRepository(self._session)
        self.events = SqlAlchemyApplicationEventRepository(self._session)
        self.outbox = SqlAlchemyApplicationOutboxRepository(self._session)


class SqlAlchemyToolReadUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """One read-tool observation plus evidence write in one transaction."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(self._session)
        self.incidents = SqlAlchemyIncidentRepository(self._session)
        self.evidence = SqlAlchemyEvidenceRepository(self._session)
        self.events = SqlAlchemyApplicationEventRepository(self._session)


class SqlAlchemyProposalCreationUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Serialize proposal creation on the run row.

    The run lock turns concurrent proposal creation into a deterministic
    re-check of run state; the partial unique index remains the DB safety net.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(
            self._session,
            lock_for_update=True,
        )
        self.incidents = SqlAlchemyIncidentRepository(
            self._session,
            lock_for_update=True,
        )
        self.evidence = SqlAlchemyEvidenceRepository(self._session)
        self.proposals = SqlAlchemyProposalRepository(self._session)
        self.events = SqlAlchemyApplicationEventRepository(self._session)


class SqlAlchemyApprovalExecutionUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Serialize one human decision and all of its side effects.

    The proposal row is locked before the service checks for an existing
    approval. A concurrent identical Approve therefore waits for the first
    transaction and can replay its stored result instead of creating duplicate
    action/work-order rows. Database unique constraints remain the final guard.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(
            self._session,
            lock_for_update=True,
        )
        self.incidents = SqlAlchemyIncidentRepository(
            self._session,
            lock_for_update=True,
        )
        self.evidence = SqlAlchemyEvidenceRepository(self._session)
        self.proposals = SqlAlchemyProposalRepository(
            self._session,
            lock_for_update=True,
        )
        self.approvals = SqlAlchemyApprovalRepository(self._session)
        self.executed_actions = SqlAlchemyExecutedActionRepository(self._session)
        self.work_orders = SqlAlchemyWorkOrderRepository(self._session)
        self.events = SqlAlchemyApplicationEventRepository(self._session)


class SqlAlchemyLifecycleUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Transaction boundary for lifecycle/audit writes and timeline reads."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.runs = SqlAlchemyRunRepository(self._session)
        self.evidence = SqlAlchemyEvidenceRepository(self._session)
        self.events = SqlAlchemyApplicationEventRepository(self._session)



class SqlAlchemyDispatchUnitOfWork(_SqlAlchemyUnitOfWorkBase):
    """Short transactions for claiming/completing durable agent dispatch."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        super().__init__(session_factory)
        self.outbox = SqlAlchemyApplicationOutboxRepository(self._session)
