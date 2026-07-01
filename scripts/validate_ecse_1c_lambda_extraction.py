#!/usr/bin/env python3
"""Validate PHASE ECSE-1C lambda extraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_lambda_extraction import (
    METHOD_VERSION,
    audit_ecse_lambda_features,
    build_ecse_lambda_features,
    ensure_ecse_lambda_features_table,
    lambda_fingerprint,
)

CHECKS: list[tuple[str, bool, str]] = []
EXPECTED_DATASET = 217_518
EXPECTED_CLEAN = 1_908_702
EXPECTED_RESULTS = 222_985


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("ECSE-1C lambda extraction validation\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_lambda_features_table(conn)

    dataset_n = conn.execute("SELECT COUNT(1) FROM ecse_training_dataset").fetchone()[0]
    clean_n = conn.execute("SELECT COUNT(1) FROM historical_csv_odds_prematch_clean").fetchone()[0]
    results_n = conn.execute("SELECT COUNT(1) FROM historical_fixture_results").fetchone()[0]
    check("source_dataset_unchanged", dataset_n == EXPECTED_DATASET, f"rows={dataset_n}")
    check("source_clean_unchanged", clean_n == EXPECTED_CLEAN, f"rows={clean_n}")
    check("source_results_unchanged", results_n == EXPECTED_RESULTS, f"rows={results_n}")

    audit = audit_ecse_lambda_features(conn)
    check("lambda_table_populated", audit.get("rows", 0) > 0, f"rows={audit.get('rows', 0)}")
    check("lambdas_positive", audit.get("non_positive_lambdas", 1) == 0, f"bad={audit.get('non_positive_lambdas')}")
    check(
        "lambda_total_equals_sum",
        audit.get("lambda_total_mismatch", 1) == 0,
        f"mismatch={audit.get('lambda_total_mismatch')}",
    )
    check(
        "missing_draw_handled",
        audit.get("rows", 0) > 0 and audit.get("missing_draw_rows", 0) == audit.get("rows", 0),
        f"missing_draw={audit.get('missing_draw_rows')}/{audit.get('rows')} (expected all — SOURCE_EXPORT_GAP)",
    )
    check(
        "draw_proxy_populated",
        conn.execute(
            "SELECT COUNT(1) FROM ecse_lambda_features WHERE draw_proxy_probability IS NOT NULL"
        ).fetchone()[0]
        == audit.get("rows", 0),
        "all rows have draw_proxy",
    )
    check(
        "data_quality_ok",
        (audit.get("avg_data_quality_score") or 0) >= 0.35,
        f"avg={audit.get('avg_data_quality_score')}",
    )
    check(
        "insufficient_flagged_or_skipped",
        audit.get("insufficient_odds_rows", -1) == 0,
        f"insufficient_in_table={audit.get('insufficient_odds_rows')}",
    )
    skipped = EXPECTED_DATASET - audit.get("rows", 0)
    check(
        "insufficient_fixtures_skipped",
        skipped > 0,
        f"skipped={skipped} of {EXPECTED_DATASET}",
    )
    check("method_version", any(v["version"] == METHOD_VERSION for v in audit.get("method_versions", [])), METHOD_VERSION)

    fp_before = lambda_fingerprint(conn)
    before_rows = audit.get("rows", 0)
    rerun = build_ecse_lambda_features(conn, dry_run=False, rebuild=False)
    after_rows = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]
    fp_after = lambda_fingerprint(conn)
    check(
        "build_idempotent",
        rerun.rows_inserted == 0 and after_rows == before_rows,
        f"inserted={rerun.rows_inserted}",
    )
    check("fingerprint_stable", fp_before == fp_after, f"fp={fp_before}")

    summary_path = ROOT / "artifacts" / "ecse_1c_lambda_summary.json"
    check("summary_artifact_exists", summary_path.is_file(), str(summary_path))

    failed = sum(1 for _, ok, _ in CHECKS if not ok)
    print(f"\n{len(CHECKS) - failed}/{len(CHECKS)} checks passed")
    if failed:
        return 1

    out = ROOT / "artifacts" / "ecse_1c_validation.json"
    out.write_text(
        json.dumps({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in CHECKS]}, indent=2),
        encoding="utf-8",
    )
    print(f"Validation artifact: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
