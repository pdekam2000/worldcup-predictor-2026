#!/usr/bin/env python3
"""PHASE ECSE-X2-M6 — Shadow-live smoke backfill from ECSE snapshots + training fixtures."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["ECSE_X2_M6_SHADOW_LIVE_ENABLED"] = "1"

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables
from worldcup_predictor.research.ecse_x2_m2.prob_features import load_baseline_top_scores, load_fixture_records
from worldcup_predictor.research.ecse_x2_m4.segment import classify_match_state
from worldcup_predictor.research.ecse_x2_m6.evaluator import (
    backfill_evaluations_from_snapshots,
    evaluate_fixture_shadow,
)
from worldcup_predictor.research.ecse_x2_m6.hook import attach_shadow_live_shortlist
from worldcup_predictor.research.ecse_x2_m6.lift_model import get_lift_model
from worldcup_predictor.research.ecse_x2_m6.runtime import compute_shadow_live_shortlist
from worldcup_predictor.research.ecse_x2_m6.store import read_shadow_shortlists

TOP_N = 10


def _prediction_from_snapshot(snap: dict) -> dict:
    top_10 = snap.get("top_10_scorelines") or []
    return {
        "fixture_id": snap["fixture_id"],
        "kickoff_utc": snap.get("kickoff_utc"),
        "competition_key": snap.get("competition_key"),
        "home_team": snap.get("home_team"),
        "away_team": snap.get("away_team"),
        "top_10_scorelines": top_10,
        "top_1_score": snap.get("top_1_score"),
        "raw_features": snap.get("raw_features") or {},
    }


def _prediction_from_training(rec: dict, dist_map: dict) -> dict | None:
    fid = int(rec["registry_fixture_id"])
    if fid not in dist_map:
        return None
    top_10 = [
        {
            "scoreline": r["scoreline"],
            "probability": r["probability"],
            "rank": r["rank"],
            "home_goals": r.get("home_goals"),
            "away_goals": r.get("away_goals"),
        }
        for r in dist_map[fid][:TOP_N]
    ]
    odds = {f"{k}_closing": rec.get(f"{k}_closing") for k in (
        "ft_home", "ft_away", "ft_draw", "ou_over_25", "ou_under_25", "btts_yes", "btts_no"
    )}
    return {
        "fixture_id": fid,
        "kickoff_utc": rec.get("kickoff_utc"),
        "competition_key": rec.get("league"),
        "top_10_scorelines": top_10,
        "top_1_score": top_10[0]["scoreline"] if top_10 else None,
        "raw_features": {"odds_row": odds, "coverage": {"feature_coverage_count": rec.get("feature_coverage_count")}},
    }


def run_smoke(*, upcoming_target: int = 20, completed_target: int = 20) -> dict:
    get_settings.cache_clear()
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_live_tables(conn)
    get_lift_model(conn)

    stats = {
        "upcoming_attempted": 0,
        "upcoming_attached": 0,
        "completed_attempted": 0,
        "completed_attached": 0,
        "evaluated": 0,
        "strong_segment": 0,
        "balanced_control": 0,
        "applied": 0,
        "samples": [],
    }

    snapshots = conn.execute(
        """
        SELECT * FROM ecse_prediction_snapshots
        ORDER BY kickoff_utc DESC
        LIMIT ?
        """,
        (max(upcoming_target, completed_target) * 2,),
    ).fetchall()

    for snap_row in snapshots:
        snap = dict(snap_row)
        for key in ("top_10_scorelines_json", "raw_features_json"):
            if isinstance(snap.get(key), str):
                try:
                    snap[key.replace("_json", "")] = json.loads(snap[key])
                except json.JSONDecodeError:
                    pass
        pred = _prediction_from_snapshot(snap)
        fid = int(snap["fixture_id"])
        stats["upcoming_attempted"] += 1
        out = attach_shadow_live_shortlist(conn, fixture_id=fid, prediction=pred, snapshot_id=snap.get("id"))
        if out and out.get("storage_appended"):
            stats["upcoming_attached"] += 1
            if out.get("applied"):
                stats["applied"] += 1
            if out.get("strong_segment"):
                stats["strong_segment"] += 1
        if stats["upcoming_attached"] >= upcoming_target:
            break

    dist_map = load_baseline_top_scores(conn, top_n=TOP_N)
    records = load_fixture_records(conn)
    records = sorted(records, key=lambda r: r.get("kickoff_unix") or 0, reverse=True)

    strong_n = 0
    balanced_n = 0
    for rec in records:
        if stats["completed_attached"] >= completed_target:
            break
        pred = _prediction_from_training(rec, dist_map)
        if not pred:
            continue
        state = classify_match_state(rec["probs"])
        if state == "balanced" and balanced_n < 3:
            balanced_n += 1
        h = rec["probs"].get("ft_home")
        if h is not None and h >= 0.60:
            strong_n += 1
        fid = int(rec["registry_fixture_id"])
        stats["completed_attempted"] += 1
        out = attach_shadow_live_shortlist(conn, fixture_id=fid, prediction=pred, snapshot_id=None)
        if out and out.get("storage_appended"):
            stats["completed_attached"] += 1
            if out.get("applied"):
                stats["applied"] += 1
            if out.get("strong_segment"):
                stats["strong_segment"] += 1
            if state == "balanced":
                stats["balanced_control"] += 1
            actual = rec.get("actual")
            if actual and out.get("applied"):
                ev = evaluate_fixture_shadow(fid, actual_score=str(actual))
                if ev:
                    stats["evaluated"] += 1
            if len(stats["samples"]) < 5 and out.get("applied"):
                stats["samples"].append(
                    {
                        "fixture_id": fid,
                        "actual": actual,
                        "baseline_top1": (out.get("baseline_top10") or [{}])[0].get("scoreline"),
                        "enhanced_top1": (out.get("enhanced_top10") or [{}])[0].get("scoreline"),
                        "home_prob": out.get("home_prob"),
                    }
                )

    backfill = backfill_evaluations_from_snapshots(conn, limit=200)
    stats["backfill"] = backfill
    all_rows = read_shadow_shortlists(limit=100_000)
    stats["shadow_rows"] = len(all_rows)
    if stats["balanced_control"] < 1:
        stats["balanced_control"] = sum(
            1 for r in all_rows if r.get("exclusion_reason") == "balanced_match"
        )
    conn.close()
    return stats


def main() -> int:
    stats = run_smoke()
    print(json.dumps(stats, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
