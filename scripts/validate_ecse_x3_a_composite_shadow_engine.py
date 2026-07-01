#!/usr/bin/env python3
"""Validate PHASE ECSE-X3-A composite market algebra shadow engine."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x3.constants import (
    RECOMMENDATIONS,
    SHADOW_ARTIFACT,
    SUMMARY_ARTIFACT,
    ZZ2_BTTS_MIN,
    ZZ2_U25_MIN,
)
from worldcup_predictor.research.ecse_x3.mapping import score_all_methods
from worldcup_predictor.research.ecse_x3.signals import compute_composite_signals, signals_finite

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def validate_signal_formulas() -> None:
    probs = {
        "ft_home": 0.50,
        "ft_draw": 0.28,
        "ft_away": 0.22,
        "ou_over_15": 0.75,
        "ou_over_25": 0.52,
        "ou_under_25": 0.48,
        "btts_yes": 0.58,
        "btts_no": 0.42,
    }
    sig = compute_composite_signals(probs)
    check("H_formula", sig.H is not None and abs(sig.H - (0.50 + 0.52 + 0.58) / 3) < 1e-6)
    check("I_formula", sig.I is not None and abs(sig.I - (0.28 + 0.48 + 0.42) / 3) < 1e-6)
    check("ZZ2_formula", sig.zz2_flag is False)  # p_u25=0.48 < 0.52
    check("J2_formula", sig.J2 is not None and abs(sig.J2 - 0.52 / 0.58) < 1e-6)
    check("G_formula", sig.G is not None and abs(sig.G - abs(0.50 - 0.22) / 0.52) < 1e-6)
    check("OU_slope_formula", sig.ou_slope is not None and abs(sig.ou_slope - 0.75 / 0.52) < 1e-6)
    check("signals_finite", signals_finite(sig))


def validate_missing_odds_safe() -> None:
    sig = compute_composite_signals({})
    check("missing_all_recorded", len(sig.missing_fields) >= 5)
    check("missing_H_none", sig.H is None)
    check("missing_no_nan", all(v is None or math.isfinite(v) for v in (sig.H, sig.I, sig.J2, sig.G, sig.ou_slope)))


def validate_divide_by_zero() -> None:
    sig = compute_composite_signals(
        {
            "ft_home": 0.5,
            "ft_away": 0.5,
            "ou_over_25": 0.0,
            "btts_yes": 0.0,
        }
    )
    check("zero_den_G_none", sig.G is None)
    check("zero_den_J2_none", sig.J2 is None)


def validate_mapping_no_nan() -> None:
    dist = [
        {"scoreline": "1-0", "probability": 0.15, "rank": 1, "home_goals": 1, "away_goals": 0},
        {"scoreline": "1-1", "probability": 0.12, "rank": 2, "home_goals": 1, "away_goals": 1},
        {"scoreline": "2-1", "probability": 0.10, "rank": 3, "home_goals": 2, "away_goals": 1},
    ]
    probs = {
        "ft_home": 0.55,
        "ft_draw": 0.25,
        "ft_away": 0.20,
        "ou_over_15": 0.70,
        "ou_over_25": 0.50,
        "ou_under_25": 0.50,
        "btts_yes": 0.57,
        "btts_no": 0.43,
    }
    out = score_all_methods(dist_rows=dist, probs=probs)
    for method, rows in out["outputs"].items():
        probs_ok = all(math.isfinite(float(r["probability"])) for r in rows)
        check(f"mapping_finite_{method}", probs_ok)


def validate_unchanged_systems() -> None:
    conn = connect(get_db_path(get_settings().sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()
    preds = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    check("predictions_no_x3_leak", "ecse_x3" not in preds.lower())
    billing = (ROOT / "worldcup_predictor/billing/billing_service.py").read_text(encoding="utf-8")
    check("billing_unchanged", "ecse_x3" not in billing.lower())


def validate_artifacts() -> None:
    shadow = ROOT / SHADOW_ARTIFACT
    summary = ROOT / SUMMARY_ARTIFACT
    check("shadow_artifact_exists", shadow.is_file())
    check("summary_artifact_exists", summary.is_file())
    if summary.is_file():
        data = json.loads(summary.read_text(encoding="utf-8"))
        check("summary_has_methods", bool(data.get("method_results")))
        check("summary_has_folds", bool((data.get("method_results") or {}).get("composite_full", {}).get("fold_results")))
        check("summary_has_segments", bool(data.get("segment_results")))
        rec = (data.get("recommendation") or {}).get("recommendation")
        check("recommendation_enum", rec in RECOMMENDATIONS, str(rec))
        cov = data.get("coverage") or {}
        check("coverage_present", "missing_odds_rate_pct" in cov)
    if shadow.is_file():
        rows = [json.loads(ln) for ln in shadow.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("shadow_rows_present", len(rows) > 0, f"n={len(rows)}")
        if rows:
            r0 = rows[0]
            check("row_has_signals", "computed_signals" in r0)
            check("row_has_baseline", bool(r0.get("baseline_top10")))
            check("row_has_challengers", bool(r0.get("challenger_top10")))


def validate_deterministic() -> None:
    dist = [
        {"scoreline": "1-1", "probability": 0.2, "rank": 1, "home_goals": 1, "away_goals": 1},
        {"scoreline": "1-0", "probability": 0.15, "rank": 2, "home_goals": 1, "away_goals": 0},
    ]
    probs = {
        "ft_home": 0.6,
        "ft_draw": 0.22,
        "ft_away": 0.18,
        "ou_over_15": 0.72,
        "ou_over_25": 0.48,
        "ou_under_25": 0.55,
        "btts_yes": 0.59,
        "btts_no": 0.41,
    }
    a = score_all_methods(dist_rows=dist, probs=probs)
    b = score_all_methods(dist_rows=dist, probs=probs)
    check("deterministic_output", a["outputs"] == b["outputs"])


def validate_report() -> None:
    report = ROOT / "ECSE_X3_A_COMPOSITE_MARKET_ALGEBRA_SHADOW_REPORT.md"
    check("report_exists", report.is_file())


def main() -> int:
    print("ECSE-X3-A validation\n")
    validate_signal_formulas()
    validate_missing_odds_safe()
    validate_divide_by_zero()
    validate_mapping_no_nan()
    validate_unchanged_systems()
    validate_artifacts()
    validate_deterministic()
    validate_report()
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
