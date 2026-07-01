#!/usr/bin/env python3
"""Validate PHASE ECSE-WC-2 — knockout draw/PEN risk signal."""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path, init_database
from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL
from worldcup_predictor.research.ecse_live.store import insert_snapshot
from worldcup_predictor.research.ecse_wc.knockout_draw_pen_risk import (
    RISK_JSONL,
    RISK_SUMMARY,
    compute_knockout_draw_pen_risk,
    evaluate_fixture_knockout_risk,
    run_knockout_draw_pen_risk_evaluation,
)
from worldcup_predictor.research.ecse_x2_m8.lab_service import (
    EcseOwnerShadowLabService,
    _merge_knockout_draw_pen_risk,
)

CHECKS: list[tuple[str, bool, str]] = []

GERMANY = 1565176
NETHERLANDS = 1562345
BRAZIL = 1562344


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def _seed_knockout_fixture(
    conn,
    *,
    fixture_id: int,
    home: str,
    away: str,
    top10: list[dict],
    top1: str,
    lambda_home: float,
    lambda_away: float,
    round_name: str = "Round of 32",
    outcome: str | None = None,
    score: str | None = None,
    penalty: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    past = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO competitions(key, name, league_id, season, competition_type,
            supports_groups, supports_table, updated_at)
        VALUES ('world_cup_2026', 'World Cup 2026', 732, 2026, 'world_cup_finals', 1, 1, ?)
        """,
        (now,),
    )
    status = outcome or "NS"
    conn.execute(
        """
        INSERT OR REPLACE INTO fixtures(fixture_id, competition_key, home_team, away_team,
            kickoff_utc, status, round_name, is_placeholder, source, updated_at)
        VALUES (?, 'world_cup_2026', ?, ?, ?, ?, ?, 0, 'test', ?)
        """,
        (fixture_id, home, away, past, status, round_name, now),
    )
    if score and outcome:
        hg, ag = [int(x) for x in score.split("-", 1)]
        conn.execute(
            """
            INSERT OR REPLACE INTO fixture_results(
                fixture_id, competition_key, final_score, home_goals, away_goals,
                winner, over_under_2_5, total_goals, finished_at, source,
                match_outcome_type, penalty_score
            ) VALUES (?, 'world_cup_2026', ?, ?, ?, 'draw', 'under_2_5', ?, ?, 'test', ?, ?)
            """,
            (fixture_id, score, hg, ag, hg + ag, now, outcome, penalty),
        )
    for ddl in PHASE_ECSE_LIVE_DDL:
        conn.execute(ddl)
    insert_snapshot(
        conn,
        {
            "fixture_id": fixture_id,
            "competition_key": "world_cup_2026",
            "home_team": home,
            "away_team": away,
            "kickoff_utc": past,
            "model_version": "test",
            "lambda_home": lambda_home,
            "lambda_away": lambda_away,
            "top_10_scorelines": top10,
            "top_1_score": top1,
            "top_3_scores": [r["scoreline"] for r in top10[:3]],
            "top_5_scores": [r["scoreline"] for r in top10[:5]],
            "confidence_score": 0.5,
            "data_quality_score": 0.8,
            "raw_features": {
                "odds_row": {
                    "ft_home_closing": 2.1,
                    "ft_draw_closing": 3.2,
                    "ft_away_closing": 3.5,
                    "ou_under_25_closing": 1.85,
                    "btts_yes_closing": 1.9,
                    "btts_no_closing": 1.9,
                },
                "coverage": {"feature_coverage_count": 5},
            },
        },
    )
    conn.commit()


def main() -> int:
    print("validate_ecse_wc_knockout_draw_pen_risk")

    # Unit: deterministic risk levels
    top10_germany = [
        {"scoreline": "2-0", "probability": 0.17, "rank": 1},
        {"scoreline": "1-0", "probability": 0.13, "rank": 2},
        {"scoreline": "3-0", "probability": 0.12, "rank": 3},
        {"scoreline": "2-1", "probability": 0.10, "rank": 4},
        {"scoreline": "1-1", "probability": 0.08, "rank": 5},
        {"scoreline": "0-0", "probability": 0.07, "rank": 6},
        {"scoreline": "3-1", "probability": 0.06, "rank": 7},
        {"scoreline": "0-1", "probability": 0.05, "rank": 8},
        {"scoreline": "2-2", "probability": 0.04, "rank": 9},
        {"scoreline": "1-2", "probability": 0.03, "rank": 10},
    ]
    risk_g = compute_knockout_draw_pen_risk(
        competition_key="world_cup_2026",
        round_name="Round of 32",
        top10=top10_germany,
        top1="2-0",
        lambda_home=2.5,
        lambda_away=0.4,
        home_prob=0.70,
        away_prob=0.18,
        wde={"predicted_1x2": "home_win", "predicted_over_under_2_5": "under_2_5"},
        probs={"ft_draw": 0.24, "ou_under_25": 0.55},
    )
    check("germany_pattern_risk_signal", risk_g["knockout_draw_pen_risk"] is True, f"level={risk_g['risk_level']}")
    check("germany_rank_1_1", risk_g["rank_1_1"] == 5)

    top10_nl = [
        {"scoreline": "1-0", "probability": 0.13, "rank": 1},
        {"scoreline": "1-1", "probability": 0.12, "rank": 2},
        {"scoreline": "2-0", "probability": 0.10, "rank": 3},
        {"scoreline": "0-0", "probability": 0.09, "rank": 4},
        {"scoreline": "2-1", "probability": 0.08, "rank": 5},
        {"scoreline": "0-1", "probability": 0.08, "rank": 6},
        {"scoreline": "1-2", "probability": 0.07, "rank": 7},
        {"scoreline": "2-2", "probability": 0.06, "rank": 8},
        {"scoreline": "3-0", "probability": 0.05, "rank": 9},
        {"scoreline": "0-2", "probability": 0.04, "rank": 10},
    ]
    risk_nl = compute_knockout_draw_pen_risk(
        competition_key="world_cup_2026",
        round_name="Round of 32",
        top10=top10_nl,
        top1="1-0",
        lambda_home=1.43,
        lambda_away=0.97,
        home_prob=0.42,
        away_prob=0.35,
        wde={"predicted_1x2": "draw"},
        probs={"ft_draw": 0.28, "ou_under_25": 0.52},
    )
    check("netherlands_pattern_risk_signal", risk_nl["knockout_draw_pen_risk"] is True, f"level={risk_nl['risk_level']}")
    check("netherlands_rank_1_1", risk_nl["rank_1_1"] == 2)

    top10_brazil = [
        {"scoreline": "1-0", "probability": 0.15, "rank": 1},
        {"scoreline": "2-0", "probability": 0.14, "rank": 2},
        {"scoreline": "1-1", "probability": 0.10, "rank": 3},
        {"scoreline": "2-1", "probability": 0.09, "rank": 4},
        {"scoreline": "3-0", "probability": 0.08, "rank": 5},
        {"scoreline": "0-0", "probability": 0.07, "rank": 6},
        {"scoreline": "3-1", "probability": 0.06, "rank": 7},
        {"scoreline": "0-1", "probability": 0.05, "rank": 8},
        {"scoreline": "4-0", "probability": 0.04, "rank": 9},
        {"scoreline": "1-2", "probability": 0.03, "rank": 10},
    ]
    risk_br = compute_knockout_draw_pen_risk(
        competition_key="world_cup_2026",
        round_name="Round of 32",
        top10=top10_brazil,
        top1="1-0",
        lambda_home=1.86,
        lambda_away=0.64,
        home_prob=0.541,
        away_prob=0.26,
        wde={"predicted_1x2": "home_win"},
        probs={"ft_draw": 0.20, "ou_under_25": 0.42},
        match_outcome_type="FT",
        actual_score="2-1",
    )
    check(
        "brazil_no_false_pen_draw_risk",
        risk_br["knockout_draw_pen_risk"] is False or risk_br["risk_level"] == "NONE",
        f"level={risk_br['risk_level']}",
    )

    # Isolated DB artifact + lab merge
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "risk.db"
        conn = init_database(db)
        try:
            fid = 9_900_202
            _seed_knockout_fixture(
                conn,
                fixture_id=fid,
                home="Germany",
                away="Paraguay",
                top10=top10_germany,
                top1="2-0",
                lambda_home=2.5,
                lambda_away=0.4,
                outcome="PEN",
                score="1-1",
                penalty="3-4",
            )
            row = evaluate_fixture_knockout_risk(conn, fid)
            check("evaluate_fixture_row", row is not None and row.get("rank_1_1") == 5)
            check("penalty_score_preserved", row.get("penalty_score") == "3-4")
            base_membership = {r["scoreline"] for r in top10_germany}
            check("baseline_top10_unchanged", base_membership == {r["scoreline"] for r in top10_germany})

            out_jsonl = Path(tmp) / "risk.jsonl"
            out_sum = Path(tmp) / "risk.json"
            result = run_knockout_draw_pen_risk_evaluation(
                conn,
                jsonl_path=out_jsonl,
                summary_path=out_sum,
            )
            check("artifacts_created", out_jsonl.exists() and out_sum.exists())
            check("summary_has_historical_scan", "historical_scan" in result.summary)

            lab_item = {"fixture_id": fid, "owner_note": "base"}
            merged = _merge_knockout_draw_pen_risk(lab_item, conn, {})
            check("owner_lab_merge", merged.get("knockout_draw_pen_risk") is True)
        finally:
            conn.close()

    owner_report = (ROOT / "scripts" / "owner_today_10_exact_scores.py").read_text(encoding="utf-8")
    check("owner_report_includes_warning", "knockout_draw_pen_risk" in owner_report)
    check("owner_report_owner_only_note", "Owner-only research" in owner_report)

    route_src = (ROOT / "worldcup_predictor/api/routes/owner_ecse_shadow_lab.py").read_text(encoding="utf-8")
    check("owner_route_owner_only", "require_owner_user" in route_src)
    ecse_public = (ROOT / "worldcup_predictor/api/routes/ecse_display.py").read_text(encoding="utf-8")
    check("public_ecse_unchanged", "knockout_draw_pen_risk" not in ecse_public)

    # Production artifacts + fixtures when DB available
    settings = get_settings()
    prod_conn = connect(get_db_path(settings.sqlite_path))
    try:
        if RISK_SUMMARY.exists():
            prod_summary = json.loads(RISK_SUMMARY.read_text(encoding="utf-8"))
            check("production_artifacts", prod_summary.get("fixture_count", 0) >= 1)
        for fid, label in ((GERMANY, "germany"), (NETHERLANDS, "netherlands"), (BRAZIL, "brazil")):
            prod_row = evaluate_fixture_knockout_risk(prod_conn, fid, settings=settings)
            if prod_row:
                if fid in (GERMANY, NETHERLANDS):
                    check(
                        f"production_{label}_risk",
                        prod_row.get("knockout_draw_pen_risk") is True,
                        f"level={prod_row.get('risk_level')}",
                    )
                else:
                    check(
                        f"production_{label}_no_false_risk",
                        prod_row.get("knockout_draw_pen_risk") is False
                        or prod_row.get("risk_level") == "NONE",
                        f"level={prod_row.get('risk_level')}",
                    )
        pre_eval = prod_conn.execute(
            "SELECT final_score FROM fixture_results WHERE fixture_id = ?", (GERMANY,)
        ).fetchone()
        pre_score = dict(pre_eval)["final_score"] if pre_eval else None
        check("ecse_eval_score_stable_marker", pre_score == "1-1", pre_score or "missing")
    finally:
        prod_conn.close()

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{passed}/{len(CHECKS)} passed, {failed} failed")
    out = ROOT / "artifacts" / "validate_ecse_wc_knockout_draw_pen_risk.json"
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
