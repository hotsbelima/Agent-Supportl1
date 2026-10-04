"""PostgreSQL persistence implementation for the product backend.

Phase 4A keeps database/framework types out of the pure domain package.  The
classes exported here implement the repository/UoW ports fixed in Phase 3.
"""

from .database import (
    DatabaseSettings,
    create_engine,
    create_session_factory,
    normalize_database_url,
)
from .events import SqlAlchemyApplicationEventRepository
from .uow import (
    SqlAlchemyApprovalExecutionUnitOfWork,
    SqlAlchemyLifecycleUnitOfWork,
    SqlAlchemyProposalCreationUnitOfWork,
    SqlAlchemyToolReadUnitOfWork,
)

__all__ = [
    "DatabaseSettings",
    "SqlAlchemyApplicationEventRepository",
    "SqlAlchemyApprovalExecutionUnitOfWork",
    "SqlAlchemyLifecycleUnitOfWork",
    "SqlAlchemyProposalCreationUnitOfWork",
    "SqlAlchemyToolReadUnitOfWork",
    "create_engine",
    "create_session_factory",
    "normalize_database_url",
]
