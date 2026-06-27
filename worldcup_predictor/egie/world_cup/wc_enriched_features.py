"""Rebuild enriched WC EGIE feature rows — Phase 62B (data only)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.world_cup.competition_tags import classify_fixture_competition_type
from worldcup_predictor.egie.world_cup.config import (
    COMPETITION_TYPE_FINALS,
    RAW_CACHE_DIR,
    WORLD_CUP_COMPETITION_KEY,
)
from worldcup_predictor.egie.world_cup.wc_feature_builder import WC_FEATURE_VERSION, build_wc_timing_features
from worldcup_predictor.goal_timing.data.stored_adapter import StoredGoalTimingAdapter
from worldcup_predictor.goal_timing.minute_ranges import minute_to_range_key

logger = logging.getLogger(__name__)

_CONFEDERATION_HINTS = {
    "Brazil": "CONMEBOL",
    "Argentina": "CONMEBOL",
    "Germany": "UEFA",
    "France": "UEFA",
    "Spain": "UEFA",
    "England": "UEFA",
    "USA": "CONCACAF",
    "Mexico": "CONCACAF",
    "Japan": "AFC",
    "South Korea": "AFC",
    "Australia": "AFC",
    "Morocco": "CAF",
    "Senegal": "CAF",
}


def _load_xg_snapshot(repo: FootballIntelligenceRepository, fixture_id: int) -> dict[str, Any]:
    if repo.has_xg_snapshot(fixture_id):
        rows = repo._conn.execute(
            "SELECT payload_json FROM xg_snapshots WHERE fixture_id = ? ORDER BY id DESC LIMIT 1",
            (fixture_id,),
        ).fetchone()
        if rows and rows[0]:
            try:
                return json.loads(rows[0])
            except json.JSONDecodeError:
                pass
    cache = Path.cwd() / RAW_CACHE_DIR / "sportmonks" / "fixture_enrichment"
    # fallback file from raw_cache sportmonks path
    for path in (Path.cwd() / RAW_CACHE_DIR / "sportmonks").glob(f"*.json"):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            meta = blob.get("payload") or {}
            if isinstance(meta, dict) and meta.get("data"):
                continue
        except (json.JSONDecodeError, OSError):
            continue
    return {}


def _load_lineup_enrichment(repo: FootballIntelligenceRepository, fixture_id: int) -> dict[str, Any]:
    row = repo.get_fixture_enrichment_row(fixture_id)
    if not row or not row.get("lineups_json"):
        return {"lineup_available": False, "lineup_missing_reason": "provider_no_data"}
    try:
        lineups = json.loads(row["lineups_json"])
    except (json.JSONDecodeError, TypeError):
        return {"lineup_available": False, "lineup_missing_reason": "parse_error"}
    return {
        "lineup_available": bool(lineups),
        "lineups": lineups,
        "lineup_count": len(lineups) if isinstance(lineups, list) else 0,
    }


def _goal_labels(repo: FootballIntelligenceRepository, fixture_id: int, home: str, away: str) -> dict[str, Any]:
    events = repo.list_fixture_goal_events(fixture_id)
    if not events:
        return {
            "goal_event_count": 0,
            "first_goal_team": None,
            "first_goal_minute": None,
            "goal_timing_label": None,
        }
    first = events[0]
    minute = first.get("minute")
    team = first.get("team")
    side = "home" if team == home else "away" if team == away else "unknown"
    timing_label = minute_to_range_key(int(minute)) if minute is not None else None
    return {
        "goal_event_count": len(events),
        "first_goal_team": side,
        "first_goal_minute": minute,
        "goal_timing_label": timing_label,
        "goal_events_available": True,
    }


def rebuild_enriched_feature_rows(
    *,
    settings: Settings | None = None,
    limit: int = 800,
    finals_only: bool = True,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    stored = StoredGoalTimingAdapter(settings)
    out_dir = Path.cwd() / RAW_CACHE_DIR / "goal_timing_features_enriched"
    out_dir.mkdir(parents=True, exist_ok=True)

    query = """
        SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.round_name,
               f.group_name, f.season, COALESCE(f.competition_type, 'world_cup_finals')
        FROM fixtures f
        WHERE f.competition_key = ?
    """
    params: list[Any] = [WORLD_CUP_COMPETITION_KEY]
    if finals_only:
        query += " AND COALESCE(f.competition_type, 'world_cup_finals') = ?"
        params.append(COMPETITION_TYPE_FINALS)
    query += " ORDER BY f.kickoff_utc DESC LIMIT ?"
    params.append(int(limit))

    rows = repo._conn.execute(query, params).fetchall()
    rebuilt = 0
    with_xg = 0
    with_lineup = 0
    with_goals = 0

    for r in rows:
        fid = int(r[0])
        home, away, kickoff = str(r[1] or ""), str(r[2] or ""), r[3]
        comp_type = str(r[7] or COMPETITION_TYPE_FINALS)
        kickoff_dt = stored.parse_kickoff(kickoff) if kickoff else None
        base = build_wc_timing_features(
            fid,
            competition_key=WORLD_CUP_COMPETITION_KEY,
            stored=stored,
            as_of=kickoff_dt,
            context={"home_team": home, "away_team": away},
            skip_provider=True,
        )
        xg = _load_xg_snapshot(repo, fid)
        if not xg.get("xg_available"):
            sm_row = repo._conn.execute(
                "SELECT payload_json FROM xg_snapshots WHERE fixture_id = ? ORDER BY id DESC LIMIT 1",
                (fid,),
            ).fetchone()
            if sm_row and sm_row[0]:
                try:
                    xg = json.loads(sm_row[0])
                except json.JSONDecodeError:
                    pass
        lineup = _load_lineup_enrichment(repo, fid)
        goals = _goal_labels(repo, fid, home, away)
        odds = repo.has_odds_snapshot(fid)

        enriched = {
            **base,
            "feature_version": f"{WC_FEATURE_VERSION}_62b",
            "competition_type": comp_type,
            "tournament_stage": str(r[4] or r[5] or ""),
            "season": r[6],
            "confederation_home": _CONFEDERATION_HINTS.get(home, "OTHER"),
            "confederation_away": _CONFEDERATION_HINTS.get(away, "OTHER"),
            "xg_features": xg,
            "lineup_features": lineup,
            "goal_labels": goals,
            "odds_available": odds,
            "pressure_available": bool(xg.get("pressure_index_home") or xg.get("pressure_index_away")),
            "rebuilt_at": datetime.now(timezone.utc).isoformat(),
        }
        dq = float(base.get("data_quality_score") or 0.0)
        if xg.get("xg_available"):
            dq = min(1.0, dq + 0.15)
            with_xg += 1
        if lineup.get("lineup_available"):
            dq = min(1.0, dq + 0.12)
            with_lineup += 1
        if goals.get("goal_event_count", 0) > 0:
            dq = min(1.0, dq + 0.1)
            with_goals += 1
        if odds:
            dq = min(1.0, dq + 0.05)
        enriched["data_quality_score"] = round(dq, 4)

        (out_dir / f"{fid}.json").write_text(json.dumps(enriched, indent=2, default=str), encoding="utf-8")
        rebuilt += 1

    return {
        "status": "ok",
        "rebuilt": rebuilt,
        "with_xg": with_xg,
        "with_lineup": with_lineup,
        "with_goal_events": with_goals,
        "output_dir": str(out_dir),
    }
