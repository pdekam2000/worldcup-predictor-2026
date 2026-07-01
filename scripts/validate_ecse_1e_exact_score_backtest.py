#!/usr/bin/env python3
"""Validate PHASE ECSE-1E exact score backtest."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_exact_score_backtest import (
    EXPECTED_LAMBDA_ROWS,
    run_exact_score_backtest,
    verify_hit_rate_sample,
    verify_join_integrity,
)
from worldcup_predictor.research.ecse_score_distribution import generation_uses_result_labels

CHECKS: list[tuple[str, bool, str]] = []
EXPECTED_DATASET = 217_518
EXPECTED_DIST_ROWS = 10_935_145


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("ECSE-1E exact score backtest validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))

    lambda_n = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]
    dataset_n = conn.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    dist_n = conn.execute("SELECT COUNT(1) FROM ecse_score_distributions").fetchone()[0]
    results_n = conn.execute("SELECT COUNT(1) FROM historical_fixture_results").fetchone()[0]

    check("source_lambda_unchanged", lambda_n == EXPECTED_LAMBDA_ROWS, f"rows={lambda_n}")
    check("source_dataset_unchanged", dataset_n == EXPECTED_DATASET, f"rows={dataset_n}")
    check("source_distributions_unchanged", dist_n == EXPECTED_DIST_ROWS, f"rows={dist_n}")
    check("source_results_unchanged", results_n == 222_985, f"rows={results_n}")

    join = verify_join_integrity(conn)
    check(
        "labels_join_correctly",
        join["joined_fixtures"] == EXPECTED_LAMBDA_ROWS,
        f"joined={join['joined_fixtures']}",
    )
    check(
        "join_coverage",
        join["join_coverage_pct"] >= 99.9,
        f"pct={join['join_coverage_pct']}",
    )
    check(
        "per_fixture_prob_sums",
        join["fixtures_prob_sum_off"] == 0,
        f"off={join['fixtures_prob_sum_off']}",
    )
    check(
        "no_labels_in_distribution_generation",
        not generation_uses_result_labels(),
        "ECSE-1D generator audit",
    )

    sample = verify_hit_rate_sample(conn, sample_id=1)
    check("sample_top1_hit_math", sample["top1_hit"] == (sample["rank"] == 1), str(sample))
    check("sample_top3_hit_math", sample["top3_hit"] == (sample["rank"] <= 3), f"rank={sample['rank']}")

    summary_path = ROOT / "artifacts" / "ecse_1e_backtest_summary.json"
    check("summary_artifact_exists", summary_path.is_file(), str(summary_path))
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        o = summary["overall"]
        check("fixtures_evaluated", summary["fixtures_evaluated"] == EXPECTED_LAMBDA_ROWS, str(summary["fixtures_evaluated"]))
        check(
            "hit_rates_ordered",
            o["top1_hit_rate_pct"] <= o["top3_hit_rate_pct"] <= o["top5_hit_rate_pct"] <= o["top10_hit_rate_pct"],
            f"top1={o['top1_hit_rate_pct']} top10={o['top10_hit_rate_pct']}",
        )
        check("log_loss_finite", math.isfinite(o["avg_log_loss"]) and o["avg_log_loss"] > 0, str(o["avg_log_loss"]))
        check("brier_in_range", 0 <= o["avg_brier"] <= 2.0, str(o["avg_brier"]))
        ecse_top1 = o["top1_hit_rate_pct"]
        hist_top1 = summary["baselines"][0]["top1_hit_rate_pct"]
        check(
            "ecse_beats_historical_mode_baseline",
            ecse_top1 >= hist_top1 * 0.5,
            f"ecse={ecse_top1} hist={hist_top1}",
        )

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    if failed:
        return 1

    out = ROOT / "artifacts" / "ecse_1e_validation.json"
    out.write_text(
        json.dumps({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS]}, indent=2),
        encoding="utf-8",
    )
    print(f"Validation artifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
