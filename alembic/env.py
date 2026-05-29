"""Alembic environment for prompture-hub.

Wires Alembic into :data:`SQLModel.metadata` and resolves the SQLite URL
from :class:`HubSettings` at runtime so ``HUB_DB_PATH`` env overrides apply
both to the CLI (``alembic upgrade head``) and the programmatic upgrade
called from :func:`prompture_hub.storage.db.init_db`.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Importing the models package registers every table on SQLModel.metadata.
import prompture_hub.storage.models  # noqa: F401
from prompture_hub.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLModel's shared metadata for autogenerate.
target_metadata = SQLModel.metadata


def _resolved_url() -> str:
    cli_url = config.get_main_option("sqlalchemy.url") or ""
    if cli_url:
        return cli_url
    return f"sqlite:///{get_settings().db_path}"


def run_migrations_offline() -> None:
    context.configure(
        url=_resolved_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section) or {}
    cfg["sqlalchemy.url"] = _resolved_url()
    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite needs batch mode to ALTER TABLE — keeps future
            # migrations portable.
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
