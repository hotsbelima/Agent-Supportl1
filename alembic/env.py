"""Alembic environment for the Phase 4A PostgreSQL schema."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from product_backend.persistence.database import normalize_database_url
from product_backend.persistence.tables import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Google ADK DatabaseSessionService owns these runtime tables. Product
# Alembic must neither create nor propose dropping them during autogenerate/check.
_ADK_OWNED_TABLES = frozenset(
    {"adk_internal_metadata", "sessions", "events", "app_states", "user_states"}
)


def _include_object(object_, name, type_, reflected, compare_to) -> bool:
    del object_, compare_to
    if type_ == "table" and reflected and name in _ADK_OWNED_TABLES:
        return False
    return True


def _database_url() -> str:
    raw_url = os.environ.get("DATABASE_URL")
    if raw_url is None:
        raise RuntimeError(
            "DATABASE_URL must be set explicitly before running Alembic"
        )
    return normalize_database_url(raw_url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def _run_sync_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=_include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_run_sync_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
