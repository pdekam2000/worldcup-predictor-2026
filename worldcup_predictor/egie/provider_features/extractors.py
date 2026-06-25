"""Extract paid-provider fields from stored raw payloads."""

from __future__ import annotations

import json
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import parse_snapshot_payload
from worldcup_predictor.egie.config import PROVIDER_API_FOOTBALL, PROVIDER_SPORTMONKS
from worldcup_predictor.egie.readers.api_football_raw import load_fixture_item_from_egie
from worldcup_predictor.egie.storage.repository import EgieRawStoreRepository
from worldcup_predictor.providers.sportmonks_xg_extraction import parse_sportmonks_xg_match


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_api_football_fixture_statistics(payload: Any) -> dict[str, float | None]:
    """Parse API-Football fixture statistics response."""
    out: dict[str, float | None] = {
        "home_shots": None,
        "away_shots": None,
        "home_shots_on_target": None,
        "away_shots_on_target": None,
        "home_dangerous_attacks": None,
        "away_dangerous_attacks": None,
    }
    if not payload:
        return out
    if isinstance(payload, dict) and "response" in payload and "endpoint" in payload:
        payload = payload.get("response")
    rows = payload.get("response") if isinstance(payload, dict) and "response" in payload else payload
    if not isinstance(rows, list) or len(rows) < 2:
        return out
    home_stats = rows[0].get("statistics") if isinstance(rows[0], dict) else []
    away_stats = rows[1].get("statistics") if isinstance(rows[1], dict) else []

    def pick(stats: list, *names: str) -> float | None:
        for item in stats:
            if not isinstance(item, dict):
                continue
            st = item.get("type") or {}
            if isinstance(st, str):
                label = st.lower()
            elif isinstance(st, dict):
                label = str(st.get("name") or "").lower()
            else:
                label = ""
            if any(n in label for n in names):
                return _float(item.get("value"))
        return None

    out["home_shots"] = pick(home_stats or [], "total shots", "shots total")
    out["away_shots"] = pick(away_stats or [], "total shots", "shots total")
    out["home_shots_on_target"] = pick(home_stats or [], "shots on goal", "on target")
    out["away_shots_on_target"] = pick(away_stats or [], "shots on goal", "on target")
    out["home_dangerous_attacks"] = pick(home_stats or [], "dangerous attack")
    out["away_dangerous_attacks"] = pick(away_stats or [], "dangerous attack")
    return out


def parse_odds_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, float | None]:
    if not snapshots:
        return {
            "odds_implied_home": None,
            "odds_implied_away": None,
            "odds_implied_draw": None,
            "odds_movement_home": None,
            "odds_implied_over_25": None,
            "odds_implied_under_25": None,
            "odds_implied_btts_yes": None,
            "odds_implied_btts_no": None,
        }

    def _parse_row(row: dict[str, Any]) -> dict[str, float | None]:
        payload = row.get("payload") or row
        fixture_id = row.get("fixture_id")
        captured_at = row.get("snapshot_at") or (
            payload.get("snapshot_at") if isinstance(payload, dict) else None
        )
        return parse_snapshot_payload(
            payload,
            fixture_id=int(fixture_id) if fixture_id is not None else None,
            captured_at=str(captured_at) if captured_at else None,
        )

    latest = _parse_row(snapshots[-1])
    first = _parse_row(snapshots[0])
    move = None
    if latest.get("odds_implied_home") is not None and first.get("odds_implied_home") is not None:
        move = round(float(latest["odds_implied_home"]) - float(first["odds_implied_home"]), 4)

    return {
        "odds_implied_home": _float(latest.get("odds_implied_home")),
        "odds_implied_away": _float(latest.get("odds_implied_away")),
        "odds_implied_draw": _float(latest.get("odds_implied_draw")),
        "odds_movement_home": move,
        "odds_implied_over_25": _float(latest.get("odds_implied_over_25")),
        "odds_implied_under_25": _float(latest.get("odds_implied_under_25")),
        "odds_implied_btts_yes": _float(latest.get("odds_implied_btts_yes")),
        "odds_implied_btts_no": _float(latest.get("odds_implied_btts_no")),
    }


def parse_lineups_payload(payload: Any) -> dict[str, float | None]:
    """Crude lineup strength from starter count / formation presence."""
    rows = payload.get("response") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or len(rows) < 2:
        return {"lineup_strength_home": None, "lineup_strength_away": None}
    strengths: list[float | None] = []
    for row in rows[:2]:
        start_xi = row.get("startXI") if isinstance(row, dict) else None
        if isinstance(start_xi, list) and len(start_xi) >= 9:
            strengths.append(round(min(1.0, len(start_xi) / 11.0), 4))
        else:
            strengths.append(None)
    return {
        "lineup_strength_home": strengths[0] if strengths else None,
        "lineup_strength_away": strengths[1] if len(strengths) > 1 else None,
    }


def parse_injuries_payload(payload: Any) -> dict[str, float | None]:
    rows = payload.get("response") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        return {"injuries_impact_home": None, "injuries_impact_away": None}
    home_n = away_n = 0
    for row in rows:
        team = str((row.get("team") or {}).get("name") or "").lower()
        side = str(row.get("team", {}).get("id") or "")
        if not team and not side:
            continue
        # injuries list doesn't always label home/away — count total split heuristically later
        home_n += 1
    total = len(rows)
    return {
        "injuries_impact_home": round(min(1.0, home_n / 5.0), 4) if total else None,
        "injuries_impact_away": round(min(1.0, max(0, total - home_n) / 5.0), 4) if total else None,
    }


def load_sportmonks_fixture_raw(
    fixture_id: int,
    *,
    store: EgieRawStoreRepository | None = None,
) -> dict[str, Any] | None:
    repo = store or EgieRawStoreRepository()
    for resource in ("xg", "fixture_statistics", "fixtures"):
        row = repo.get_latest_raw(
            provider=PROVIDER_SPORTMONKS,
            resource_type=resource,
            fixture_id=int(fixture_id),
        )
        if row:
            payload = row.get("payload_json")
            if isinstance(payload, dict):
                return payload
            if isinstance(payload, str):
                try:
                    return json.loads(payload)
                except json.JSONDecodeError:
                    pass
    return None


def parse_sportmonks_pressure(raw: dict[str, Any] | None) -> dict[str, float | None]:
    """Derive pressure proxy from Sportmonks statistics or xG open-play share."""
    if not raw:
        return {"pressure_index_home": None, "pressure_index_away": None}
    stats = raw.get("statistics") or raw.get("data", {}).get("statistics")
    if isinstance(stats, list):
        home_p = away_p = None
        for block in stats:
            if not isinstance(block, dict):
                continue
            loc = str(block.get("location") or "").lower()
            for metric in block.get("data") or []:
                if not isinstance(metric, dict):
                    continue
                label = str(metric.get("type", {}).get("name") or "").lower()
                if "ball possession" in label or "possession" in label:
                    val = _float(metric.get("value"))
                    if "home" in loc:
                        home_p = val
                    elif "away" in loc:
                        away_p = val
        if home_p is not None:
            home_p = home_p / 100.0 if home_p > 1 else home_p
        if away_p is not None:
            away_p = away_p / 100.0 if away_p > 1 else away_p
        if home_p is not None or away_p is not None:
            return {
                "pressure_index_home": home_p,
                "pressure_index_away": away_p,
            }
    parsed = parse_sportmonks_xg_match(raw)
    team = parsed.get("team") or {}
    hx = _float(team.get("home_xg"))
    ax = _float(team.get("away_xg"))
    if hx is not None and ax is not None and (hx + ax) > 0:
        return {
            "pressure_index_home": round(hx / (hx + ax), 4),
            "pressure_index_away": round(ax / (hx + ax), 4),
        }
    return {"pressure_index_home": None, "pressure_index_away": None}


def parse_xg_fields(raw: dict[str, Any] | None) -> dict[str, float | None]:
    parsed = parse_sportmonks_xg_match(raw)
    team = parsed.get("team") or {}
    return {
        "home_xg_for": _float(team.get("home_xg")),
        "away_xg_for": _float(team.get("away_xg")),
        "home_xg_against": _float(team.get("away_xga") or team.get("away_xg")),
        "away_xg_against": _float(team.get("home_xg")),
    }


def load_sqlite_xg_payload(repo, fixture_id: int) -> dict[str, Any] | None:
    row = repo._conn.execute(
        "SELECT payload_json FROM xg_snapshots WHERE fixture_id = ? ORDER BY snapshot_at DESC LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload_json"])
    except (json.JSONDecodeError, TypeError):
        return None
