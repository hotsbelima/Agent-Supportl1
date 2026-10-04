"""Async PostgreSQL engine/session configuration.

The deployment supplies DATABASE_URL.  Credentials are never logged or copied
into application/domain state.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def normalize_database_url(url: str) -> str:
    """Normalize managed-Postgres URLs for SQLAlchemy's psycopg async dialect."""
    value = url.strip()
    if not value:
        raise ValueError("DATABASE_URL is empty")
    if value.startswith("postgresql+psycopg://"):
        return value
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    raise ValueError("DATABASE_URL must use a PostgreSQL scheme")


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    url: str
    echo: bool = False
    pool_pre_ping: bool = True

    @classmethod
    def from_env(cls, variable: str = "DATABASE_URL") -> "DatabaseSettings":
        raw_url = os.environ.get(variable)
        if raw_url is None:
            raise RuntimeError(f"{variable} is not configured")
        return cls(url=normalize_database_url(raw_url))


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(settings.url),
        echo=settings.echo,
        pool_pre_ping=settings.pool_pre_ping,
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )
