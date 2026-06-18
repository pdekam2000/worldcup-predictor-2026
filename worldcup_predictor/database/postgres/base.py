"""SQLAlchemy declarative base for PostgreSQL SaaS tables."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata root for Alembic and PostgreSQL repositories."""

    pass
