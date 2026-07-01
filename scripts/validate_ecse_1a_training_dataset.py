#!/usr/bin/env python3
"""Validate PHASE ECSE-1A ECSE training dataset."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_training_dataset import (
    FEATURE_COLUMNS,
    ODDS_FEATURE_SPECS,
    audit_ecse_training_dataset,
    build_ecse_training_dataset,
    dataset_fingerprint,
    ensure_ecse_training_dataset_table,
)

CHECKS: list[tuple[str, bool, str]] = []
EXPECTED_SOURCE_CLEAN = 1_908_702
EXPECTED_SOURCE_RESULTS = 222_985


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("ECSE-1A training dataset validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_training_dataset_table(conn)

    clean_count = conn.execute("SELECT COUNT(1) FROM historical_csv_odds_prematch_clean").fetchone()[0]
    results_count = conn.execute("SELECT COUNT(1) FROM historical_fixture_results").fetchone()[0]
    check("source_clean_unchanged", clean_count == EXPECTED_SOURCE_CLEAN, f"rows={clean_count}")
    check("source_results_unchanged", results_count == EXPECTED_SOURCE_RESULTS, f"rows={results_count}")

    audit = audit_ecse_training_dataset(conn)
    check("dataset_populated", audit["dataset_rows"] > 0, f"rows={audit['dataset_rows']}")
    check(
        "dataset_matches_eligible_fixtures",
        audit["dataset_rows"] == audit["eligible_fixtures"],
        f"dataset={audit['dataset_rows']} eligible={audit['eligible_fixtures']}",
    )
    check("no_orphan_rows", audit["orphan_rows"] == 0, f"orphans={audit['orphan_rows']}")
    check("labels_consistent", audit["label_mismatch_rows"] == 0, f"mismatch={audit['label_mismatch_rows']}")
    check(
        "feature_coverage_present",
        audit["avg_feature_coverage"] >= 3.0,
        f"avg={audit['avg_feature_coverage']}",
    )
    check(
        "feature_column_count",
        audit["feature_columns"] == len(FEATURE_COLUMNS),
        f"cols={audit['feature_columns']}",
    )
    check(
        "feature_spec_count",
        audit["feature_specs"] == len(ODDS_FEATURE_SPECS),
        f"specs={audit['feature_specs']}",
    )

    # Core ECSE labels populated
    null_labels = conn.execute(
        """
        SELECT COUNT(1) FROM ecse_training_dataset
        WHERE exact_score IS NULL OR home_goals IS NULL OR away_goals IS NULL
           OR goal_difference IS NULL OR total_goals IS NULL
        """
    ).fetchone()[0]
    check("labels_non_null", null_labels == 0, f"null_rows={null_labels}")

    # ft + ou core features present on majority of rows
    ft_cov = conn.execute(
        """
        SELECT COUNT(1) FROM ecse_training_dataset
        WHERE ft_home_closing IS NOT NULL OR ft_away_closing IS NOT NULL
        """
    ).fetchone()[0]
    ft_pct = round(100.0 * ft_cov / max(audit["dataset_rows"], 1), 2)
    check("ft_odds_coverage", ft_pct >= 30.0, f"coverage={ft_pct}%")

    ou_cov = conn.execute(
        """
        SELECT COUNT(1) FROM ecse_training_dataset
        WHERE ou_over_25_closing IS NOT NULL
        """
    ).fetchone()[0]
    ou_pct = round(100.0 * ou_cov / max(audit["dataset_rows"], 1), 2)
    check("ou_25_coverage", ou_pct >= 50.0, f"coverage={ou_pct}%")

    fp_before = dataset_fingerprint(conn)
    before_rows = audit["dataset_rows"]
    rerun = build_ecse_training_dataset(conn, dry_run=False, rebuild=False)
    after_rows = conn.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    fp_after = dataset_fingerprint(conn)
    check(
        "build_idempotent",
        rerun.rows_inserted == 0 and after_rows == before_rows,
        f"inserted={rerun.rows_inserted}",
    )
    check("fingerprint_stable", fp_before == fp_after, f"fp={fp_before}")

    summary_path = ROOT / "artifacts" / "ecse_1a_build_summary.json"
    check("summary_artifact_exists", summary_path.is_file(), str(summary_path))

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    if failed:
        return 1

    out = ROOT / "artifacts" / "ecse_1a_validation.json"
    out.write_text(
        json.dumps({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS]}, indent=2),
        encoding="utf-8",
    )
    print(f"Validation artifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
