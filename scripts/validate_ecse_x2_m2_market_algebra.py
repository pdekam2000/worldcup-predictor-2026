#!/usr/bin/env python3
"""Validate PHASE ECSE-X2-M2 market algebra miner."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_score_distribution import PROB_SUM_TOLERANCE, generate_score_distribution
from worldcup_predictor.research.ecse_x2_m2.build import baseline_table_row_count
from worldcup_predictor.research.ecse_x2_m2.equations import CANDIDATE_EQUATIONS, compute_equation
from worldcup_predictor.research.ecse_x2_m2.prob_features import build_prob_map
from worldcup_predictor.research.ecse_x2_m2.reorder import apply_reorder, learn_lift_table, quantile_boundaries

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def validate_equations() -> None:
    probs = {
        "ft_home": 0.45,
        "ft_away": 0.30,
        "ft_draw": 0.25,
        "draw_proxy": 0.25,
        "btts_yes": 0.55,
        "btts_no": 0.45,
        "ou_over_25": 0.52,
        "ou_under_25": 0.48,
        "ou_over_15": 0.72,
        "ou_under_35": 0.65,
        "team_home_over_15": 0.40,
        "team_away_over_05": 0.70,
        "corner_over_85": 0.60,
        "fh_draw": 0.42,
        "fh_home": 0.33,
        "corner_over_95": 0.45,
    }
    ok_count = 0
    for spec in CANDIDATE_EQUATIONS:
        if compute_equation(spec, probs) is not None:
            ok_count += 1
    check("candidate_equations_compute", ok_count >= 15, f"ok={ok_count}/{len(CANDIDATE_EQUATIONS)}")


def validate_reorder_normalization() -> None:
    dist = [
        {
            "scoreline": e["scoreline"],
            "home_goals": e["home_goals"],
            "away_goals": e["away_goals"],
            "probability": e["probability"],
            "rank": e["rank"],
        }
        for e in generate_score_distribution(1.3, 1.0)
    ]
    train = [
        {"value": 0.2, "actual": "1-1", "actual_cluster": "drawish"},
        {"value": 0.5, "actual": "2-1", "actual_cluster": "home_win"},
        {"value": 0.8, "actual": "1-0", "actual_cluster": "home_win"},
    ] * 40
    model = learn_lift_table(train)
    out = apply_reorder(dist, value=0.5, model=model)
    total = sum(float(r["probability"]) for r in out)
    check("reorder_probs_sum", abs(total - 1.0) <= PROB_SUM_TOLERANCE, f"sum={total}")


def validate_no_baseline_writes() -> None:
    miner_text = (ROOT / "worldcup_predictor/research/ecse_x2_m2/miner.py").read_text(encoding="utf-8")
    check("miner_no_delete_baseline", "DELETE FROM ecse_score_distributions" not in miner_text)


def validate_production(settings) -> None:
    conn = connect(get_db_path(settings.sqlite_path))
    try:
        n = baseline_table_row_count(conn)
        check("baseline_populated", n > 0, f"rows={n}")
        summary = ROOT / "artifacts" / "ecse_x2_m2_equation_rankings.json"
        report = ROOT / "ECSE_X2_M2_MARKET_ALGEBRA_REPORT.md"
        check("summary_artifact", summary.is_file())
        check("report_artifact", report.is_file())
        if summary.is_file():
            payload = json.loads(summary.read_text(encoding="utf-8"))
            check("summary_phase", payload.get("phase") == "ECSE-X2-M2")
            check("top_equations_present", len(payload.get("top_equations") or []) > 0)
    finally:
        conn.close()


def main() -> int:
    print("ECSE-X2-M2 validation\n")
    validate_equations()
    validate_reorder_normalization()
    validate_no_baseline_writes()
    db = get_db_path(get_settings().sqlite_path)
    if db.exists():
        validate_production(get_settings())
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
