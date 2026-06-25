"""Map Sportmonks enrichment payloads into intelligence report gaps — no new API calls."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

from worldcup_predictor.domain.intelligence import InjuryReport, MatchIntelligenceReport
from worldcup_predictor.intelligence.sportmonks_odds_prediction_engine import (
    parse_odds_predictions_from_fixture,
)
from worldcup_predictor.intelligence.sportmonks_xg_intelligence_engine import (
    parse_sportmonks_xg_from_fixture,
)

logger = logging.getLogger(__name__)

SPORTMONKS_SUPPLEMENTAL_KEY = "sportmonks"
SPORTMONKS_ODDS_PREDICTION_KEY = "sportmonks_odds_prediction"
SPORTMONKS_XG_INTELLIGENCE_KEY = "sportmonks_xg_intelligence"

_XG_TYPE_HINTS = frozenset(
    {
        "expected goals",
        "expected_goals",
        "xg",
        "xgoals",
        "expected goals (xg)",
    }
)


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _participant_location(participant: dict[str, Any]) -> str:
    meta = participant.get("meta") or {}
    return str(meta.get("location") or "").lower()


def _participant_team_name(participant: dict[str, Any]) -> str:
    return str(participant.get("name") or "")


def _participant_team_id(participant: dict[str, Any]) -> int | None:
    try:
        pid = participant.get("id")
        return int(pid) if pid is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stat_label(entry: dict[str, Any]) -> str:
    type_block = entry.get("type")
    if isinstance(type_block, dict):
        for key in ("name", "developer_name", "code"):
            text = type_block.get(key)
            if text:
                return str(text).lower()
    for key in ("name", "developer_name", "code", "description"):
        text = entry.get(key)
        if text:
            return str(text).lower()
    return ""


def _stat_value(entry: dict[str, Any]) -> float | None:
    data = entry.get("data")
    if isinstance(data, dict):
        val = _float_or_none(data.get("value"))
        if val is not None:
            return val
    return _float_or_none(entry.get("value"))


def map_sportmonks_payload_fields(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Inventory available top-level Sportmonks fixture fields (for audits)."""
    if not isinstance(raw, dict):
        return {
            "available": False,
            "fields_present": [],
            "has_participants": False,
            "has_lineups": False,
            "has_formations": False,
            "has_statistics": False,
            "has_sidelined": False,
            "has_scores": False,
            "has_odds": False,
            "has_predictions": False,
            "has_xg_fixture": False,
        }
    keys = [k for k, v in raw.items() if v not in (None, [], {}, "")]
    return {
        "available": True,
        "fields_present": sorted(keys),
        "has_participants": bool(_safe_list(raw.get("participants"))),
        "has_lineups": bool(_safe_list(raw.get("lineups"))),
        "has_formations": bool(_safe_list(raw.get("formations"))),
        "has_statistics": bool(_safe_list(raw.get("statistics"))),
        "has_sidelined": bool(_safe_list(raw.get("sidelined"))),
        "has_scores": bool(_safe_list(raw.get("scores"))),
        "has_odds": bool(_safe_list(raw.get("odds"))),
        "has_predictions": bool(_safe_list(raw.get("predictions"))),
        "has_xg_fixture": raw.get("xGFixture") is not None or bool(_safe_list(raw.get("expected"))),
        "sportmonks_fixture_id": raw.get("id"),
    }


def _parse_sidelined_to_injuries(
    sidelined: list[Any],
    *,
    participant_id: int | None,
    team_name: str,
    team_id: int | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in sidelined:
        if not isinstance(row, dict):
            continue
        row_participant = row.get("participant_id")
        if participant_id is not None and row_participant not in (None, participant_id):
            continue
        sideline = row.get("sideline") if isinstance(row.get("sideline"), dict) else row
        if not isinstance(sideline, dict):
            continue
        player = sideline.get("player") if isinstance(sideline.get("player"), dict) else {}
        player_id = player.get("id") or sideline.get("player_id")
        player_name = player.get("name") or sideline.get("player_name") or "Unknown"
        category = str(sideline.get("category") or sideline.get("type") or "")
        reason = str(sideline.get("reason") or sideline.get("description") or category)
        out.append(
            {
                "team": {"id": team_id, "name": team_name},
                "player": {
                    "id": player_id,
                    "name": player_name,
                    "type": category,
                    "reason": reason,
                    "pos": player.get("position") or player.get("detailed_position"),
                },
                "source": "sportmonks",
            }
        )
    return out


def _lineup_entries_to_api_shape(
    lineups: list[Any],
    *,
    participant_id: int | None,
    team_name: str,
    team_id: int | None,
    formation: str | None,
) -> dict[str, Any] | None:
    starters: list[dict[str, Any]] = []
    subs: list[dict[str, Any]] = []
    for row in lineups:
        if not isinstance(row, dict):
            continue
        row_team_id = row.get("team_id") or row.get("participant_id")
        if participant_id is not None and row_team_id not in (None, participant_id):
            continue
        type_id = row.get("type_id")
        entry = {
            "player": {
                "id": row.get("player_id"),
                "name": row.get("player_name") or row.get("name"),
                "pos": _position_code_from_id(row.get("position_id")),
                "number": row.get("jersey_number"),
            }
        }
        if type_id == 12 or str(row.get("type") or "").lower() in {"bench", "substitute", "sub"}:
            subs.append(entry)
        else:
            starters.append(entry)
    if not starters and not subs:
        return None
    return {
        "team": {"id": team_id, "name": team_name},
        "formation": formation or "",
        "startXI": starters,
        "substitutes": subs,
        "source": "sportmonks",
    }


def _position_code_from_id(position_id: Any) -> str:
    mapping = {24: "G", 25: "D", 26: "M", 27: "F"}
    try:
        return mapping.get(int(position_id), "")
    except (TypeError, ValueError):
        return ""


def _formation_for_participant(formations: list[Any], participant_id: int | None) -> str | None:
    for row in formations:
        if not isinstance(row, dict):
            continue
        if participant_id is not None and row.get("participant_id") not in (None, participant_id):
            continue
        formation = row.get("formation") or row.get("name")
        if formation:
            return str(formation)
    return None


def _parse_statistics(
    statistics: list[Any],
    participants: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, Any]]:
    """Return per-side xG map and flat home_/away_ stat keys for supplemental use."""
    xg: dict[str, float] = {}
    flat: dict[str, Any] = {}
    id_to_side: dict[int, str] = {}
    name_to_side: dict[str, str] = {}
    for participant in participants:
        if not isinstance(participant, dict):
            continue
        loc = _participant_location(participant)
        if loc not in {"home", "away"}:
            continue
        pid = _participant_team_id(participant)
        if pid is not None:
            id_to_side[pid] = loc
        name_to_side[_participant_team_name(participant).lower()] = loc

    for entry in statistics:
        if not isinstance(entry, dict):
            continue
        label = _stat_label(entry)
        value = _stat_value(entry)
        if value is None:
            continue
        participant_id = entry.get("participant_id")
        side = id_to_side.get(int(participant_id)) if participant_id is not None else None
        if side is None:
            continue
        if any(hint in label for hint in _XG_TYPE_HINTS):
            xg[side] = value
        key_suffix = label.replace(" ", "_").replace("%", "pct")
        flat[f"{side}_{key_suffix}"] = value
    return xg, flat


def normalize_sportmonks_fixture(
    raw: dict[str, Any],
    *,
    home_team_name: str,
    away_team_name: str,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
) -> dict[str, Any]:
    """Normalize Sportmonks fixture object into supplemental + gap-fill friendly structure."""
    participants = [p for p in _safe_list(raw.get("participants")) if isinstance(p, dict)]
    home_part = next(
        (p for p in participants if _participant_location(p) == "home" or _participant_team_name(p) == home_team_name),
        None,
    )
    away_part = next(
        (p for p in participants if _participant_location(p) == "away" or _participant_team_name(p) == away_team_name),
        None,
    )
    home_pid = _participant_team_id(home_part) if home_part else home_team_id
    away_pid = _participant_team_id(away_part) if away_part else away_team_id
    home_name = _participant_team_name(home_part) if home_part else home_team_name
    away_name = _participant_team_name(away_part) if away_part else away_team_name

    formations = _safe_list(raw.get("formations"))
    lineups_raw = _safe_list(raw.get("lineups"))
    sidelined = _safe_list(raw.get("sidelined"))
    statistics = _safe_list(raw.get("statistics"))

    home_lineup = _lineup_entries_to_api_shape(
        lineups_raw,
        participant_id=home_pid,
        team_name=home_name,
        team_id=home_pid,
        formation=_formation_for_participant(formations, home_pid),
    )
    away_lineup = _lineup_entries_to_api_shape(
        lineups_raw,
        participant_id=away_pid,
        team_name=away_name,
        team_id=away_pid,
        formation=_formation_for_participant(formations, away_pid),
    )

    home_injuries = _parse_sidelined_to_injuries(
        sidelined, participant_id=home_pid, team_name=home_name, team_id=home_pid
    )
    away_injuries = _parse_sidelined_to_injuries(
        sidelined, participant_id=away_pid, team_name=away_name, team_id=away_pid
    )

    xg_map, stat_flat = _parse_statistics(statistics, participants)

    return {
        "field_map": map_sportmonks_payload_fields(raw),
        "participants": participants,
        "scores": _safe_list(raw.get("scores")),
        "lineups_api": [x for x in (home_lineup, away_lineup) if x],
        "injuries_api": home_injuries + away_injuries,
        "home_injuries": home_injuries,
        "away_injuries": away_injuries,
        "xg": xg_map,
        "match_statistics": stat_flat,
        "formations": formations,
        "sportmonks_fixture_id": raw.get("id"),
    }


def _premium_access_for_report(report: MatchIntelligenceReport) -> dict[str, bool] | None:
    meta = report.provider_metadata or {}
    direct = meta.get("sportmonks_premium_access")
    if isinstance(direct, dict):
        return direct
    unified = meta.get("sportmonks_unified") or {}
    nested = unified.get("premium_access")
    if isinstance(nested, dict):
        return nested

    fixture_id = getattr(report, "fixture_id", None)
    if fixture_id is not None:
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository
            from worldcup_predictor.providers.sportmonks_enrichment import _premium_access_from_row

            repo = FootballIntelligenceRepository()
            row = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(int(fixture_id))
            if row:
                return _premium_access_from_row(row)
        except Exception as exc:
            from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

            log_enrichment_failure(
                "worldcup_predictor.providers.sportmonks_consumption",
                exc,
                fixture_id=int(fixture_id) if fixture_id is not None else None,
                layer="premium_access_lookup",
            )
    return None


def _resolve_raw_fixture_data(report: MatchIntelligenceReport) -> tuple[dict[str, Any] | None, str]:
    """Prefer SQLite rows with full Phase 22C/22D includes over lookup fallback metadata."""
    fixture_id = getattr(report, "fixture_id", None)

    if fixture_id is not None:
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository
            from worldcup_predictor.providers.sportmonks_enrichment import _cache_includes_complete

            repo = FootballIntelligenceRepository()
            row = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(int(fixture_id))
            if row and row.get("raw_json") and _cache_includes_complete(row):
                payload = json.loads(row["raw_json"])
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, dict):
                    return data, "sqlite_cache_complete"
        except Exception as exc:
            from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

            log_enrichment_failure(
                "worldcup_predictor.providers.sportmonks_consumption",
                exc,
                fixture_id=int(fixture_id) if fixture_id is not None else None,
                layer="sqlite_cache_complete",
            )

    meta = report.provider_metadata or {}
    live = meta.get("sportmonks_fixture")
    if isinstance(live, dict) and live:
        return live, "provider_metadata"

    if fixture_id is not None:
        try:
            from worldcup_predictor.database.repository import FootballIntelligenceRepository

            repo = FootballIntelligenceRepository()
            row = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(int(fixture_id))
            if row and row.get("raw_json"):
                payload = json.loads(row["raw_json"])
                data = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(data, dict):
                    return data, "sqlite_cache"
        except Exception as exc:
            from worldcup_predictor.providers.safe_enrichment_logger import log_enrichment_failure

            log_enrichment_failure(
                "worldcup_predictor.providers.sportmonks_consumption",
                exc,
                fixture_id=int(fixture_id) if fixture_id is not None else None,
                layer="sqlite_cache_fallback",
            )
    return None, "none"


def _injuries_empty(team_intel: Any) -> bool:
    injuries = getattr(team_intel, "injuries", None)
    if injuries is None:
        return True
    players = getattr(injuries, "players", None) or []
    return len(players) == 0


def _lineups_empty(report: MatchIntelligenceReport) -> bool:
    items = _safe_list((report.lineups or {}).get("items"))
    if not items:
        return True
    for item in items:
        if isinstance(item, dict) and _safe_list(item.get("startXI")):
            return False
    return True


def _fixture_stats_empty(report: MatchIntelligenceReport) -> bool:
    block = report.fixture_statistics or {}
    items = block.get("items") if isinstance(block, dict) else None
    return not items


def apply_sportmonks_consumption(report: MatchIntelligenceReport) -> MatchIntelligenceReport:
    """
    Consume existing Sportmonks payloads — API-Football first, Sportmonks gap-fill only.

    No provider calls. Safe to call on every cached/live intelligence report.
    """
    raw, raw_source = _resolve_raw_fixture_data(report)
    if not raw:
        return report

    home_name = report.home_team.team_name
    away_name = report.away_team.team_name
    normalized = normalize_sportmonks_fixture(
        raw,
        home_team_name=home_name,
        away_team_name=away_name,
        home_team_id=report.home_team.team_id,
        away_team_id=report.away_team.team_id,
    )

    supplemental = dict(report.supplemental_sources or {})
    premium_access = _premium_access_for_report(report)
    supplemental[SPORTMONKS_SUPPLEMENTAL_KEY] = {
        **normalized,
        "source": raw_source,
        "consumed": True,
        "premium_access": premium_access,
    }
    supplemental[SPORTMONKS_ODDS_PREDICTION_KEY] = parse_odds_predictions_from_fixture(raw)
    supplemental[SPORTMONKS_XG_INTELLIGENCE_KEY] = parse_sportmonks_xg_from_fixture(raw)
    try:
        from worldcup_predictor.providers.sportmonks_xg_extraction import (
            attach_sportmonks_xg_to_report,
        )

        report = attach_sportmonks_xg_to_report(report)
        supplemental = dict(report.supplemental_sources or {})
    except Exception:
        logger.debug("Sportmonks xG match extraction skipped", exc_info=True)

    missing = list(report.missing_data or [])
    sources = list(report.enrichment_sources or [])
    if "sportmonks" not in sources:
        sources.append("sportmonks")

    home_team = report.home_team
    away_team = report.away_team

    if _injuries_empty(home_team) and normalized.get("home_injuries"):
        home_team = replace(
            home_team,
            injuries=InjuryReport(
                team_name=home_name,
                team_id=home_team.team_id,
                players=list(normalized["home_injuries"]),
                source="live",
                available=True,
            ),
        )
        if "injuries" in missing:
            missing.remove("injuries")

    if _injuries_empty(away_team) and normalized.get("away_injuries"):
        away_team = replace(
            away_team,
            injuries=InjuryReport(
                team_name=away_name,
                team_id=away_team.team_id,
                players=list(normalized["away_injuries"]),
                source="live",
                available=True,
            ),
        )
        if "injuries" in missing:
            missing.remove("injuries")

    lineups_block = dict(report.lineups or {})
    if _lineups_empty(report) and normalized.get("lineups_api"):
        lineups_block = {
            "items": list(normalized["lineups_api"]),
            "available": True,
            "source": "sportmonks",
        }
        if "lineups" in missing:
            missing.remove("lineups")

    fixture_statistics = report.fixture_statistics
    if _fixture_stats_empty(report) and normalized.get("match_statistics"):
        fixture_statistics = {
            "items": [],
            "source": "sportmonks",
            "supplemental_flat": normalized["match_statistics"],
        }

    return replace(
        report,
        home_team=home_team,
        away_team=away_team,
        lineups=lineups_block if lineups_block else report.lineups,
        fixture_statistics=fixture_statistics,
        supplemental_sources=supplemental,
        missing_data=missing,
        enrichment_sources=sources,
    )
