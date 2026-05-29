"""SQLite engine + session factory + Alembic-driven schema management.

The engine is lazily constructed on first access so module import is cheap
and unit tests can swap ``HUB_DB_PATH`` (and clear the lru_cache on settings)
before the engine is built.

Schema is created and upgraded via Alembic. The migration environment lives
*inside* the package at ``prompture_hub/migrations/`` so it ships in the wheel
and is found the same way whether the app was installed from PyPI, run from a
source checkout, or built into a container. :func:`init_db` runs
``alembic upgrade head`` programmatically on every boot, so the schema always
self-heals to the latest version with no manual step.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, create_engine

from ..settings import get_settings

logger = logging.getLogger(__name__)

_engine = None

# The packaged migration environment (env.py, versions/). Resolved relative to
# this module — NOT the repo root — so it works in an installed package where
# there is no repo at all. The directory ships because it lives under the
# prompture_hub package tree.
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
    return _engine


def init_db() -> None:
    """Bring the database up to the latest schema. Runs on every boot.

    Fresh databases get the full schema; existing ones get only the migrations
    they are missing. Idempotent and safe to call on every startup — there is
    no manual migration step for anyone running the hub.

    The alembic config is assembled in code (no ``alembic.ini`` needed at
    runtime) and pointed at the migrations bundled in the package, so this works
    identically for PyPI installs, source checkouts, and containers.
    """
    if not _MIGRATIONS_DIR.is_dir():
        # Should never happen in a correctly built package; guard so a broken
        # install still produces a usable (if un-versioned) schema rather than
        # crashing on boot.
        logger.warning(
            "Packaged migrations not found at %s; falling back to create_all. "
            "Schema changes won't auto-migrate — reinstall a complete build.",
            _MIGRATIONS_DIR,
        )
        from sqlmodel import SQLModel

        from . import models  # noqa: F401  — register tables
        SQLModel.metadata.create_all(get_engine())
        return

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{get_settings().db_path}")

    # Ensure the engine is built against the same path before running, so
    # connection-pool behaviour matches.
    engine = get_engine()

    # Adopt a pre-Alembic database without re-running the initial migration over
    # existing tables. An older build created the schema with create_all and left
    # no alembic_version row; if we see the schema but no version table, stamp it
    # at head (that schema matches the latest models) before upgrading. Fresh
    # databases have no tables and migrate normally from base.
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "hubkey" in tables:
        logger.info("Adopting pre-Alembic database: stamping schema at head.")
        command.stamp(cfg, "head")

    command.upgrade(cfg, "head")


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
