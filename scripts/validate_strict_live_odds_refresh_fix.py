#!/usr/bin/env python3
"""Validate strict live odds refresh wiring without provider calls."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.ecse_live.store import (  # noqa: E402
    ensure_ecse_live_tables,
    insert_evaluation,
    insert_snapshot,
)


def check(name: str, ok: bool, details: str = "") -> dict[str, object]:
    return {"name": name, "passed": bool(ok), "details": details}


def sample_payload(*, top1: str, source: str, generated_at: str) -> dict[str, object]:
    return {
        "fixture_id": 999001,
        "registry_fixture_id": None,
        "competition_key": "europa_league",
        "home_team": "Home",
        "away_team": "Away",
        "kickoff_utc": "2026-07-09T18:00:00+00:00",
        "generated_at": generated_at,
        "model_version": "validator-model",
        "lambda_home": 1.7,
        "lambda_away": 0.8,
        "top_10_scorelines": [
            {"score": top1, "probability": 0.2},
            {"score": "1-0", "probability": 0.15},
        ],
        "top_1_score": top1,
        "top_3_scores": [top1, "1-0", "2-0"],
        "top_5_scores": [top1, "1-0", "2-0", "1-1", "0-0"],
        "confidence_score": 0.6,
        "data_quality_score": 0.9,
        "raw_features": {"validator": True},
        "prediction_source": source,
    }


def main() -> int:
    checks: list[dict[str, object]] = []

    strict_src = (ROOT / "worldcup_predictor/odds/strict_live_refresh.py").read_text(encoding="utf-8")
    refresh_src = (ROOT / "worldcup_predictor/odds/freshness_refresh.py").read_text(encoding="utf-8")
    cycle_src = (ROOT / "worldcup_predictor/owner_daily/cycle.py").read_text(encoding="utf-8")
    pred_src = (ROOT / "worldcup_predictor/owner_daily/predictions.py").read_text(encoding="utf-8")

    checks.append(check("api_force_refresh", "get_odds(fid, force_refresh=True)" in strict_src))
    checks.append(check("require_live_source", 'odds_result.source != "live"' in strict_src))
    checks.append(check("no_cached_restamp", "cache_bypassed" in strict_src))
    checks.append(check("stale_ids_targeted", "refresh_fixture_odds_live" in refresh_src))
    checks.append(
        check(
            "strict_path_isolated",
            "and not config.refresh_stale_odds" in cycle_src,
        )
    )
    checks.append(
        check(
            "successful_refresh_forces_regeneration",
            "config.force_predictions or refreshed_for_prediction" in cycle_src,
        )
    )
    checks.append(
        check(
            "ecse_strict_freshness",
            pred_src.count("strict_fresh_odds and freshness.get") >= 2,
        )
    )
    checks.append(
        check(
            "ecse_receives_strict_flag",
            "strict_fresh_odds=strict_fresh_odds" in pred_src,
        )
    )

    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        ensure_ecse_live_tables(conn)

        first = sample_payload(
            top1="2-0",
            source="live_odds",
            generated_at="2026-07-09 03:00:00 UTC",
        )
        sid1, reason1 = insert_snapshot(conn, first)
        checks.append(check("initial_ecse_insert", sid1 is not None and reason1 == "inserted", reason1))

        refreshed = sample_payload(
            top1="3-0",
            source="owner_daily_predictions",
            generated_at="2026-07-09 05:00:00 UTC",
        )
        sid2, reason2 = insert_snapshot(conn, refreshed)
        row = conn.execute(
            "SELECT id, top_1_score FROM ecse_prediction_snapshots WHERE fixture_id=999001"
        ).fetchone()
        checks.append(
            check(
                "unevaluated_ecse_refresh",
                reason2 == "refreshed" and sid2 == sid1 and row and row["top_1_score"] == "3-0",
                reason2,
            )
        )
        audit_count = conn.execute(
            "SELECT COUNT(*) FROM ecse_live_api_log WHERE action='archive_before_refresh'"
        ).fetchone()[0]
        checks.append(check("ecse_refresh_audited", audit_count == 1, str(audit_count)))

        eid, ereason = insert_evaluation(
            conn,
            {
                "snapshot_id": sid1,
                "fixture_id": 999001,
                "final_score": "3-0",
                "top1_correct": True,
                "top3_correct": True,
                "top5_correct": True,
                "top10_correct": True,
                "rank_of_actual_score": 1,
                "actual_home_goals": 3,
                "actual_away_goals": 0,
            },
        )
        checks.append(check("evaluation_insert", eid is not None and ereason == "inserted", ereason))

        locked = sample_payload(
            top1="1-0",
            source="owner_daily_predictions",
            generated_at="2026-07-09 06:00:00 UTC",
        )
        sid3, reason3 = insert_snapshot(conn, locked)
        locked_row = conn.execute(
            "SELECT top_1_score FROM ecse_prediction_snapshots WHERE fixture_id=999001"
        ).fetchone()
        checks.append(
            check(
                "evaluated_snapshot_locked",
                sid3 is None and reason3 == "evaluated_snapshot_locked" and locked_row["top_1_score"] == "3-0",
                reason3,
            )
        )
        conn.close()

    all_passed = all(bool(item["passed"]) for item in checks)
    output = {
        "phase": "STRICT-LIVE-ODDS-REFRESH-FIX",
        "all_passed": all_passed,
        "checks": checks,
    }
    print(json.dumps(output, indent=2))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
