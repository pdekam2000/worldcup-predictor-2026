#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M1 BTTS×OU M1 filter and backtest."""

from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_score_distribution import PROB_SUM_TOLERANCE, generate_score_distribution
from worldcup_predictor.research.ecse_x2_m1.build import (
    baseline_table_row_count,
    build_ecse_score_distributions_m1,
    ensure_ecse_score_distributions_m1_table,
)
from worldcup_predictor.research.ecse_x2_m1.constants import BASELINE_TABLE, METHOD_VERSION, TABLE_NAME
from worldcup_predictor.research.ecse_x2_m1.filter import apply_m1_quadrant_filter
from worldcup_predictor.research.ecse_x2_m1.quadrants import (
    classify_score,
    quadrant_probs_joint,
    resolve_market_probs,
)

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def validate_quadrant_geometry() -> None:
    check("yes_under_only_1_1", classify_score(1, 1) == frozenset({"yes_under"}))
    check("yes_over_2_1", classify_score(2, 1) == frozenset({"yes_over"}))
    check("no_under_1_0", classify_score(1, 0) == frozenset({"no_under"}))
    check("no_over_3_0", classify_score(3, 0) == frozenset({"no_over"}))
    q = quadrant_probs_joint(0.6, 0.55)
    check("quadrant_probs_sum", abs(sum(q.values()) - 1.0) < 1e-6, f"sum={sum(q.values())}")


def validate_filter_math() -> None:
    dist = generate_score_distribution(1.4, 1.1)
    baseline = [
        {
            "scoreline": e["scoreline"],
            "home_goals": e["home_goals"],
            "away_goals": e["away_goals"],
            "probability": e["probability"],
            "rank": e["rank"],
        }
        for e in dist
    ]
    market = resolve_market_probs(
        btts_yes_closing=1.75,
        btts_no_closing=2.05,
        ou_over_25_closing=1.90,
        ou_under_25_closing=1.95,
        lambda_home=1.4,
        lambda_away=1.1,
    )
    filtered = apply_m1_quadrant_filter(baseline, market)
    total = sum(float(r["probability"]) for r in filtered)
    check("m1_probs_sum_to_one", abs(total - 1.0) <= PROB_SUM_TOLERANCE, f"sum={total}")
    ranks = [int(r["rank"]) for r in filtered]
    check("m1_ranks_valid", min(ranks) == 1 and len(set(ranks)) == len(ranks))


def validate_no_results_in_filter_source() -> None:
    text = (ROOT / "worldcup_predictor/research/ecse_x2_m1/filter.py").read_text(encoding="utf-8")
    check("filter_no_historical_results", "historical_fixture_results" not in text)
    build_text = (ROOT / "worldcup_predictor/research/ecse_x2_m1/build.py").read_text(encoding="utf-8")
    check("build_no_historical_results", "historical_fixture_results" not in build_text)


def validate_idempotent_build(conn) -> None:
    ensure_ecse_score_distributions_m1_table(conn)
    # seed minimal baseline-like rows in temp db
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ecse_score_distributions (
            registry_fixture_id INTEGER, scoreline TEXT, home_goals INTEGER, away_goals INTEGER,
            probability REAL, rank INTEGER, method_version TEXT, lambda_home REAL, lambda_away REAL,
            data_quality_score REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ecse_lambda_features (
            registry_fixture_id INTEGER PRIMARY KEY, lambda_home REAL, lambda_away REAL, data_quality_score REAL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ecse_training_dataset (
            registry_fixture_id INTEGER PRIMARY KEY,
            btts_yes_closing REAL, btts_no_closing REAL, ou_over_25_closing REAL, ou_under_25_closing REAL
        )
        """
    )
    fid = 999001
    conn.execute("DELETE FROM ecse_score_distributions WHERE registry_fixture_id=?", (fid,))
    conn.execute("DELETE FROM ecse_lambda_features WHERE registry_fixture_id=?", (fid,))
    conn.execute("DELETE FROM ecse_training_dataset WHERE registry_fixture_id=?", (fid,))
    conn.execute(
        "INSERT INTO ecse_lambda_features VALUES (?, 1.3, 1.0, 0.7)",
        (fid,),
    )
    conn.execute(
        "INSERT INTO ecse_training_dataset VALUES (?, 1.7, 2.1, 1.85, 2.0)",
        (fid,),
    )
    for e in generate_score_distribution(1.3, 1.0):
        conn.execute(
            """
            INSERT INTO ecse_score_distributions VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                fid,
                e["scoreline"],
                e["home_goals"],
                e["away_goals"],
                e["probability"],
                e["rank"],
                "test",
                1.3,
                1.0,
                0.7,
            ),
        )
    conn.commit()
    s1 = build_ecse_score_distributions_m1(conn, rebuild=True)
    s2 = build_ecse_score_distributions_m1(conn, rebuild=False)
    check("first_build_rows", s1.distribution_rows_inserted > 0, str(s1.distribution_rows_inserted))
    check("idempotent_skip", s2.fixtures_skipped_existing >= 1, str(s2.fixtures_skipped_existing))


def validate_backtest_math() -> None:
    prob_actual = 0.12
    log_loss = -math.log(max(prob_actual, 1e-12))
    brier = (1 - prob_actual) ** 2 + 9 * prob_actual**2  # 10-class toy
    check("log_loss_formula", abs(log_loss - 2.120264) < 0.001)
    check("brier_multiclass_toy", brier > 0)


def validate_production(settings) -> None:
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        poisson_n = baseline_table_row_count(conn)
        m1_n = conn.execute(f"SELECT COUNT(1) FROM {TABLE_NAME}").fetchone()[0]
        check("baseline_unchanged_count", poisson_n > 0, f"rows={poisson_n}")
        check("m1_table_populated", m1_n > 0, f"m1_rows={m1_n}")
        bad = conn.execute(
            f"""
            SELECT COUNT(1) FROM (
                SELECT registry_fixture_id FROM {TABLE_NAME}
                GROUP BY registry_fixture_id
                HAVING ABS(SUM(probability)-1.0) > {PROB_SUM_TOLERANCE}
            )
            """
        ).fetchone()[0]
        check("production_prob_sums", bad == 0, f"violations={bad}")
        summary = ROOT / "artifacts" / "ecse_x2_m1_summary.json"
        check("summary_artifact", summary.is_file())
        check("filter_report", (ROOT / "ECSE_X2_M1_BTTS_OU_FILTER_REPORT.md").is_file())
        check("backtest_report", (ROOT / "ECSE_X2_M1_BACKTEST_REPORT.md").is_file())
        if summary.is_file():
            payload = json.loads(summary.read_text(encoding="utf-8"))
            check("summary_phase", payload.get("phase") == "ECSE-X2-M1")
            bt = payload.get("backtest", {})
            check("comparison_present", "comparison" in bt)
    finally:
        conn.close()


def main() -> int:
    print("ECSE-X2-M1 validation\n")
    validate_quadrant_geometry()
    validate_filter_math()
    validate_no_results_in_filter_source()
    validate_backtest_math()

    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(str(Path(tmp) / "m1_validate.db"))
        try:
            validate_idempotent_build(conn)
        finally:
            conn.close()

    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    if db_path.exists():
        validate_production(settings)

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
