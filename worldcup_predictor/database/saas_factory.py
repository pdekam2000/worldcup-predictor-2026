"""Factory for PostgreSQL SaaS persistence — primary production database layer."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import get_session_factory, postgres_configured, session_scope
from worldcup_predictor.database.postgres.uow import SaasUnitOfWork, build_uow


def require_postgres(settings: Settings | None = None) -> None:
    active = settings or get_settings()
    if not postgres_configured(active):
        raise RuntimeError(
            "DATABASE_URL must be set for PostgreSQL SaaS repositories. "
            "SQLite intelligence DB remains available separately for local/legacy use."
        )
    if active.is_production and not postgres_configured(active):
        raise RuntimeError("Production requires DATABASE_URL (PostgreSQL primary).")


@contextmanager
def saas_uow(settings: Settings | None = None) -> Generator[SaasUnitOfWork, None, None]:
    """Transactional unit-of-work for SaaS tables."""
    require_postgres(settings)
    with session_scope(settings) as session:
        yield build_uow(session)


def open_saas_uow(settings: Settings | None = None) -> SaasUnitOfWork:
    """Manual session — caller must commit/close."""
    require_postgres(settings)
    factory = get_session_factory(settings)
    session = factory()
    return build_uow(session)
