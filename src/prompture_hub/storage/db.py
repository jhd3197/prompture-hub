"""SQLite engine + session factory.

The engine is lazily constructed on first access so module import is cheap
and unit tests can swap ``HUB_DB_PATH`` (and clear the lru_cache on settings)
before the engine is built.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlmodel import Session, SQLModel, create_engine

from ..settings import get_settings

_engine = None


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
    """Create all tables. Idempotent; safe to call on every startup."""
    from . import models  # noqa: F401  — register tables with SQLModel.metadata

    SQLModel.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
