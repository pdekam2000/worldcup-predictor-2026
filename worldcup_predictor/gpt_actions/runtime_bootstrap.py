"""GPT Actions process bootstrap — writable cache paths under systemd sandbox."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(os.environ.get("APP_ROOT", "/opt/worldcup-predictor"))


def _ensure_production_env(root: Path) -> None:
    """Load .env.production when running on the production tree without APP_ENV."""
    if os.environ.get("APP_ENV", "").strip():
        return
    prod_env = root / ".env.production"
    if prod_env.is_file() and prod_env.stat().st_size > 0:
        os.environ["APP_ENV"] = "production"


def bootstrap_gpt_actions_runtime() -> dict[str, Any]:
    """
    Ensure API/prediction caches use paths writable under ProtectSystem=strict.

    worldcup-gpt-actions.service ReadWritePaths includes data/ but not .cache/.
    Must run before the first get_settings() call.
    """
    root = _project_root()
    _ensure_production_env(root)
    os.environ.setdefault("API_CACHE_DIR", "data/cache/api_football")
    os.environ.setdefault("PREDICTION_CACHE_DIR", "data/cache/predictions")
    for key in ("API_CACHE_DIR", "PREDICTION_CACHE_DIR"):
        raw = os.environ.get(key, "").strip()
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        path.mkdir(parents=True, exist_ok=True)

    from worldcup_predictor.config.env_loading import loaded_env_file_display
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    return {
        "app_env": os.environ.get("APP_ENV", ""),
        "api_cache_dir": os.environ.get("API_CACHE_DIR", ""),
        "prediction_cache_dir": os.environ.get("PREDICTION_CACHE_DIR", ""),
        "env_file": loaded_env_file_display(),
        "api_football_configured": settings.api_football_configured,
        "sqlite_path": settings.sqlite_path,
    }
