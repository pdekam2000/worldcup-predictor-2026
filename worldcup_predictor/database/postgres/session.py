"""PostgreSQL session factory and engine access."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.engine import _to_sqlalchemy_url

_engine_singleton: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def postgres_configured(settings: Settings | None = None) -> bool:
    active = settings or get_settings()
    return bool((active.database_url or "").strip())


def get_postgres_engine(settings: Settings | None = None) -> Engine:
    """Return a process-wide SQLAlchemy engine for PostgreSQL."""
    global _engine_singleton, _session_factory
    active = settings or get_settings()
    url = (active.database_url or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. PostgreSQL is required for SaaS repositories."
        )
    if _engine_singleton is None:
        _engine_singleton = create_engine(
            _to_sqlalchemy_url(url),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
        _session_factory = sessionmaker(bind=_engine_singleton, autoflush=False, expire_on_commit=False)
    return _engine_singleton


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    get_postgres_engine(settings)
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope(settings: Settings | None = None) -> Generator[Session, None, None]:
    """Transactional scope for repository operations."""
    factory = get_session_factory(settings)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def ping_postgres(settings: Settings | None = None) -> bool:
    """Lightweight connectivity check."""
    if not postgres_configured(settings):
        return False
    try:
        with get_postgres_engine(settings).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_postgres_engine() -> None:
    """Dispose engine — intended for tests."""
    global _engine_singleton, _session_factory
    if _engine_singleton is not None:
        _engine_singleton.dispose()
    _engine_singleton = None
    _session_factory = None
