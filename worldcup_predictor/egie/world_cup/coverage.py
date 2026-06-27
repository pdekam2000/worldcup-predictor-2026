"""Coverage metrics for World Cup EGIE dataset — Phase 62."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.postgres.session import postgres_configured, session_scope
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.world_cup.config import (
    RAW_CACHE_DIR,
    TARGET_FIXTURES,
    TARGET_GOAL_EVENT_COVERAGE,
    TARGET_LINEUP_COVERAGE,
    TARGET_ODDS_COVERAGE,
    TARGET_XG_COVERAGE,
    WORLD_CUP_COMPETITION_KEY,
)
from sqlalchemy import text


def _fixture_ids(repo: FootballIntelligenceRepository, *, limit: int = 600) -> list[dict[str, Any]]:
    rows = repo._conn.execute(
        """
        SELECT f.fixture_id, f.home_team, f.away_team, f.season, f.status,
               fr.home_goals, fr.away_goals
        FROM fixtures f
        LEFT JOIN fixture_results fr ON fr.fixture_id = f.fixture_id
        WHERE f.competition_key = ?
        ORDER BY f.kickoff_utc DESC
        LIMIT ?
        """,
        (WORLD_CUP_COMPETITION_KEY, int(limit)),
    ).fetchall()
    return [
        {
            "fixture_id": int(r[0]),
            "home_team": r[1],
            "away_team": r[2],
            "season": r[3],
            "status": r[4],
            "home_goals": r[5],
            "away_goals": r[6],
        }
        for r in rows
    ]


def _raw_cache_file(provider: str, resource: str, fixture_id: int) -> Path:
    return Path.cwd() / RAW_CACHE_DIR / provider / resource / f"{fixture_id}.json"


def _has_lineup(repo: FootballIntelligenceRepository, fixture_id: int) -> bool:
    if _raw_cache_file("api-football", "lineups", fixture_id).is_file():
        return True
    enriched = Path.cwd() / RAW_CACHE_DIR / "goal_timing_features_enriched" / f"{fixture_id}.json"
    if enriched.is_file():
        try:
            blob = json.loads(enriched.read_text(encoding="utf-8"))
            if (blob.get("lineup_features") or {}).get("lineup_available"):
                return True
        except (json.JSONDecodeError, OSError):
            pass
    row = repo._conn.execute(
        "SELECT lineups_json FROM fixture_enrichment WHERE fixture_id = ? LIMIT 1",
        (fixture_id,),
    ).fetchone()
    return bool(row and row[0] and row[0] not in ("", "[]", "null"))


def _has_pressure(repo: FootballIntelligenceRepository, fixture_id: int) -> bool:
    if _raw_cache_file("sportmonks", "fixture_enrichment", fixture_id).is_file():
        return True
    row = repo._conn.execute(
        """
        SELECT premium_xg_available, raw_json
        FROM sportmonks_fixture_enrichment
        WHERE fixture_id_api_football = ? AND status = 'ok'
        ORDER BY id DESC LIMIT 1
        """,
        (fixture_id,),
    ).fetchone()
    return bool(row and (row[0] or row[1]))


def measure_coverage(settings: Settings | None = None, *, sample_limit: int = 600) -> dict[str, Any]:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    fixtures = _fixture_ids(repo, limit=sample_limit)
    total = len(fixtures)
    if total == 0:
        return {"total_fixtures": 0, "status": "empty"}

    finished = [f for f in fixtures if f.get("home_goals") is not None]

    odds_n = xg_n = lineup_n = pressure_n = goal_events_n = 0
    for fx in fixtures:
        fid = int(fx["fixture_id"])
        if repo.has_odds_snapshot(fid):
            odds_n += 1
        if repo.has_xg_snapshot(fid):
            xg_n += 1
        else:
            enriched = Path.cwd() / RAW_CACHE_DIR / "goal_timing_features_enriched" / f"{fid}.json"
            if enriched.is_file():
                try:
                    blob = json.loads(enriched.read_text(encoding="utf-8"))
                    if (blob.get("xg_features") or {}).get("xg_available"):
                        xg_n += 1
                except (json.JSONDecodeError, OSError):
                    pass
        if _has_lineup(repo, fid):
            lineup_n += 1
        if _has_pressure(repo, fid):
            pressure_n += 1
        if repo.count_fixture_goal_events(fid) > 0:
            goal_events_n += 1

    pg: dict[str, Any] = {}
    if postgres_configured(settings):
        try:
            with session_scope(settings) as sess:
                pg["goal_timing_features_wc"] = int(
                    sess.execute(
                        text("SELECT COUNT(1) FROM goal_timing_features WHERE competition_key = :ck"),
                        {"ck": WORLD_CUP_COMPETITION_KEY},
                    ).scalar()
                    or 0
                )
                pg["goal_timing_predictions_wc"] = int(
                    sess.execute(
                        text("SELECT COUNT(1) FROM goal_timing_predictions WHERE competition_key = :ck"),
                        {"ck": WORLD_CUP_COMPETITION_KEY},
                    ).scalar()
                    or 0
                )
                pg["egie_raw_wc"] = int(
                    sess.execute(
                        text("SELECT COUNT(1) FROM egie_provider_raw_responses WHERE competition_key = :ck"),
                        {"ck": WORLD_CUP_COMPETITION_KEY},
                    ).scalar()
                    or 0
                )
        except Exception as exc:
            pg["error"] = str(exc)[:200]

    def pct(n: int) -> float:
        return round(n / total, 4) if total else 0.0

    def pct_finished(n: int) -> float:
        return round(n / len(finished), 4) if finished else 0.0

    usable_egie = sum(1 for fx in finished if repo.count_fixture_goal_events(int(fx["fixture_id"])) > 0)

    metrics = {
        "total_fixtures": total,
        "finished_fixtures": len(finished),
        "odds_coverage": pct(odds_n),
        "xg_coverage": pct(xg_n),
        "lineup_coverage": pct(lineup_n),
        "pressure_coverage": pct(pressure_n),
        "goal_event_coverage": pct_finished(goal_events_n),
        "goal_event_count": goal_events_n,
        "usable_egie_fixtures": usable_egie,
        "usable_egie_coverage": pct_finished(usable_egie),
        "postgresql": pg,
        "targets": {
            "fixtures": TARGET_FIXTURES,
            "xg": TARGET_XG_COVERAGE,
            "lineups": TARGET_LINEUP_COVERAGE,
            "odds": TARGET_ODDS_COVERAGE,
            "goal_events": TARGET_GOAL_EVENT_COVERAGE,
        },
    }
    metrics["meets_fixture_target"] = total >= TARGET_FIXTURES
    metrics["meets_xg_target"] = metrics["xg_coverage"] >= TARGET_XG_COVERAGE
    metrics["meets_lineup_target"] = metrics["lineup_coverage"] >= TARGET_LINEUP_COVERAGE
    metrics["meets_odds_target"] = metrics["odds_coverage"] >= TARGET_ODDS_COVERAGE
    metrics["meets_goal_event_target"] = metrics["goal_event_coverage"] >= TARGET_GOAL_EVENT_COVERAGE
    metrics["all_targets_met"] = all(
        metrics[k]
        for k in (
            "meets_fixture_target",
            "meets_xg_target",
            "meets_lineup_target",
            "meets_odds_target",
            "meets_goal_event_target",
        )
    )
    return metrics


def recommend_phase(metrics: dict[str, Any]) -> str:
    if metrics.get("total_fixtures", 0) == 0:
        return "BLOCKED"
    if metrics.get("all_targets_met"):
        return "READY_FOR_PHASE_61B_RERUN"
    if metrics.get("total_fixtures", 0) < 100:
        return "PROVIDER_LIMITED"
    return "NEED_MORE_IMPORTS"
