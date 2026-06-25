#!/usr/bin/env python3
"""Phase 54F-4 — coverage audit after targeted xG backfill."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f4_xg_parser_and_backfill"
UEFA_CACHE = ROOT / "data" / "egie" / "uefa_club" / "raw"
LEAGUE_NAMES = {2: "champions_league", 5: "europa_league", 2286: "conference_league", 732: "world_cup"}


def _uefa_fixture_ids() -> list[int]:
    ids: list[int] = []
    if not UEFA_CACHE.is_dir():
        return ids
    for path in UEFA_CACHE.glob("*.json"):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data = (blob.get("payload") or {}).get("data")
        if isinstance(data, dict):
            sm_id = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
            if sm_id > 0:
                ids.append(sm_id)
    return ids


def _prior_coverage() -> dict:
    out = {}
    for phase, path in (
        ("54F", ROOT / "artifacts" / "phase54f_egie_xg_backtest" / "dataset_coverage.json"),
        ("54F-2", ROOT / "artifacts" / "phase54f2_xg_coverage_repair" / "coverage_audit.json"),
    ):
        if path.is_file():
            blob = json.loads(path.read_text(encoding="utf-8"))
            cov = blob.get("coverage") or blob.get("db_coverage") or {}
            out[phase] = {
                "rolling_xg_available": cov.get("fixtures_with_xg") or cov.get("rolling_xg_available"),
                "usable_rolling_xg_coverage_pct": cov.get("xg_coverage_pct") or cov.get("usable_rolling_xg_coverage_pct"),
            }
    return out


def main() -> int:
    from sqlalchemy import text

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.postgres.session import session_scope
    from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XgFeatureBuilder

    settings = get_settings()
    builder = XgFeatureBuilder(settings)
    chronological = builder.build_chronological_features()
    uefa_ids = _uefa_fixture_ids()
    uefa_fixtures = len(uefa_ids) if uefa_ids else (len(list(UEFA_CACHE.glob("*.json"))) if UEFA_CACHE.is_dir() else 80)
    uefa_feats = {fid: chronological.get(fid, {}) for fid in uefa_ids}
    xg_available = sum(1 for f in uefa_feats.values() if f.get("xg_available"))
    rolling_3 = sum(1 for f in uefa_feats.values() if f.get("rolling_xg_3_home") is not None)
    rolling_5 = sum(1 for f in uefa_feats.values() if f.get("rolling_xg_5_home") is not None)
    rolling_10 = sum(1 for f in uefa_feats.values() if f.get("rolling_xg_10_home") is not None)
    usable_pct = round(100.0 * xg_available / uefa_fixtures, 2) if uefa_fixtures else 0.0
    global_xg_available = sum(1 for f in chronological.values() if f.get("xg_available"))

    by_league: dict[str, dict] = {}
    with session_scope(settings) as session:
        league_rows = session.execute(
            text(
                """
                SELECT league_id, season_id,
                       COUNT(*) AS summaries,
                       COUNT(*) FILTER (WHERE home_xg IS NOT NULL OR away_xg IS NOT NULL) AS team_xg
                FROM fs_sportmonks_xg_fixture_summary
                GROUP BY league_id, season_id
                ORDER BY league_id, season_id
                """
            )
        ).mappings().all()

        metrics = session.execute(
            text(
                """
                SELECT league_id, metric_key, record_type, COUNT(*) AS n
                FROM fs_sportmonks_xg_records
                GROUP BY league_id, metric_key, record_type
                """
            )
        ).mappings().all()

        manifest = session.execute(
            text(
                """
                SELECT status, COUNT(*) AS n
                FROM fs_sportmonks_xg_ingest_manifest
                WHERE job_key LIKE 'phase54f4%'
                GROUP BY status
                """
            )
        ).mappings().all()

        player_xg = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT sportmonks_fixture_id) AS n
                FROM fs_sportmonks_xg_records
                WHERE record_type = 'player_xg' AND metric_key = 'xg'
                """
            )
        ).scalar() or 0

        xgot_only = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT sportmonks_fixture_id) AS n
                FROM fs_sportmonks_xg_records r
                WHERE metric_key = 'xgot'
                  AND NOT EXISTS (
                    SELECT 1 FROM fs_sportmonks_xg_records x
                    WHERE x.sportmonks_fixture_id = r.sportmonks_fixture_id
                      AND x.metric_key = 'xg'
                      AND x.record_type IN ('team_metric', 'team_xg')
                  )
                """
            )
        ).scalar() or 0

        total_records = session.execute(text("SELECT COUNT(*) FROM fs_sportmonks_xg_records")).scalar() or 0
        total_summaries = session.execute(text("SELECT COUNT(*) FROM fs_sportmonks_xg_fixture_summary")).scalar() or 0

    for row in league_rows:
        lid = int(row["league_id"] or 0)
        name = LEAGUE_NAMES.get(lid, f"league_{lid}")
        by_league.setdefault(name, {"league_id": lid, "seasons": []})
        by_league[name]["seasons"].append(
            {
                "season_id": row["season_id"],
                "summaries": int(row["summaries"] or 0),
                "fixtures_with_team_xg": int(row["team_xg"] or 0),
            }
        )

    metric_summary: dict[str, int] = {}
    for row in metrics:
        key = f"{row['record_type']}:{row['metric_key']}"
        metric_summary[key] = metric_summary.get(key, 0) + int(row["n"] or 0)

    report = {
        "phase": "54F-4",
        "prior_coverage": _prior_coverage(),
        "summary": {
            "uefa_cache_fixtures": uefa_fixtures,
            "total_records": int(total_records),
            "total_summaries": int(total_summaries),
            "global_rolling_xg_available": global_xg_available,
            "uefa_rolling_xg_available": xg_available,
            "rolling_xg_available": xg_available,
            "rolling_xg_3_fixtures": rolling_3,
            "rolling_xg_5_fixtures": rolling_5,
            "rolling_xg_10_fixtures": rolling_10,
            "usable_rolling_xg_coverage_pct": usable_pct,
            "fixtures_with_player_xg": int(player_xg),
            "fixtures_xgot_only": int(xgot_only),
        },
        "by_league": by_league,
        "metric_summary": metric_summary,
        "manifest_skipped": {str(r["status"]): int(r["n"]) for r in manifest},
        "threshold_met": usable_pct >= 30.0,
        "threshold_target_pct": 30.0,
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "coverage_audit.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["threshold_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
