"""SQLite engine + session factory + Alembic-driven schema management.

The engine is lazily constructed on first access so module import is cheap
and unit tests can swap ``HUB_DB_PATH`` (and clear the lru_cache on settings)
before the engine is built.

Schema is created and upgraded via Alembic — see ``alembic/`` at the repo
root. :func:`init_db` runs ``alembic upgrade head`` programmatically at app
startup so deployments self-migrate on boot, no manual step required.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlmodel import Session, create_engine

from ..settings import get_settings

logger = logging.getLogger(__name__)

_engine = None

# Path to the alembic config relative to this file. Resolved at runtime so
# both editable installs and packaged installs see the right location.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _REPO_ROOT / "alembic.ini"


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
    """Run ``alembic upgrade head`` so the DB matches the latest schema.

    Idempotent — safe to call on every startup. Falls back to
    ``SQLModel.metadata.create_all`` only if ``alembic.ini`` can't be located
    (e.g. running from an unusual install layout), to keep dev runs working.
    """
    if not _ALEMBIC_INI.is_file():
        logger.warning(
            "alembic.ini not found at %s; falling back to create_all. "
            "Future schema changes won't auto-migrate.",
            _ALEMBIC_INI,
        )
        from sqlmodel import SQLModel

        from . import models  # noqa: F401  — register tables
        SQLModel.metadata.create_all(get_engine())
        return

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    # Pin the script_location to an absolute path so commands work no
    # matter what cwd the server happens to start in.
    cfg.set_main_option("script_location", str(_REPO_ROOT / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url", f"sqlite:///{get_settings().db_path}",
    )

    # Ensure the engine is built against the same path before running, so
    # connection_pool behaviour matches.
    get_engine()
    command.upgrade(cfg, "head")


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
