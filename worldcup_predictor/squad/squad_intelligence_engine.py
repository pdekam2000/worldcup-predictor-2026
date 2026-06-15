"""Phase 55 — Bench depth and squad age intelligence from existing squad API data."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.integrations.player_feature_extraction import _float_val, _int_val
from worldcup_predictor.prediction.player_position_utils import normalize_position

API_SPORTS_DEEP_KEY = "api_sports_deep"

_POSITION_GROUPS = ("Goalkeeper", "Defender", "Midfielder", "Forward")


def _pos_group(raw: str) -> str:
    key = normalize_position(raw).upper()
    if key in {"G", "GK"}:
        return "Goalkeeper"
    if key in {"D", "DF", "DEF", "CB", "LB", "RB"}:
        return "Defender"
    if key in {"M", "MF", "MID", "CM", "DM", "AM"}:
        return "Midfielder"
    if key in {"F", "FW", "ST", "CF", "ATT"}:
        return "Forward"
    return "Midfielder"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def build_squad_age_profile(players: list[dict[str, Any]]) -> dict[str, Any]:
    ages = [_int_val(p.get("age")) for p in players if isinstance(p, dict)]
    ages = [a for a in ages if a is not None and 15 <= a <= 45]
    if not ages:
        return {
            "available": False,
            "average_age": None,
            "median_age": None,
            "experience_score": 50.0,
        }
    ages.sort()
    avg = sum(ages) / len(ages)
    mid = ages[len(ages) // 2]
    # Sweet spot 26–29 for tournament experience; conservative scoring
    if 26 <= avg <= 29:
        exp = 72.0 + (avg - 27) * 2
    elif avg < 26:
        exp = 55.0 + (avg - 22) * 3
    else:
        exp = 68.0 - (avg - 29) * 2
    return {
        "available": True,
        "average_age": round(avg, 1),
        "median_age": float(mid),
        "experience_score": round(_clamp(exp, 0, 100), 1),
        "squad_size": len(players),
    }


def build_bench_depth_intelligence(
    squad_players: list[dict[str, Any]],
    *,
    player_quality_rows: list[dict[str, Any]] | None = None,
    lineup_starters: list[str] | None = None,
    unavailable_names: list[str] | None = None,
) -> dict[str, Any]:
    """BenchDepthIntelligenceV1 — 0–100 depth score per team."""
    by_group: dict[str, list[dict[str, Any]]] = {g: [] for g in _POSITION_GROUPS}
    for p in squad_players:
        if not isinstance(p, dict):
            continue
        grp = _pos_group(str(p.get("position") or ""))
        by_group[grp].append(p)

    quality_by_name: dict[str, float] = {}
    for row in player_quality_rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("player") or "").lower()
        if name:
            quality_by_name[name] = _float_val(row.get("player_rating") or row.get("score_hint")) or 55.0

    depth_by_position: dict[str, int] = {}
    replacement_scores: list[float] = []
    starters = {s.lower() for s in (lineup_starters or []) if s}

    for grp, members in by_group.items():
        depth_by_position[grp] = len(members)
        bench = [m for m in members if str(m.get("name", "")).lower() not in starters]
        for b in bench[:3]:
            nm = str(b.get("name", "")).lower()
            replacement_scores.append(quality_by_name.get(nm, 52.0))

    min_depth = min(depth_by_position.values()) if depth_by_position else 0
    avg_depth = sum(depth_by_position.values()) / max(len(_POSITION_GROUPS), 1)
    depth_score = _clamp(35 + min_depth * 8 + avg_depth * 2, 0, 100)

    if replacement_scores:
        depth_score = _clamp(depth_score * 0.7 + (sum(replacement_scores) / len(replacement_scores)) * 0.3, 0, 100)

    missing_impact = 0.0
    for name in unavailable_names or []:
        key = name.lower()
        if key in quality_by_name and quality_by_name[key] >= 65:
            missing_impact += 12.0
        elif key in starters:
            missing_impact += 8.0
    missing_impact = min(missing_impact, 40.0)
    effective_depth = round(_clamp(depth_score - missing_impact * 0.5, 0, 100), 1)

    rotation_risk = "Low"
    if effective_depth < 45:
        rotation_risk = "High"
    elif effective_depth < 62:
        rotation_risk = "Medium"

    return {
        "depth_score": round(depth_score, 1),
        "effective_depth_score": effective_depth,
        "depth_by_position": depth_by_position,
        "replacement_quality_avg": round(sum(replacement_scores) / len(replacement_scores), 1) if replacement_scores else None,
        "missing_starter_impact": round(missing_impact, 1),
        "rotation_risk": rotation_risk,
        "available": bool(squad_players),
    }


def build_squad_intelligence_bundle(report: Any) -> dict[str, Any]:
    """Build bench depth + age profile for home/away from supplemental deep data."""
    deep = (getattr(report, "supplemental_sources", None) or {}).get(API_SPORTS_DEEP_KEY) or {}
    squads = deep.get("squads") or {}
    if not squads:
        return {"available": False}

    from worldcup_predictor.integrations.api_sports_deep_data import deep_player_rows_for_team

    home_name = getattr(getattr(report, "home_team", None), "team_name", "Home")
    away_name = getattr(getattr(report, "away_team", None), "team_name", "Away")
    lineup_items = (getattr(report, "lineups", None) or {}).get("items") or []

    def _starters(team_name: str) -> list[str]:
        names: list[str] = []
        for item in lineup_items:
            if not isinstance(item, dict):
                continue
            if str((item.get("team") or {}).get("name", "")).lower() != team_name.lower():
                continue
            for entry in item.get("startXI") or []:
                if isinstance(entry, dict):
                    n = (entry.get("player") or {}).get("name")
                    if n:
                        names.append(str(n))
        return names

    def _unavailable(team_name: str) -> list[str]:
        intel = report.home_team if team_name == home_name else report.away_team
        inj = getattr(getattr(intel, "injuries", None), "players", None) or []
        out: list[str] = []
        for row in inj:
            if not isinstance(row, dict):
                continue
            player = row.get("player") or {}
            name = player.get("name") if isinstance(player, dict) else row.get("name")
            if name:
                out.append(str(name))
        return out

    bundle: dict[str, Any] = {"available": True, "home": {}, "away": {}}
    for side, team_name in (("home", home_name), ("away", away_name)):
        squad = squads.get(side) or []
        quality_rows = deep_player_rows_for_team(report, team_name)
        age = build_squad_age_profile(squad if isinstance(squad, list) else [])
        depth = build_bench_depth_intelligence(
            squad if isinstance(squad, list) else [],
            player_quality_rows=quality_rows,
            lineup_starters=_starters(team_name),
            unavailable_names=_unavailable(team_name),
        )
        bundle[side] = {
            "squad_age_profile": age,
            "bench_depth": depth,
        }
    return bundle
