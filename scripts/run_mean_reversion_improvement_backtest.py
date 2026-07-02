#!/usr/bin/env python3
"""Phase MR-1 — Mean-reversion improvement backtest runner.

Tests three improvement techniques on top of the Strategy-D baseline
(odds 3.5–12) using the existing historical CSV odds database.

Usage
-----
    python scripts/run_mean_reversion_improvement_backtest.py
    python scripts/run_mean_reversion_improvement_backtest.py --db path/to/football_intelligence.db

Output
------
    artifacts/phase_mr1_mean_reversion_improvement/mr1_improvement_report.json

Research only — no API calls, no production writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_DB = ROOT / "data" / "football_intelligence.db"

PASS_MARK = "PASS"
FAIL_MARK = "FAIL"


def _check(label: str, condition: bool, detail: str = "") -> bool:
    status = PASS_MARK if condition else FAIL_MARK
    suffix = f" — {detail}" if detail else ""
    print(f"  [{status}] {label}{suffix}")
    return condition


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MR-1 mean-reversion improvement backtest")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="Path to SQLite database")
    parser.add_argument("--no-write", action="store_true", help="Skip writing artifact")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"[ERROR] Database not found: {db_path}")
        print("  The historical odds database is required. Run the historical CSV import first.")
        return 1

    print(f"\n=== Phase MR-1 — Mean-reversion improvement backtest ===")
    print(f"  Database : {db_path}")
    print()

    # ------------------------------------------------------------------
    # Run backtest
    # ------------------------------------------------------------------
    from worldcup_predictor.research.mean_reversion_improvement import (
        run,
        write_report,
        STRATEGIES,
    )

    print("Running backtest…")
    report = run(db_path)
    print(f"  Rows seen      : {report['rows_seen']:,}")
    print(f"  Rows evaluated : {report['rows_evaluated']:,}")
    print()

    # ------------------------------------------------------------------
    # Print strategy comparison table
    # ------------------------------------------------------------------
    strategies = report.get("strategies", {})
    improvements = report.get("improvement_vs_baseline", {})

    header = f"{'Strategy':<25} {'Bets':>6} {'ROI %':>8} {'Hit %':>7} {'Δ ROI':>8} {'CI95 low':>10} {'CI95 high':>10}"
    print(header)
    print("-" * len(header))

    baseline = strategies.get("baseline_D", {})
    b_roi = baseline.get("roi_pct")
    b_bets = baseline.get("bets", 0)

    for s in STRATEGIES:
        m = strategies.get(s, {})
        bets = m.get("bets") or 0
        roi = m.get("roi_pct")
        hit = m.get("hit_rate_pct")
        ci_lo = m.get("roi_ci95_low")
        ci_hi = m.get("roi_ci95_high")

        if s == "baseline_D":
            delta_str = "—"
        else:
            imp = improvements.get(s, {})
            d = imp.get("delta_roi_vs_baseline_pct")
            delta_str = f"{d:+.2f}%" if d is not None else "—"

        roi_str = f"{roi:.2f}%" if roi is not None else "—"
        hit_str = f"{hit:.1f}%" if hit is not None else "—"
        ci_str = f"[{ci_lo:.1f}, {ci_hi:.1f}]" if ci_lo is not None and ci_hi is not None else ""
        print(f"  {s:<23} {bets:>6,} {roi_str:>8} {hit_str:>7} {delta_str:>9}  {ci_str}")

    print()

    # ------------------------------------------------------------------
    # Validation checks
    # ------------------------------------------------------------------
    print("Validation checks:")
    passed = 0
    total = 0

    def chk(label: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, total
        total += 1
        if _check(label, cond, detail):
            passed += 1

    chk(
        "Baseline bets > 0",
        b_bets > 0,
        f"baseline_D has {b_bets} bets"
    )
    chk(
        "All strategies present",
        all(s in strategies for s in STRATEGIES),
    )

    # Check all improvement strategies have non-None ROI (or zero bets)
    for s in STRATEGIES:
        if s == "baseline_D":
            continue
        m = strategies.get(s, {})
        b = m.get("bets", 0)
        roi = m.get("roi_pct")
        chk(
            f"{s}: valid metrics",
            b == 0 or roi is not None,
            f"bets={b}, roi={roi}"
        )

    # CLV filter should reduce trade count vs baseline
    clv_bets = strategies.get("MR_CLV_filter", {}).get("bets", 0)
    chk(
        "CLV_filter reduces trade count",
        clv_bets <= b_bets,
        f"CLV={clv_bets} vs baseline={b_bets}"
    )

    # Calibration filter should reduce trade count
    calib_bets = strategies.get("MR_calib_filter", {}).get("bets", 0)
    chk(
        "calib_filter reduces trade count",
        calib_bets <= b_bets,
        f"calib={calib_bets} vs baseline={b_bets}"
    )

    # Dynamic Kelly should have fractional total stake
    dk_staked = strategies.get("MR_dynamic_kelly", {}).get("staked", 0)
    dk_bets = strategies.get("MR_dynamic_kelly", {}).get("bets", 0)
    chk(
        "dynamic_kelly uses fractional stakes",
        dk_bets == 0 or dk_staked < dk_bets,
        f"staked={dk_staked:.1f} bets={dk_bets}"
    )

    # Combined has fewer or equal bets than CLV alone
    comb_bets = strategies.get("MR_combined", {}).get("bets", 0)
    chk(
        "combined <= CLV_filter bets",
        comb_bets <= clv_bets,
        f"combined={comb_bets} CLV={clv_bets}"
    )

    chk("Report has disclaimer", bool(report.get("disclaimer")))
    chk("Technique summary present", bool(report.get("technique_summary")))
    chk(
        "Calibration bucket catalogue present",
        len(report.get("calibration_bucket_catalogue", [])) > 0
    )

    print()

    # ------------------------------------------------------------------
    # Write artifact
    # ------------------------------------------------------------------
    if not args.no_write:
        from worldcup_predictor.research.mean_reversion_improvement import write_report
        out = write_report(report)
        print(f"Artifact written: {out}")
    else:
        print("(--no-write: artifact skipped)")

    print()
    print(f"Result: {passed}/{total} checks passed")

    # ------------------------------------------------------------------
    # Insight summary
    # ------------------------------------------------------------------
    print()
    print("=== Insight summary ===")
    for s, info in improvements.items():
        d = info.get("delta_roi_vs_baseline_pct")
        roi = info.get("roi_pct")
        n = info.get("trade_count") or 0
        direction = "↑ improves" if (d or 0) > 0 else ("↓ hurts" if (d or 0) < 0 else "neutral")
        print(f"  {s:<25}  ROI={roi}%  Δ={'+' if (d or 0) >= 0 else ''}{d}%  n={n:,}  [{direction}]")

    print()
    print("Techniques (no code changes to engine required):")
    for name, desc in (report.get("technique_summary") or {}).items():
        print(f"  [{name}]")
        # wrap at 80 chars
        words = desc.split()
        line = "    "
        for w in words:
            if len(line) + len(w) + 1 > 82:
                print(line)
                line = "    " + w + " "
            else:
                line += w + " "
        if line.strip():
            print(line)

    return 0 if passed == total else 2


if __name__ == "__main__":
    sys.exit(main())
