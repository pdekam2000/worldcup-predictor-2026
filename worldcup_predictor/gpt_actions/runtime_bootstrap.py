"""GPT Actions process bootstrap — writable cache paths under systemd sandbox."""

from __future__ import annotations

import os
from pathlib import Path


def bootstrap_gpt_actions_runtime() -> None:
    """
    Ensure API/prediction caches use paths writable under ProtectSystem=strict.

    worldcup-gpt-actions.service ReadWritePaths includes data/ but not .cache/.
    Must run before the first get_settings() call.
    """
    root = Path(os.environ.get("APP_ROOT", "/opt/worldcup-predictor"))
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
