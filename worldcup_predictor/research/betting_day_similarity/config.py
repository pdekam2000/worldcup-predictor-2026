"""Config loader — research-only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else Path(__file__).with_name("default_config.json")
    return json.loads(p.read_text(encoding="utf-8"))
