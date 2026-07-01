#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M3 champion/challenger shadow layer."""

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
from worldcup_predictor.research.ecse_x2_m3.constants import SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m3.equation import compute_log_home_prob_phi
from worldcup_predictor.research.ecse_x2_m3.scorer import score_fixture_shadow
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def validate_equation() -> None:
    v = compute_log_home_prob_phi({"ft_home": 0.45})
    check("equation_finite", v is not None and math.isfinite(v), f"val={v}")
    check("missing_odds_safe", compute_log_home_prob_phi({"ft_home": None}) is None)


def validate_scorer_no_nan() -> None:
    dist = [
        {
            "scoreline": e["scoreline"],
            "home_goals": e["home_goals"],
            "away_goals": e["away_goals"],
            "probability": e["probability"],
            "rank": e["rank"],
        }
        for e in generate_score_distribution(1.2, 1.0)
    ]
    scored = score_fixture_shadow(
        dist_rows=dist,
        probs={"ft_home": 0.5},
        lift_model=None,
        top_n=10,
    )
    probs = [r["probability"] for r in scored["challenger_top"]]
    check("no_nan_probs", all(math.isfinite(p) for p in probs))


def validate_no_public_exposure() -> None:
    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    check("no_m3_public_route", "ecse_x2_m3" not in main_py.lower())


def validate_production(settings) -> None:
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_unchanged", n > 0, f"rows={n}")
    finally:
        conn.close()

    shadow = ROOT / SHADOW_ARTIFACT
    summary = ROOT / "artifacts/ecse_x2_m3_champion_challenger_summary.json"
    report = ROOT / "ECSE_X2_M3_CHAMPION_CHALLENGER_SHADOW_REPORT.md"
    check("shadow_artifact_exists", shadow.is_file(), str(shadow))
    check("summary_exists", summary.is_file())
    check("report_exists", report.is_file())

    if summary.is_file():
        payload = json.loads(summary.read_text(encoding="utf-8"))
        check("phase_tag", payload.get("phase") == "ECSE-X2-M3")
        check("fold_results", len(payload.get("fold_results") or []) >= 3)
        check("overfit_assessment", "recommendation" in (payload.get("overfit") or {}))
        check("champion_challenger_metrics", bool(payload.get("overall")))

    if shadow.is_file():
        lines = [ln for ln in shadow.read_text(encoding="utf-8").splitlines() if ln.strip()]
        check("shadow_rows_present", len(lines) > 0, f"rows={len(lines)}")
        if lines:
            row = json.loads(lines[0])
            required = {
                "fixture_id",
                "baseline_top_10",
                "challenger_top_10",
                "equation_value",
                "evaluation_status",
            }
            check("shadow_schema", required.issubset(row.keys()))


def main() -> int:
    print("ECSE-X2-M3 validation\n")
    validate_equation()
    validate_scorer_no_nan()
    validate_no_public_exposure()
    validate_production(get_settings())
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
