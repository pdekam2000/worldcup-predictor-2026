#!/usr/bin/env python3
"""Phase 54F-2 — xG coverage audit after metric-key repair."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f2_xg_coverage_repair"
UEFA_CACHE = ROOT / "data" / "egie" / "uefa_club" / "raw"
LEAGUE_NAMES = {2: "champions_league", 5: "europa_league", 2286: "conference_league", 732: "world_cup"}


def _usable_rolling_pct(xg_available: int, total: int) -> float:
    return round(100.0 * xg_available / total, 2) if total else 0.0


def audit_db_coverage() -> dict[str, Any]:
    from sqlalchemy import text

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.postgres.session import session_scope
    from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XgFeatureBuilder

    settings = get_settings()
    builder = XgFeatureBuilder(settings)
    chronological = builder.build_chronological_features()
    uefa_fixtures = len(list(UEFA_CACHE.glob("*.json"))) if UEFA_CACHE.is_dir() else 0

    xg_available = sum(1 for f in chronological.values() if f.get("xg_available"))
    summaries_with_home_xg = 0
    by_league: dict[str, Any] = {}

    with session_scope(settings) as session:
        league_rows = session.execute(
            text(
                """
                SELECT league_id,
                       COUNT(*) AS summaries,
                       COUNT(*) FILTER (WHERE home_xg IS NOT NULL OR away_xg IS NOT NULL) AS with_team_xg
                FROM fs_sportmonks_xg_fixture_summary
                GROUP BY league_id
                """
            )
        ).mappings().all()

        metric_rows = session.execute(
            text(
                """
                SELECT league_id, metric_key, record_type, COUNT(*) AS n
                FROM fs_sportmonks_xg_records
                GROUP BY league_id, metric_key, record_type
                """
            )
        ).mappings().all()

        manifest_skips = session.execute(
            text(
                """
                SELECT status, COUNT(*) AS n
                FROM fs_sportmonks_xg_ingest_manifest
                WHERE status LIKE '%xgot_only%' OR status LIKE '%no_true_xg%'
                GROUP BY status
                """
            )
        ).mappings().all()

        player_xg = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT sportmonks_fixture_id) AS fixtures
                FROM fs_sportmonks_xg_records
                WHERE record_type = 'player_xg' AND metric_key = 'xg'
                """
            )
        ).mappings().first()

        xgot_only = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT r.sportmonks_fixture_id) AS fixtures
                FROM fs_sportmonks_xg_records r
                WHERE r.metric_key = 'xgot'
                  AND NOT EXISTS (
                    SELECT 1 FROM fs_sportmonks_xg_records x
                    WHERE x.sportmonks_fixture_id = r.sportmonks_fixture_id
                      AND x.metric_key = 'xg'
                      AND x.record_type IN ('team_metric', 'team_xg')
                  )
                """
            )
        ).mappings().first()

        summaries_with_home_xg = session.execute(
            text(
                "SELECT COUNT(*) FROM fs_sportmonks_xg_fixture_summary WHERE home_xg IS NOT NULL"
            )
        ).scalar() or 0

    rolling_3 = sum(1 for f in chronological.values() if f.get("rolling_xg_3_home") is not None)
    rolling_5 = sum(1 for f in chronological.values() if f.get("rolling_xg_5_home") is not None)
    rolling_10 = sum(1 for f in chronological.values() if f.get("rolling_xg_10_home") is not None)

    for row in league_rows:
        lid = int(row["league_id"] or 0)
        name = LEAGUE_NAMES.get(lid, f"league_{lid}")
        by_league[name] = {
            "league_id": lid,
            "summaries": int(row["summaries"] or 0),
            "with_team_xg": int(row["with_team_xg"] or 0),
            "metrics": {},
        }

    for row in metric_rows:
        lid = int(row["league_id"] or 0)
        name = LEAGUE_NAMES.get(lid, f"league_{lid}")
        by_league.setdefault(name, {"league_id": lid, "summaries": 0, "with_team_xg": 0, "metrics": {}})
        key = f"{row['record_type']}:{row['metric_key']}"
        by_league[name]["metrics"][key] = int(row["n"] or 0)

    usable_pct = _usable_rolling_pct(xg_available, uefa_fixtures)

    return {
        "uefa_cache_fixtures": uefa_fixtures,
        "summaries_with_team_xg": int(summaries_with_home_xg),
        "fixtures_with_player_xg": int((player_xg or {}).get("fixtures") or 0),
        "fixtures_xgot_only_no_team_xg": int((xgot_only or {}).get("fixtures") or 0),
        "rolling_xg_available": xg_available,
        "rolling_xg_3_fixtures": rolling_3,
        "rolling_xg_5_fixtures": rolling_5,
        "rolling_xg_10_fixtures": rolling_10,
        "usable_rolling_xg_coverage_pct": usable_pct,
        "coverage_pass_30pct": usable_pct >= 30.0,
        "coverage_pass_40pct": usable_pct >= 40.0,
        "by_league": by_league,
        "skipped_by_manifest": {str(r["status"]): int(r["n"]) for r in manifest_skips},
    }


def audit_cache_semantics() -> dict[str, Any]:
    import json
    from collections import Counter

    from worldcup_predictor.feature_store.normalizers import normalize_fixture_xg_records

    stats: Counter[str] = Counter()
    per_league: dict[int, dict[str, int]] = {}

    if not UEFA_CACHE.is_dir():
        return {"cache_present": False}

    for path in UEFA_CACHE.glob("*.json"):
        stats["fixtures_scanned"] += 1
        blob = json.loads(path.read_text(encoding="utf-8"))
        data = (blob.get("payload") or {}).get("data") or {}
        lid = int(data.get("league_id") or 0)
        per_league.setdefault(lid, {"scanned": 0, "team_xg": 0, "xgot_only": 0, "no_xg": 0})
        per_league[lid]["scanned"] += 1
        recs = normalize_fixture_xg_records(data, sportmonks_fixture_id=int(path.stem))
        has_xg = any(r.metric_key == "xg" and r.record_type in ("team_metric", "team_xg") for r in recs)
        has_xgot = any(r.metric_key == "xgot" for r in recs)
        if has_xg:
            stats["fixtures_with_team_xg"] += 1
            per_league[lid]["team_xg"] += 1
        elif has_xgot:
            stats["fixtures_xgot_only"] += 1
            per_league[lid]["xgot_only"] += 1
        else:
            stats["fixtures_no_xg_data"] += 1
            per_league[lid]["no_xg"] += 1
        if recs:
            stats["fixtures_with_any_xg_rows"] += 1

    return {
        "cache_present": True,
        "totals": dict(stats),
        "by_league_id": per_league,
    }


def main() -> int:
    db = audit_db_coverage()
    cache = audit_cache_semantics()

    # Load prior 54F baseline if present
    prior_path = ROOT / "artifacts" / "phase54f_egie_xg_backtest" / "dataset_coverage.json"
    prior = {}
    if prior_path.is_file():
        prior = json.loads(prior_path.read_text(encoding="utf-8")).get("coverage", {})

    report = {
        "phase": "54F-2",
        "prior_54f": {
            "fixtures_with_xg": prior.get("fixtures_with_xg"),
            "xg_coverage_pct": prior.get("xg_coverage_pct"),
        },
        "cache_audit": cache,
        "db_coverage": db,
        "threshold_met": db.get("coverage_pass_30pct", False),
        "recommendation": (
            "RERUN_54F_BACKTEST" if db.get("coverage_pass_30pct") else "NEED_MORE_HISTORICAL_XG"
        ),
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if db.get("coverage_pass_30pct") else 1


if __name__ == "__main__":
    raise SystemExit(main())
