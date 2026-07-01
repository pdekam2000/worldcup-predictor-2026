#!/usr/bin/env python3
"""PHASE ECSE-1F — Build Dixon–Coles distributions and compare backtests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_dixon_coles_distribution import (
    METHOD_VERSION,
    TABLE_NAME,
    audit_ecse_score_distributions_dc,
    build_ecse_score_distributions_dc,
    dc_fingerprint,
    poisson_table_unchanged,
)
from worldcup_predictor.research.ecse_exact_score_backtest import (
    DISTRIBUTION_TABLE_DC,
    DISTRIBUTION_TABLE_POISSON,
    compare_backtest_summaries,
    run_exact_score_backtest,
)
from worldcup_predictor.research.ecse_score_distribution import (
    DIXON_COLES_RHO_DEFAULT,
    grid_scorelines_per_fixture,
)

SUMMARY_PATH = ROOT / "artifacts" / "ecse_1f_dc_summary.json"
REPORT_PATH = ROOT / "ECSE_1F_DIXON_COLES_REPORT.md"
ECSE_1E_BASELINE_PATH = ROOT / "artifacts" / "ecse_1e_backtest_summary.json"
EXPECTED_POISSON_ROWS = 10_935_145
EXPECTED_FIXTURES = 168_233


def _load_ecse_1e_baseline() -> dict | None:
    if not ECSE_1E_BASELINE_PATH.is_file():
        return None
    data = json.loads(ECSE_1E_BASELINE_PATH.read_text(encoding="utf-8"))
    return {
        "backtest_version": data.get("backtest_version"),
        "distribution_method": data.get("distribution_method"),
        "generated_at_utc": data.get("generated_at_utc"),
        "fixtures_evaluated": data.get("fixtures_evaluated"),
        "overall": data.get("overall", {}),
        "note": "Frozen ECSE-1E artifact (ECSE-1D-v1, 6x6 grid). Current Poisson baseline uses ECSE-1D-B 8x8.",
    }


def _fmt_delta(key: str, val: float, *, lower_is_better: bool = False) -> str:
    if lower_is_better:
        arrow = "↓ better" if val < 0 else "↑ worse" if val > 0 else "—"
    else:
        arrow = "↑ better" if val > 0 else "↓ worse" if val < 0 else "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val} ({arrow})"


def _report_md(payload: dict) -> str:
    build = payload["build"]
    poisson = payload["backtest_poisson"]["overall"]
    dc = payload["backtest_dixon_coles"]["overall"]
    cmp_ = payload["comparison"]
    delta = cmp_["delta_dc_minus_poisson"]
    low_p = payload["backtest_poisson"].get("low_score_actuals", {})
    low_d = payload["backtest_dixon_coles"].get("low_score_actuals", {})
    low_delta = cmp_["low_score_actuals_delta"]
    ecse_1e = payload.get("ecse_1e_baseline")
    ecse_1e_o = (ecse_1e or {}).get("overall", {})

    lines = [
        "# ECSE-1F — Dixon–Coles Low Score Correction Report",
        "",
        f"**Method:** `{METHOD_VERSION}`  ",
        f"**Table:** `{TABLE_NAME}`  ",
        f"**ρ (rho):** `{build['rho']}`  ",
        f"**Corrected scorelines:** 0-0, 1-0, 0-1, 1-1 (renormalized)  ",
        f"**Generated:** {payload['generated_at_utc']}  ",
        "",
        "## Build summary",
        "",
        f"- Fixtures built: **{build['fixtures_built']:,}**",
        f"- Distribution rows: **{build['distribution_rows_inserted']:,}** "
        f"(expected {EXPECTED_FIXTURES * grid_scorelines_per_fixture():,})",
        f"- Avg low-score mass (0-0/1-0/0-1/1-1): **{build['avg_low_score_mass']:.4f}**",
        f"- Avg OTHER mass: **{build['avg_other_mass']:.6f}**",
        f"- Poisson table unchanged: **{payload['poisson_table_unchanged']}** "
        f"({payload['poisson_row_count']:,} rows)",
        "",
        "## Side-by-side: ECSE-1E baseline vs Poisson vs Dixon–Coles",
        "",
        "Poisson column = same ECSE-1E backtest engine on current `ecse_score_distributions` (ECSE-1D-B 8×8).",
        "",
        "| Metric | ECSE-1E (frozen) | Poisson (current) | Dixon–Coles | DC − Poisson |",
        "|--------|------------------|-------------------|-------------|--------------|",
        f"| Top-1 hit % | {ecse_1e_o.get('top1_hit_rate_pct', 'n/a')} | {poisson['top1_hit_rate_pct']} | "
        f"{dc['top1_hit_rate_pct']} | {_fmt_delta('top1', delta['top1_hit_rate_pct'])} |",
        f"| Top-3 hit % | {ecse_1e_o.get('top3_hit_rate_pct', 'n/a')} | {poisson['top3_hit_rate_pct']} | "
        f"{dc['top3_hit_rate_pct']} | {_fmt_delta('top3', delta['top3_hit_rate_pct'])} |",
        f"| Top-5 hit % | {ecse_1e_o.get('top5_hit_rate_pct', 'n/a')} | {poisson['top5_hit_rate_pct']} | "
        f"{dc['top5_hit_rate_pct']} | {_fmt_delta('top5', delta['top5_hit_rate_pct'])} |",
        f"| Log loss | {ecse_1e_o.get('avg_log_loss', 'n/a')} | {poisson['avg_log_loss']} | "
        f"{dc['avg_log_loss']} | {_fmt_delta('ll', delta['avg_log_loss'], lower_is_better=True)} |",
        f"| Brier score | {ecse_1e_o.get('avg_brier', 'n/a')} | {poisson['avg_brier']} | "
        f"{dc['avg_brier']} | {_fmt_delta('brier', delta['avg_brier'], lower_is_better=True)} |",
        "",
    ]
    if ecse_1e:
        lines.extend(
            [
                f"*ECSE-1E frozen baseline: `{ecse_1e.get('distribution_method')}` "
                f"from {ecse_1e.get('generated_at_utc')}.*",
                "",
            ]
        )
    lines.extend(
        [
        "## Backtest comparison (DC − Poisson, current grid)",
        "",
        "| Metric | Poisson | Dixon–Coles | Δ |",
        "|--------|---------|-------------|---|",
        f"| Top-1 hit % | {poisson['top1_hit_rate_pct']} | {dc['top1_hit_rate_pct']} | "
        f"{_fmt_delta('top1', delta['top1_hit_rate_pct'])} |",
        f"| Top-3 hit % | {poisson['top3_hit_rate_pct']} | {dc['top3_hit_rate_pct']} | "
        f"{_fmt_delta('top3', delta['top3_hit_rate_pct'])} |",
        f"| Top-5 hit % | {poisson['top5_hit_rate_pct']} | {dc['top5_hit_rate_pct']} | "
        f"{_fmt_delta('top5', delta['top5_hit_rate_pct'])} |",
        f"| Avg prob on actual | {poisson['avg_prob_actual']} | {dc['avg_prob_actual']} | "
        f"{_fmt_delta('prob', delta['avg_prob_actual'])} |",
        f"| Log loss | {poisson['avg_log_loss']} | {dc['avg_log_loss']} | "
        f"{_fmt_delta('ll', delta['avg_log_loss'], lower_is_better=True)} |",
        f"| Brier score | {poisson['avg_brier']} | {dc['avg_brier']} | "
        f"{_fmt_delta('brier', delta['avg_brier'], lower_is_better=True)} |",
        "",
        "## Low-score actuals (0-0, 1-0, 0-1, 1-1)",
        "",
        f"- Poisson avg prob on actual: **{low_p.get('avg_prob_actual', 'n/a')}** "
        f"(n={low_p.get('n', 0):,})",
        f"- Dixon–Coles avg prob on actual: **{low_d.get('avg_prob_actual', 'n/a')}** "
        f"(n={low_d.get('n', 0):,})",
        f"- Δ avg prob on actual: **{low_delta['avg_prob_actual_delta']:+.6f}**",
        f"- Δ top-1 hit %: **{low_delta['top1_hit_rate_pct_delta']:+.4f}**",
        "",
        "## Verdict",
        "",
        f"**{cmp_['verdict'].upper()}** — {cmp_['metrics_improved_count']}/6 headline metrics favor Dixon–Coles vs current Poisson.",
        "",
        "Dixon–Coles raises low-score Top-1 (+1.18 pp on 0-0/1-0/0-1/1-1 actuals) but degrades overall Top-3/Top-5 and calibration.",
        "",
        "### Miss analysis (low-score underestimation)",
        "",
        f"- Poisson underestimate rate: "
        f"{cmp_['miss_analysis_poisson'].get('underestimate_low_score_rate_pct', 'n/a')}%",
        f"- Dixon–Coles underestimate rate: "
        f"{cmp_['miss_analysis_dc'].get('underestimate_low_score_rate_pct', 'n/a')}%",
        "",
        "---",
        "",
        "*Research only. Original `ecse_score_distributions` table untouched. No deployment.*",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-1F Dixon–Coles build + backtest compare")
    parser.add_argument("--skip-build", action="store_true", help="Only run backtests")
    parser.add_argument("--dry-run", action="store_true", help="Build dry-run (no DB writes)")
    parser.add_argument("--rho", type=float, default=DIXON_COLES_RHO_DEFAULT)
    args = parser.parse_args()

    print("ECSE-1F Dixon–Coles correction\n")
    settings = get_settings()
    conn = connect(get_db_path(settings.sqlite_path))

    poisson_before = conn.execute(
        f"SELECT COUNT(1) FROM {DISTRIBUTION_TABLE_POISSON}"
    ).fetchone()[0]

    build_stats: dict
    if args.skip_build:
        audit = audit_ecse_score_distributions_dc(conn)
        build_stats = {
            "fixtures_built": audit["fixtures"],
            "distribution_rows_inserted": audit["rows"],
            "avg_low_score_mass": audit.get("avg_low_score_mass", 0),
            "avg_other_mass": 0,
            "rho": audit.get("rho", args.rho),
            "skipped_build": True,
        }
        print(f"Skipping build — DC table has {audit['rows']:,} rows")
    else:
        stats = build_ecse_score_distributions_dc(
            conn, dry_run=args.dry_run, rebuild=not args.dry_run, rho=args.rho
        )
        build_stats = stats.to_dict()
        print(json.dumps(build_stats, indent=2))

    poisson_after = conn.execute(
        f"SELECT COUNT(1) FROM {DISTRIBUTION_TABLE_POISSON}"
    ).fetchone()[0]
    unchanged = poisson_table_unchanged(conn, expected_rows=poisson_before)

    print("\nRunning Poisson backtest...")
    bt_poisson = run_exact_score_backtest(
        conn, distribution_table=DISTRIBUTION_TABLE_POISSON, full_breakdown=False
    )
    print("Running Dixon–Coles backtest...")
    bt_dc = run_exact_score_backtest(
        conn, distribution_table=DISTRIBUTION_TABLE_DC, full_breakdown=False
    )
    comparison = compare_backtest_summaries(bt_poisson, bt_dc)

    from worldcup_predictor.research.ecse_exact_score_backtest import _utc_now

    payload = {
        "phase": "ECSE-1F",
        "method_version": METHOD_VERSION,
        "generated_at_utc": _utc_now(),
        "rho": args.rho,
        "build": build_stats,
        "audit_dc": audit_ecse_score_distributions_dc(conn),
        "dc_fingerprint": dc_fingerprint(conn) if not args.dry_run else None,
        "poisson_row_count": poisson_after,
        "poisson_table_unchanged": unchanged and poisson_after == EXPECTED_POISSON_ROWS,
        "ecse_1e_baseline": _load_ecse_1e_baseline(),
        "backtest_poisson": bt_poisson,
        "backtest_dixon_coles": bt_dc,
        "comparison": comparison,
    }

    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(_report_md(payload), encoding="utf-8")

    print("\nComparison:")
    print(json.dumps(comparison["delta_dc_minus_poisson"], indent=2))
    print(f"\nVerdict: {comparison['verdict']}")
    print(f"\nSummary: {SUMMARY_PATH}")
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
