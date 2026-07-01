#!/usr/bin/env python3
"""PHASE ECSE-1D-B — Rebuild 7x7 score grid distributions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_score_distribution import (
    DIXON_COLES_RHO_DEFAULT,
    LEGACY_AVG_OTHER_MASS,
    MAX_GOALS,
    METHOD_VERSION,
    audit_ecse_score_distributions,
    audit_grid_upgrade_sample,
    build_ecse_score_distributions,
    compare_grid_rank_stability,
    distribution_fingerprint,
    ensure_ecse_score_distributions_table,
    grid_scorelines_per_fixture,
    sample_top_n_summary,
)

SUMMARY_PATH = ROOT / "artifacts" / "ecse_1d_b_distribution_summary.json"
REPORT_PATH = ROOT / "ECSE_1D_B_SCORE_GRID_UPGRADE_REPORT.md"


def _report_md(summary: dict) -> str:
    b = summary["build"]
    a = summary["audit"]
    u = summary["grid_upgrade_sample"]
    lines = [
        "# ECSE-1D-B — Score Grid Upgrade Report",
        "",
        f"**Method:** `{METHOD_VERSION}` (independent Poisson, 0-0..{MAX_GOALS}-{MAX_GOALS} + OTHER)  ",
        f"**Dixon–Coles:** disabled (rho default {DIXON_COLES_RHO_DEFAULT}, not enabled)  ",
        f"**Fixtures:** {a.get('fixtures', 0):,}",
        "",
        "## Grid upgrade",
        "",
        "| Metric | Legacy 5x5 | Upgraded 7x7 |",
        "|--------|------------|--------------|",
        f"| Scorelines per fixture | 37 | {grid_scorelines_per_fixture()} |",
        f"| Avg OTHER mass | {LEGACY_AVG_OTHER_MASS:.4%} | {a.get('avg_other_probability', 0):.4%} |",
        f"| Avg grid mass captured | ~98.36% | {a.get('avg_grid_mass_pct', 0):.2f}% |",
        "",
        "## Rank stability (500-fixture sample)",
        "",
        f"- Top-1 stable: **{u.get('top1_stable_pct')}%**",
        f"- Avg top-3 overlap: **{u.get('avg_top3_overlap')}** / 3",
        f"- OTHER mass reduction: **{u.get('other_mass_reduction_pct')}%**",
        "",
        "## Validation",
        "",
        f"- Probability sum violations: **{a.get('fixtures_prob_sum_off', 0)}**",
        f"- Rank errors: **{a.get('fixtures_rank_errors', 0)}**",
        "",
        "---",
        "",
        "*No Dixon–Coles in build. No tuning. No deployment.*",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-1D-B score grid upgrade")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuild", action="store_true", default=True)
    parser.add_argument(
        "--enable-dixon-coles",
        action="store_true",
        help="Experimental only — default off per ECSE-1D-B spec",
    )
    parser.add_argument("--rho", type=float, default=DIXON_COLES_RHO_DEFAULT)
    args = parser.parse_args()

    print("ECSE-1D-B score grid upgrade\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_score_distributions_table(conn)

    fixtures_before = conn.execute(
        "SELECT COUNT(DISTINCT registry_fixture_id) FROM ecse_score_distributions"
    ).fetchone()[0]
    legacy_other_before = conn.execute(
        "SELECT AVG(probability) FROM ecse_score_distributions WHERE scoreline = 'OTHER'"
    ).fetchone()[0]

    stats = build_ecse_score_distributions(
        conn,
        dry_run=args.dry_run,
        rebuild=args.rebuild,
        max_goals=MAX_GOALS,
        use_dixon_coles=args.enable_dixon_coles,
        rho=args.rho,
    )
    audit = audit_ecse_score_distributions(conn)
    upgrade_sample = audit_grid_upgrade_sample(conn, sample_size=500)

    sample_lambda = conn.execute(
        "SELECT lambda_home, lambda_away FROM ecse_lambda_features ORDER BY registry_fixture_id LIMIT 1"
    ).fetchone()
    example_cmp = (
        compare_grid_rank_stability(float(sample_lambda[0]), float(sample_lambda[1]))
        if sample_lambda
        else {}
    )

    summary = {
        "phase": "ECSE-1D-B",
        "method_version": METHOD_VERSION,
        "max_goals": MAX_GOALS,
        "scorelines_per_fixture": grid_scorelines_per_fixture(),
        "use_dixon_coles": args.enable_dixon_coles,
        "dixon_coles_rho_default": DIXON_COLES_RHO_DEFAULT,
        "legacy_avg_other_mass": LEGACY_AVG_OTHER_MASS,
        "dry_run": args.dry_run,
        "rebuild": args.rebuild,
        "fixtures_before": fixtures_before,
        "legacy_other_mass_before": round(float(legacy_other_before or 0), 6) if legacy_other_before else None,
        "build": stats.to_dict(),
        "audit": audit,
        "grid_upgrade_sample": upgrade_sample,
        "example_fixture_comparison": example_cmp,
        "top5_sample": sample_top_n_summary(conn, sample_fixtures=3, top_n=5),
        "fingerprint": distribution_fingerprint(conn) if audit.get("fixtures") and not args.dry_run else None,
    }

    if not args.dry_run:
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        REPORT_PATH.write_text(_report_md(summary), encoding="utf-8")

    print(json.dumps({"build": stats.to_dict(), "audit": audit, "upgrade": upgrade_sample}, indent=2))
    if not args.dry_run:
        print(f"\nSummary: {SUMMARY_PATH}")
        print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
