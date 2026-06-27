"""Smart alert rules — dedup, quiet hours, meaningful changes — Phase A19."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.ai_assistant.constants import (
    ODDS_MOVEMENT_THRESHOLD_PCT,
    QUALITY_CHANGE_THRESHOLD,
)


def is_quiet_hours(prefs: dict[str, Any]) -> bool:
    start = prefs.get("quiet_hours_start")
    end = prefs.get("quiet_hours_end")
    if not start or not end:
        return False
    tz_name = prefs.get("timezone") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    try:
        sh, sm = map(int, str(start).split(":")[:2])
        eh, em = map(int, str(end).split(":")[:2])
    except (ValueError, TypeError):
        return False
    cur_mins = now.hour * 60 + now.minute
    start_mins = sh * 60 + sm
    end_mins = eh * 60 + em
    if start_mins <= end_mins:
        return start_mins <= cur_mins < end_mins
    return cur_mins >= start_mins or cur_mins < end_mins


def passes_quality_threshold(prefs: dict[str, Any], score: float | None) -> bool:
    min_q = float(prefs.get("min_bet_quality") or 0)
    if score is None:
        return True
    return float(score) >= min_q


def is_meaningful_quality_change(old_score: float | None, new_score: float | None) -> bool:
    if old_score is None or new_score is None:
        return new_score is not None and float(new_score) > 0
    return abs(float(new_score) - float(old_score)) >= QUALITY_CHANGE_THRESHOLD


def is_meaningful_odds_movement(old_odds: float | None, new_odds: float | None) -> bool:
    if not old_odds or not new_odds or float(old_odds) <= 1:
        return False
    pct = abs(float(new_odds) - float(old_odds)) / float(old_odds) * 100
    return pct >= ODDS_MOVEMENT_THRESHOLD_PCT


def should_notify_user(prefs: dict[str, Any], *, alert_type: str) -> bool:
    if is_quiet_hours(prefs):
        return alert_type in ("paper_bet_settled", "match_final_hours")
    freq = (prefs.get("alert_frequency") or "normal").lower()
    if freq == "low" and alert_type in ("quality_increase", "quality_decrease", "odds_movement"):
        return False
    return True


def build_dedup_key(alert_type: str, fixture_id: int | None, extra: str = "") -> str:
    fid = fixture_id or 0
    return f"{alert_type}:{fid}:{extra}"
