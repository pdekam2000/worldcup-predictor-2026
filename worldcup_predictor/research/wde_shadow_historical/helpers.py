"""Shared helpers for WDE shadow historical CSV pipeline."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.intelligence.national_team._shared import normalize_team_name
from worldcup_predictor.research.wde_shadow_historical.constants import (
    PLAYED_STATUS_TOKENS,
    UNPLAYED_STATUS_TOKENS,
)


def connect_readonly(path: str | Path | None = None) -> sqlite3.Connection:
    from worldcup_predictor.database.connection import get_db_path

    db_path = get_db_path(path)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=120.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def table_count(conn: sqlite3.Connection, name: str) -> int:
    if not table_exists(conn, name):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) c FROM {name}").fetchone()["c"])


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def is_played_status(status: str | None) -> bool:
    token = str(status or "").strip().lower()
    if token in PLAYED_STATUS_TOKENS:
        return True
    if token in UNPLAYED_STATUS_TOKENS:
        return False
    return False


def is_future_event(event_date: str | None) -> bool:
    if not event_date:
        return False
    try:
        d = date.fromisoformat(str(event_date)[:10])
    except ValueError:
        return False
    return d > datetime.now(timezone.utc).date()


def label_1x2(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def label_over_25(home_goals: int, away_goals: int) -> str:
    return "over_2_5" if (home_goals + away_goals) > 2 else "under_2_5"


def label_btts(home_goals: int, away_goals: int) -> str:
    return "yes" if home_goals > 0 and away_goals > 0 else "no"


def implied_probs(odds: dict[str, float | None]) -> dict[str, float | None]:
    inv: dict[str, float] = {}
    for key, val in odds.items():
        if val is not None and val > 1.0:
            inv[key] = 1.0 / val
    total = sum(inv.values())
    if total <= 0:
        return {k: None for k in odds}
    return {k: round(inv[k] / total, 6) if k in inv else None for k in odds}


def load_raw_row(raw_json: str | None) -> dict[str, Any]:
    if not raw_json:
        return {}
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def team_alias_collision_count(conn: sqlite3.Connection, *, limit_sample: int = 50_000) -> tuple[int, list[dict[str, Any]]]:
    """Count normalized team names with multiple raw spellings (internal alias risk)."""
    if not table_exists(conn, "external_match_history_staging"):
        return 0, []
    rows = conn.execute(
        """
        SELECT home_team AS team FROM external_match_history_staging WHERE home_team IS NOT NULL
        UNION ALL
        SELECT away_team AS team FROM external_match_history_staging WHERE away_team IS NOT NULL
        LIMIT ?
        """,
        (int(limit_sample),),
    ).fetchall()
    by_norm: dict[str, set[str]] = {}
    for row in rows:
        raw = str(row["team"]).strip()
        if not raw:
            continue
        norm = normalize_team_name(raw)
        by_norm.setdefault(norm, set()).add(raw)
    collisions = [
        {"normalized": norm, "variants": sorted(variants), "variant_count": len(variants)}
        for norm, variants in by_norm.items()
        if len(variants) > 1
    ]
    collisions.sort(key=lambda x: -x["variant_count"])
    return len(collisions), collisions[:25]


def crosswalk_summary() -> dict[str, Any]:
    from worldcup_predictor.research.wde_shadow_historical.constants import CROSSWALK_PATH

    if not CROSSWALK_PATH.exists():
        return {}
    try:
        return json.loads(CROSSWALK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
