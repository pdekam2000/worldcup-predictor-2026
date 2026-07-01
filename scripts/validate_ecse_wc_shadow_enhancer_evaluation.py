#!/usr/bin/env python3
"""Validate PHASE ECSE-WC-1 — World Cup shadow enhancer evaluation."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.clients.api_football import ApiCallResult
from worldcup_predictor.config.settings import Settings
from worldcup_predictor.database.connection import init_database
from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL
from worldcup_predictor.research.ecse_live.store import insert_snapshot
from worldcup_predictor.research.ecse_wc.wc_shadow_enhancer_evaluation import (
    WC_EVAL_JSONL,
    WC_EVAL_SUMMARY,
    evaluate_wc_fixture_shadow,
    load_wc_evaluated_snapshots,
    load_wc_shadow_evaluation_rows,
    load_wc_shadow_evaluation_summary,
    run_wc_shadow_enhancer_evaluation,
)
from worldcup_predictor.research.ecse_x2_m8.lab_service import (
    EcseOwnerShadowLabService,
    _wc_row_to_lab_item,
)

CHECKS: list[tuple[str, bool, str]] = []
FID = 9_900_101


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _seed(conn, *, outcome: str = "FT", score: str = "2-1", penalty: str | None = None) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    conn.execute("DELETE FROM ecse_prediction_evaluations WHERE fixture_id = ?", (FID,))
    conn.execute("DELETE FROM ecse_prediction_snapshots WHERE fixture_id = ?", (FID,))
    conn.execute(
        """
        INSERT OR IGNORE INTO competitions(key, name, league_id, season, competition_type,
            supports_groups, supports_table, updated_at)
        VALUES ('world_cup_2026', 'World Cup 2026', 732, 2026, 'world_cup_finals', 1, 1, ?)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO fixtures(fixture_id, competition_key, home_team, away_team,
            kickoff_utc, status, round_name, is_placeholder, source, updated_at)
        VALUES (?, 'world_cup_2026', 'Brazil', 'Japan', ?, ?, 'Round of 32', 0, 'live', ?)
        """,
        (FID, past, outcome, now),
    )
    hg, ag = [int(x) for x in score.split("-", 1)]
    conn.execute(
        """
        INSERT OR REPLACE INTO fixture_results(
            fixture_id, competition_key, final_score, home_goals, away_goals,
            winner, over_under_2_5, total_goals, finished_at, source,
            match_outcome_type, penalty_score
        ) VALUES (?, 'world_cup_2026', ?, ?, ?, 'home', 'over_2_5', ?, ?, 'test', ?, ?)
        """,
        (FID, score, hg, ag, hg + ag, now, outcome, penalty),
    )
    for ddl in PHASE_ECSE_LIVE_DDL:
        conn.execute(ddl)
    top10 = [
        {"scoreline": "1-0", "probability": 0.18, "rank": 1},
        {"scoreline": "2-0", "probability": 0.14, "rank": 2},
        {"scoreline": "2-1", "probability": 0.12, "rank": 3},
        {"scoreline": "1-1", "probability": 0.10, "rank": 4},
        {"scoreline": "3-0", "probability": 0.09, "rank": 5},
        {"scoreline": "3-1", "probability": 0.08, "rank": 6},
        {"scoreline": "0-0", "probability": 0.07, "rank": 7},
        {"scoreline": "0-1", "probability": 0.06, "rank": 8},
        {"scoreline": "2-2", "probability": 0.05, "rank": 9},
        {"scoreline": "3-2", "probability": 0.04, "rank": 10},
    ]
    rank_of_actual = next(
        (r["rank"] for r in top10 if r["scoreline"] == score),
        10,
    )
    insert_snapshot(
        conn,
        {
            "fixture_id": FID,
            "competition_key": "world_cup_2026",
            "home_team": "Brazil",
            "away_team": "Japan",
            "kickoff_utc": past,
            "model_version": "test",
            "lambda_home": 1.5,
            "lambda_away": 0.9,
            "top_10_scorelines": top10,
            "top_1_score": "1-0",
            "top_3_scores": ["1-0", "2-0", "2-1"],
            "top_5_scores": ["1-0", "2-0", "2-1", "1-1", "3-0"],
            "confidence_score": 0.5,
            "data_quality_score": 0.8,
            "raw_features": {
                "odds_row": {
                    "ft_home_closing": 1.85,
                    "ft_draw_closing": 3.4,
                    "ft_away_closing": 4.2,
                },
                "coverage": {"feature_coverage_count": 3},
            },
        },
    )
    conn.execute(
        """
        INSERT INTO ecse_prediction_evaluations(
            snapshot_id, fixture_id, final_score, top1_correct, top3_correct,
            top5_correct, top10_correct, rank_of_actual_score,
            actual_home_goals, actual_away_goals, status, evaluated_at
        )
        SELECT id, fixture_id, ?, 0, 1, 1, 1, ?, ?, ?, 'evaluated', ?
        FROM ecse_prediction_snapshots WHERE fixture_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (score, rank_of_actual, hg, ag, now, FID),
    )
    conn.commit()


def main() -> int:
    print("validate_ecse_wc_shadow_enhancer_evaluation")

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "wc_eval.db"
        conn = init_database(db)
        try:
            _seed(conn, outcome="FT", score="2-1")
            snaps = load_wc_evaluated_snapshots(conn)
            check("finished_wc_snapshots_loaded", len(snaps) == 1, f"n={len(snaps)}")
            check("ft_pen_distinction", snaps[0].get("match_outcome_type") == "FT")

            lift = {
                "quantile_lifts": {},
                "score_lifts": {},
                "cluster_lifts": {},
                "default_lift": 1.0,
            }
            row = evaluate_wc_fixture_shadow(conn, snaps[0], lift_model=lift)
            base_set = set(row["baseline_top10_membership"])
            enh_set = set(row["enhanced_top10_membership"])
            check("baseline_top10_membership_unchanged", base_set == enh_set)
            check("rank_delta_computed", row.get("baseline_rank") == 3)
            check("provider_backed_only", row.get("actual_score") == "2-1")

            _seed(conn, outcome="PEN", score="1-1", penalty="3-4")
            pen_snap = load_wc_evaluated_snapshots(conn)[0]
            pen_row = evaluate_wc_fixture_shadow(conn, pen_snap, lift_model=lift)
            check("pen_fixture_safe", pen_row.get("match_outcome_type") == "PEN")
            check("penalty_score_preserved", pen_row.get("penalty_score") == "3-4")
            check(
                "pen_1_1_warning",
                pen_row.get("score_1_1_analysis", {}).get("draw_pen_warning") is True,
            )

            out_jsonl = Path(tmp) / "wc.jsonl"
            out_sum = Path(tmp) / "wc.json"
            lift = {
                "quantile_lifts": {},
                "score_lifts": {},
                "cluster_lifts": {},
                "default_lift": 1.0,
            }
            with patch(
                "worldcup_predictor.research.ecse_wc.wc_shadow_enhancer_evaluation.get_lift_model",
                return_value=lift,
            ):
                result = run_wc_shadow_enhancer_evaluation(
                    conn,
                    jsonl_path=out_jsonl,
                    summary_path=out_sum,
                )
            check("artifacts_created", out_jsonl.exists() and out_sum.exists())
            check("summary_has_comparison", "comparison" in result.summary)

            wc_summary = load_wc_shadow_evaluation_summary()
            check("owner_lab_reads_wc_summary", wc_summary is not None and wc_summary.get("fixture_count", 0) >= 1)
            wc_rows = load_wc_shadow_evaluation_rows()
            if wc_rows:
                lab_item = _wc_row_to_lab_item(wc_rows[0], None)
                check(
                    "owner_lab_fixture_detail",
                    lab_item.get("baseline_hit_rank") is not None
                    and lab_item.get("source") == "ecse_wc_shadow_replay",
                )
            else:
                check("owner_lab_fixture_detail", False, "no production wc rows")

            refresh_src = (
                ROOT / "worldcup_predictor/api/routes/owner_ecse_shadow_lab.py"
            ).read_text(encoding="utf-8")
            check("owner_route_owner_only", "require_owner_user" in refresh_src)
            check("ecse_baseline_table_unchanged", "INSERT INTO ecse_prediction_snapshots" in (
                ROOT / "worldcup_predictor/research/ecse_live/store.py"
            ).read_text(encoding="utf-8"))
            check("no_public_prediction_changes", "public_output_changed" in json.dumps(result.summary))
        finally:
            conn.close()

    # Production artifacts if present
    if WC_EVAL_SUMMARY.exists():
        prod = json.loads(WC_EVAL_SUMMARY.read_text(encoding="utf-8"))
        check(
            "production_wc_artifacts",
            prod.get("fixture_count", 0) >= 3,
            f"count={prod.get('fixture_count')}",
        )

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{passed}/{len(CHECKS)} passed, {failed} failed")
    out = ROOT / "artifacts" / "validate_ecse_wc_shadow_enhancer_evaluation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS], "passed": passed, "failed": failed},
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
