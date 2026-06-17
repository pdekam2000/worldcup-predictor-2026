"""Database engine factory — SQLite default, PostgreSQL when DATABASE_URL is set.

This module is the future connection layer. Repository code continues to use
``connection.connect()`` until Phase B wires repositories through here.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlparse, urlunparse

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import get_db_path, is_connected
from worldcup_predictor.database.schema import DEFAULT_DB_PATH, SCHEMA_VERSION


class DatabaseBackend(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


@dataclass(frozen=True)
class EngineConfig:
    backend: DatabaseBackend
    database_url: str | None
    sqlite_path: Path
    fallback_enabled: bool

    @property
    def is_postgresql(self) -> bool:
        return self.backend == DatabaseBackend.POSTGRESQL

    @property
    def is_sqlite(self) -> bool:
        return self.backend == DatabaseBackend.SQLITE


@dataclass
class EngineTestResult:
    ok: bool
    backend: DatabaseBackend
    message: str
    details: dict[str, Any]

    def format_report(self) -> str:
        lines = [
            "=" * 72,
            "  WorldCup Predictor — Database Engine Test",
            "=" * 72,
            "",
            f"  Backend: {self.backend.value}",
            f"  Status:  {'OK' if self.ok else 'FAILED'}",
            f"  Message: {self.message}",
        ]
        for key, value in self.details.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        return "\n".join(lines)


def _normalize_sqlite_path(path: str | Path | None) -> Path:
    if path is None or not str(path).strip():
        return get_db_path(DEFAULT_DB_PATH)
    return get_db_path(path)


def _normalize_database_url(url: str | None) -> str | None:
    if url is None:
        return None
    cleaned = url.strip()
    return cleaned or None


def _to_sqlalchemy_url(database_url: str) -> str:
    """Map common PostgreSQL URLs to SQLAlchemy + psycopg driver form."""
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://") :]
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    return database_url


def redact_database_url(database_url: str) -> str:
    """Hide credentials for CLI output."""
    try:
        parsed = urlparse(database_url)
        host = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{host}{port}"
        if parsed.username:
            auth = parsed.username
            if parsed.password:
                auth = f"{auth}:***"
            netloc = f"{auth}@{netloc}"
        return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))
    except Exception:
        return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:***@", database_url)


def get_engine_config(settings: Settings | None = None) -> EngineConfig:
    """Resolve active backend from settings — SQLite when DATABASE_URL is unset."""
    active = settings or get_settings()
    database_url = _normalize_database_url(active.database_url)
    backend = DatabaseBackend.POSTGRESQL if database_url else DatabaseBackend.SQLITE
    return EngineConfig(
        backend=backend,
        database_url=database_url,
        sqlite_path=_normalize_sqlite_path(active.sqlite_path),
        fallback_enabled=active.database_fallback_enabled,
    )


def create_sqlalchemy_engine(settings: Settings | None = None) -> Any:
    """Create a SQLAlchemy engine for the configured backend.

    Raises ``RuntimeError`` when PostgreSQL is selected but dependencies are missing.
    """
    config = get_engine_config(settings)
    try:
        from sqlalchemy import create_engine
    except ImportError as exc:
        raise RuntimeError(
            "SQLAlchemy is not installed. Install dependencies: pip install -r requirements.txt"
        ) from exc

    if config.is_postgresql:
        if not config.database_url:
            raise RuntimeError("DATABASE_URL is required for PostgreSQL engine.")
        return create_engine(
            _to_sqlalchemy_url(config.database_url),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )

    sqlite_url = f"sqlite:///{config.sqlite_path.resolve().as_posix()}"
    return create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )


def test_sqlite_engine(settings: Settings | None = None) -> EngineTestResult:
    """Test local SQLite file used by the existing repository layer."""
    config = get_engine_config(settings)
    path = config.sqlite_path
    exists = path.exists()
    connected = is_connected(path) if exists else False
    schema_version: str | None = None
    size_kb: float | None = None

    if exists:
        size_kb = round(path.stat().st_size / 1024, 1)
    if connected:
        try:
            import sqlite3

            conn = sqlite3.connect(str(path))
            row = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            conn.close()
            if row:
                schema_version = str(row[0])
        except Exception:
            schema_version = None

    ok = exists and connected
    if not exists:
        message = "SQLite file not found (repository will create it on first init)."
        ok = True  # expected on fresh installs — still operational
    elif connected:
        message = "SQLite database is reachable."
    else:
        message = "SQLite file exists but schema check failed."

    return EngineTestResult(
        ok=ok,
        backend=DatabaseBackend.SQLITE,
        message=message,
        details={
            "path": str(path.resolve()),
            "exists": exists,
            "connected": connected,
            "schema_version": schema_version or "unknown",
            "expected_schema_version": SCHEMA_VERSION,
            "size_kb": size_kb if size_kb is not None else "n/a",
            "fallback_enabled": config.fallback_enabled,
        },
    )


def _sqlite_fallback_summary(settings: Settings | None = None) -> str:
    """Report whether SQLite remains active for the repository layer."""
    sqlite_result = test_sqlite_engine(settings)
    if sqlite_result.ok and sqlite_result.details.get("connected"):
        path = sqlite_result.details.get("path", "unknown")
        return f"active — repository still uses SQLite ({path})"
    if sqlite_result.details.get("exists"):
        return "available — SQLite file present (repository unchanged)"
    return "available — SQLite default path (repository unchanged)"


def test_postgresql_engine(settings: Settings | None = None) -> EngineTestResult:
    """Test PostgreSQL connectivity via SQLAlchemy (no tables required)."""
    config = get_engine_config(settings)
    fallback_note = _sqlite_fallback_summary(settings) if config.fallback_enabled else "disabled"

    if not config.database_url:
        return EngineTestResult(
            ok=False,
            backend=DatabaseBackend.POSTGRESQL,
            message="DATABASE_URL is not set.",
            details={"sqlite_fallback": fallback_note},
        )

    redacted = redact_database_url(config.database_url)
    try:
        engine = create_sqlalchemy_engine(settings)
    except RuntimeError as exc:
        return EngineTestResult(
            ok=False,
            backend=DatabaseBackend.POSTGRESQL,
            message=str(exc),
            details={
                "database_url": redacted,
                "sqlite_fallback": fallback_note,
            },
        )

    started = time.perf_counter()
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            server_version = conn.execute(text("SELECT version()")).scalar()
            current_database = conn.execute(text("SELECT current_database()")).scalar()
            current_user = conn.execute(text("SELECT current_user")).scalar()
            privilege_row = conn.execute(
                text(
                    """
                    SELECT
                        has_database_privilege(current_user, current_database(), 'CONNECT') AS can_connect,
                        has_schema_privilege(current_user, 'public', 'USAGE') AS can_use_public,
                        has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_public
                    """
                )
            ).mappings().one()
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        engine.dispose()

        can_connect = bool(privilege_row.get("can_connect"))
        ok = can_connect and current_database is not None
        if not can_connect:
            message = "Connected but user lacks CONNECT privilege on target database."
        else:
            message = "PostgreSQL connection successful."

        return EngineTestResult(
            ok=ok,
            backend=DatabaseBackend.POSTGRESQL,
            message=message,
            details={
                "database_url": redacted,
                "server_version": str(server_version) if server_version else "unknown",
                "current_database": str(current_database) if current_database else "unknown",
                "current_user": str(current_user) if current_user else "unknown",
                "connection_latency_ms": latency_ms,
                "can_connect": can_connect,
                "can_use_public_schema": bool(privilege_row.get("can_use_public")),
                "can_create_in_public_schema": bool(privilege_row.get("can_create_public")),
                "sqlite_fallback": fallback_note,
                "schema": "not checked (Phase B — table migration pending)",
            },
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        try:
            engine.dispose()
        except Exception:
            pass
        return EngineTestResult(
            ok=False,
            backend=DatabaseBackend.POSTGRESQL,
            message=f"PostgreSQL connection failed: {exc}",
            details={
                "database_url": redacted,
                "connection_latency_ms": latency_ms,
                "sqlite_fallback": fallback_note,
            },
        )


def run_db_test(*, settings: Settings | None = None, stream: TextIO | None = None) -> int:
    """CLI entry: SQLite status when DATABASE_URL unset; PostgreSQL ping when set."""
    import sys

    get_settings.cache_clear()
    out = stream or sys.stdout
    active_settings = settings or get_settings()
    config = get_engine_config(active_settings)

    if config.is_sqlite:
        result = test_sqlite_engine(active_settings)
    else:
        result = test_postgresql_engine(active_settings)

    out.write(result.format_report())
    return 0 if result.ok else 1
