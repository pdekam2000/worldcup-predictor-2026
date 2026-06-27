"""Central application version manifest — Hotfix Pack 4."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings

_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "app_version.manifest.json"

# Inline fallback when manifest is missing (e.g. partial deploy).
_DEFAULTS: dict[str, str] = {
    "app_version": "A23.0.0",
    "build_label": "hotfix-pack4",
    "build_date": date.today().isoformat(),
    "commit": "unknown",
}

APP_VERSION = _DEFAULTS["app_version"]
BUILD_LABEL = _DEFAULTS["build_label"]
BUILD_DATE = _DEFAULTS["build_date"]
COMMIT_HASH = _DEFAULTS["commit"]


def _git_short_hash() -> str | None:
    try:
        root = _MANIFEST_PATH.parent
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        value = out.strip()
        return value or None
    except (OSError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=1)
def load_version_manifest() -> dict[str, str]:
    """Load version fields from repo manifest with env/git overrides."""
    data = dict(_DEFAULTS)
    if _MANIFEST_PATH.is_file():
        try:
            raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in _DEFAULTS:
                    if raw.get(key):
                        data[key] = str(raw[key])
        except (json.JSONDecodeError, OSError):
            pass

    env_commit = os.getenv("DEPLOY_COMMIT", "").strip() or os.getenv("GIT_COMMIT", "").strip()
    if env_commit:
        data["commit"] = env_commit[:12]
    elif data["commit"] in {"", "unknown"}:
        git_hash = _git_short_hash()
        if git_hash:
            data["commit"] = git_hash

    return data


def resolve_environment() -> str:
    settings = get_settings()
    env = (settings.app_env or os.getenv("APP_ENV", "local")).strip().lower()
    if env in {"production", "prod"}:
        return "production"
    if env in {"staging", "stage"}:
        return "staging"
    if env in {"local", "development", "dev"}:
        return "development"
    return env or "development"


def environment_short(environment: str | None = None) -> str:
    env = (environment or resolve_environment()).lower()
    if env == "production":
        return "prod"
    if env == "staging":
        return "stage"
    if env == "development":
        return "dev"
    return env[:8]


def build_version_payload() -> dict[str, Any]:
    manifest = load_version_manifest()
    environment = resolve_environment()
    sqlite_schema = None
    postgres_migration = None
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        sqlite_schema = str(repo.status().schema_version)
        repo.close()
    except Exception:
        try:
            from worldcup_predictor.database.schema import SCHEMA_VERSION

            sqlite_schema = str(SCHEMA_VERSION)
        except Exception:
            sqlite_schema = "unknown"

    try:
        from sqlalchemy import text
        from worldcup_predictor.database.postgres.session import get_postgres_engine, postgres_configured

        if postgres_configured():
            with get_postgres_engine().connect() as conn:
                row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                if row:
                    postgres_migration = str(row[0])
    except Exception:
        postgres_migration = None

    frontend_commit = os.getenv("FRONTEND_COMMIT", "").strip() or None
    return {
        "app_version": manifest["app_version"],
        "build_label": manifest["build_label"],
        "build_date": manifest["build_date"],
        "commit": manifest["commit"],
        "backend_commit": manifest["commit"],
        "frontend_commit": frontend_commit,
        "database_schema": sqlite_schema,
        "migration_version": postgres_migration or sqlite_schema,
        "sqlite_schema_version": sqlite_schema,
        "postgres_migration": postgres_migration,
        "environment": environment,
        "environment_short": environment_short(environment),
        "display_short": f"v{manifest['app_version']}",
        "display_full": (
            f"v{manifest['app_version']} · {manifest['build_label']} · {environment_short(environment)}"
        ),
    }
