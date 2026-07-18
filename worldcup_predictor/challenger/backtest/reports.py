"""Backtest report helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_backtest_markdown(path: Path, title: str, payload: dict[str, Any]) -> None:
    lines = [f"# {title}", "", "```json", json.dumps(payload, indent=2, ensure_ascii=False, default=str)[:120000], "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
