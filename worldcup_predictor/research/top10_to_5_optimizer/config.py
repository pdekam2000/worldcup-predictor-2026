"""Config loader for Top10-to-5 research."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_config_path() -> Path:
    return Path(__file__).with_name("default_config.json")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else default_config_path()
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg.setdefault("research_only", True)
    cfg.setdefault("owner_only", True)
    cfg.setdefault("not_deployed", True)
    cfg.setdefault("fractional_kelly_enabled", False)
    return cfg
