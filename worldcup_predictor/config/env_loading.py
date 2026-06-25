"""Phase 36C — resolve which dotenv file to load (never overrides OS env)."""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOADED_ENV_FILE: Path | None = None


def project_root() -> Path:
    return _PROJECT_ROOT


def is_production_runtime() -> bool:
    app_env = os.environ.get("APP_ENV", "").strip().lower()
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    return app_env == "production" or environment == "production"


def _non_empty_file(path: Path) -> Path | None:
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path.resolve()
    except OSError:
        pass
    return None


def resolve_env_file() -> Path | None:
    """
    Priority:
    1. OS environment variables (handled by pydantic — not read here)
    2. ENV_FILE if set and non-empty
    3. .env.production when APP_ENV=production or ENVIRONMENT=production
    4. .env as local/dev fallback
    """
    env_file = os.environ.get("ENV_FILE", "").strip()
    if env_file:
        resolved = _non_empty_file(Path(env_file))
        if resolved:
            return resolved
        resolved = _non_empty_file(_PROJECT_ROOT / env_file)
        if resolved:
            return resolved

    if is_production_runtime():
        prod = _non_empty_file(_PROJECT_ROOT / ".env.production")
        if prod:
            return prod

    dev = _non_empty_file(_PROJECT_ROOT / ".env")
    if dev:
        return dev

    return None


def note_loaded_env_file(path: Path | None) -> None:
    global _LOADED_ENV_FILE
    _LOADED_ENV_FILE = path


def loaded_env_file() -> Path | None:
    return _LOADED_ENV_FILE


def loaded_env_file_display() -> str:
    path = loaded_env_file()
    if path is None:
        return "none"
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)
