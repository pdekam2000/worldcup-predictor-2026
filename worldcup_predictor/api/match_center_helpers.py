"""Match Center API helpers — aggregation and prediction summaries (no engine changes)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from worldcup_predictor.config.competitions import (
    COMPETITION_REGISTRY,
    CompetitionConfig,
    list_competition_keys,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

_COMPETITION_EMOJI: dict[str, str] = {
    "world_cup_2026": "🏆",
    "champions_league": "🇪🇺",
    "europa_league": "🇪🇺",
    "conference_league": "🇪🇺",
    "premier_league": "🏴",
    "la_liga": "🇪🇸",
    "serie_a": "🇮🇹",
    "bundesliga": "🇩🇪",
    "ligue_1": "🇫🇷",
    "eredivisie": "🇳🇱",
    "primeira_liga": "🇵🇹",
    "super_lig": "🇹🇷",
    "saudi_pro_league": "🇸🇦",
    "mls": "🇺🇸",
}


def competition_emoji(key: str) -> str:
    return _COMPETITION_EMOJI.get(key, "⚽")


def competition_to_api_dict(comp: CompetitionConfig, *, upcoming_count: int = 0) -> dict[str, Any]:
    return {
        "key": comp.key,
        "name": comp.name,
        "country": comp.country,
        "type": comp.compensation_type,
        "season": comp.season,
        "league_id": comp.league_id,
        "enabled": comp.enabled,
        "emoji": competition_emoji(comp.key),
        "logo_url": None,
        "upcoming_count": upcoming_count,
        "supports_table": comp.supports_table,
        "supports_knockout": comp.supports_knockout,
    }


def list_enabled_competitions() -> list[CompetitionConfig]:
    return [COMPETITION_REGISTRY[k] for k in list_competition_keys(enabled_only=True)]


def _parse_payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def extract_prediction_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Lightweight card summary from stored/cached prediction payload."""
    if not payload:
        return {}

    pick = (
        payload.get("best_available_pick")
        or payload.get("value_pick")
        or payload.get("safe_pick")
        or payload.get("user_visible_pick")
    )
    market = None
    selection = None
    confidence = payload.get("confidence")
    if isinstance(pick, dict):
        market = pick.get("market") or pick.get("market_id")
        selection = pick.get("pick") or pick.get("selection") or pick.get("label")
        confidence = pick.get("confidence") or pick.get("probability") or confidence
    elif payload.get("prediction"):
        market = "1x2"
        selection = payload.get("prediction")

    tier = payload.get("pick_tier") or (payload.get("accuracy_tracking") or {}).get("pick_tier")
    risk = payload.get("risk_level") or "medium"
    no_bet = bool(payload.get("no_bet"))

    stars = 3
    if tier in ("elite", "official", "production_ready"):
        stars = 5
    elif tier in ("value", "paper_ready"):
        stars = 4
    elif tier in ("caution", "research_only"):
        stars = 2
    if no_bet:
        stars = 1

    conf_pct = None
    if confidence is not None:
        try:
            c = float(confidence)
            conf_pct = round(c * 100 if c <= 1 else c, 1)
        except (TypeError, ValueError):
            conf_pct = None

    value_grade = "—"
    if conf_pct is not None:
        if conf_pct >= 80:
            value_grade = "A+"
        elif conf_pct >= 70:
            value_grade = "A"
        elif conf_pct >= 60:
            value_grade = "B"
        else:
            value_grade = "C"

    label_map = {
        "home": "Home Win",
        "away": "Away Win",
        "draw": "Draw",
        "home_win": "Home Win",
        "away_win": "Away Win",
        "over_2_5": "Over 2.5",
        "under_2_5": "Under 2.5",
        "yes": "BTTS Yes",
        "no": "BTTS No",
    }
    best_pick_label = label_map.get(str(selection or "").lower(), selection)
    if market and best_pick_label:
        best_pick_label = f"{market}: {best_pick_label}"

    return {
        "best_pick": best_pick_label or None,
        "confidence": conf_pct,
        "value_rating": value_grade,
        "stars": stars,
        "tier": tier,
        "risk_level": risk,
        "is_elite_pick": stars >= 4 and not no_bet,
        "no_bet": no_bet,
    }


def load_prediction_summaries(
    settings: Settings | None = None,
    *,
    competition_key: str | None = None,
) -> dict[int, dict[str, Any]]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    summaries: dict[int, dict[str, Any]] = {}
    keys = [competition_key] if competition_key else list_competition_keys(enabled_only=True)
    for key in keys:
        rows = repo.list_worldcup_stored_predictions(competition_key=key, limit=500, offset=0)
        for row in rows:
            fid = row.get("fixture_id")
            if fid is None:
                continue
            payload = _parse_payload(row)
            if payload:
                summaries[int(fid)] = extract_prediction_summary(payload)
    return summaries


def apply_season_override(comp: CompetitionConfig, season: int | None) -> CompetitionConfig:
    if season is not None:
        return replace(comp, season=season)
    return comp
