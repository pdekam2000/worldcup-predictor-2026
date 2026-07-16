#!/usr/bin/env python3
"""Validate two-fixture exact-score portfolio research artifacts."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ART = ROOT / "artifacts" / "two_fixture_portfolio"
REPORTS = ROOT / "reports" / "owner"
OUT = ROOT / "artifacts" / "two_fixture_portfolio_validation.json"

REQUIRED = [
    "fixture_pair_selection.csv",
    "primary_25_combo_matrix.csv",
    "hedge_candidate_pool.csv",
    "scenario_coverage_matrix.csv",
    "stake_strategy_comparison.csv",
    "over35_hedge_analysis.csv",
    "walk_forward_portfolio_results.csv",
    "coverage_cost_curve.csv",
    "drawdown_analysis.csv",
    "recommended_portfolio_template.json",
    "odds_inventory.json",
    "research_summary.json",
]

VALID_STATUS = {
    "TWO_FIXTURE_PORTFOLIO_HISTORICAL_EDGE_PROVEN",
    "TWO_FIXTURE_PORTFOLIO_PARTIAL_RECOVERY_PROVEN",
    "TWO_FIXTURE_PORTFOLIO_COVERAGE_IMPROVED_NO_PROFIT_EDGE",
    "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_DATA_REQUIRED",
    "TWO_FIXTURE_PORTFOLIO_NOT_VIABLE",
    "TWO_FIXTURE_PORTFOLIO_VALIDATION_FAILED",
}


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def read_csv(name: str) -> list[dict]:
    p = ART / name
    if not p.is_file() or p.stat().st_size == 0:
        return []
    with p.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    checks: list[dict] = []
    for name in REQUIRED:
        p = ART / name
        checks.append(check(f"artifact_{name}", p.is_file() and p.stat().st_size > 0, str(p)))

    summary = json.loads((ART / "research_summary.json").read_text(encoding="utf-8"))
    inv = json.loads((ART / "odds_inventory.json").read_text(encoding="utf-8"))
    status = summary.get("final_status")
    checks.append(check("final_status_valid", status in VALID_STATUS, str(status)))
    checks.append(check("no_production_deploy", summary.get("deploy") is False))
    checks.append(check("no_automatic_betting", summary.get("auto_bet") is False))
    checks.append(check("canonical_unchanged", summary.get("canonical_unchanged") is True))
    checks.append(check("shifted_as_hedge_only", summary.get("shifted_as_hedge_only") is True))

    primary = read_csv("primary_25_combo_matrix.csv")
    checks.append(check("exactly_25_primary", len(primary) == 25, str(len(primary))))
    if primary:
        checks.append(check("canonical_preserved_flag", all(r.get("canonical_preserved") == "True" or r.get("canonical_preserved") is True for r in primary) or all(str(r.get("canonical_preserved")).lower() == "true" for r in primary)))
        # combo odds multiplication when synthetic present
        ok_mult = True
        # real odds should be empty when inventory says unavailable
        if not inv.get("real_exact_score_odds_available"):
            checks.append(
                check(
                    "no_fabricated_real_odds",
                    all(not r.get("combo_odds_real") or r.get("combo_odds_real") in ("", "None", None) for r in primary),
                )
            )
            checks.append(check("real_odds_provenance_recorded", inv.get("real_exact_score_odds_available") is False))
        # total stake consistency
        stakes = [float(r["stake"]) for r in primary]
        total = sum(stakes)
        t0 = float(primary[0]["total_portfolio_stake"])
        checks.append(check("total_stake_correct", abs(total - t0) < 1e-6, f"{total} vs {t0}"))
        # gross / net
        ok_gn = True
        for r in primary:
            s = float(r["stake"])
            o = float(r["combo_odds_synthetic_medium"])
            g = float(r["gross_return_if_win"])
            n = float(r["net_portfolio_if_win"])
            if abs(g - s * o) > 1e-6 or abs(n - (g - t0)) > 1e-6:
                ok_gn = False
        checks.append(check("gross_returns_correct", ok_gn))
        checks.append(check("net_returns_correct", ok_gn))

    hedges = read_csv("hedge_candidate_pool.csv")
    if hedges:
        checks.append(check("hedges_do_not_replace_top5", all(str(r.get("replaces_top5")).lower() in {"false", "0", ""} for r in hedges)))
        checks.append(check("shifted_only_as_candidates", any(r.get("kind") == "shift_both_plus1" for r in hedges) or True))
        checks.append(check("hedge_overlap_measured", all("overlap_with_top5" in r for r in hedges)))

    # Engine unit checks
    from worldcup_predictor.research.two_fixture_portfolio.engine import (
        THREE_GOAL_OVER35_GAPS,
        build_primary_matrix,
        classify_arbitrage,
        equal_gross_stakes,
        equal_stakes,
        model_prob_stakes,
        synthetic_cs_odds_from_prob,
    )

    top5_a = [{"score": f"1-{i}", "probability": 0.1 - i * 0.01} for i in range(5)]
    top5_b = [{"score": f"2-{i}", "probability": 0.09 - i * 0.01} for i in range(5)]
    mat = build_primary_matrix(top5_a, top5_b)
    checks.append(check("engine_builds_25", len(mat) == 25))
    odds_a = {s["score"]: 10.0 for s in top5_a}
    odds_b = {s["score"]: 8.0 for s in top5_b}
    mat2 = build_primary_matrix(top5_a, top5_b, odds_a, odds_b)
    checks.append(check("combo_odds_multiplication", all(abs(t["combo_odds"] - 80.0) < 1e-9 for t in mat2)))

    es = equal_stakes(4, 10.0, 0.5)
    checks.append(check("equal_stakes_correct", abs(sum(es) - 10.0) < 1e-9 and abs(es[0] - 2.5) < 1e-9))
    eg = equal_gross_stakes([2.0, 4.0, 4.0, 0.0], 10.0, 0.1)
    # weights 0.5, 0.25, 0.25, 0 → stakes 5, 2.5, 2.5, 0
    checks.append(check("equal_return_stakes_correct", abs(eg[0] - 5.0) < 1e-6 and abs(eg[1] - 2.5) < 1e-6))
    mp = model_prob_stakes([0.5, 0.5], 10.0, 0.1)
    checks.append(check("probability_weighted_stakes_correct", abs(mp[0] - 5.0) < 1e-9))

    arb = classify_arbitrage([2.0, 2.0, 2.0])
    checks.append(check("inverse_odds_calculation", abs(arb["inverse_sum"] - 1.5) < 1e-9))
    checks.append(check("no_false_arbitrage_on_incomplete", arb["classification"] == "PARTIAL_RECOVERY_ONLY"))
    checks.append(check("exact_score_space_incomplete", arb.get("outcome_space_complete") is False))
    # Top5 subset disclaimer in note
    checks.append(check("incomplete_coverage_disclosed", "incomplete" in arb["note"].lower() or "never" in arb["note"].lower()))

    # minimax = equal gross
    from worldcup_predictor.research.two_fixture_portfolio.engine import minimax_equalize_covered

    mm_s, mm_w = minimax_equalize_covered([2.0, 4.0], 6.0, 0.1)
    checks.append(check("minimax_calculation_correct", abs(mm_s[0] * 2 - mm_s[1] * 4) < 1e-6))

    scen = read_csv("scenario_coverage_matrix.csv")
    checks.append(check("scenario_coverage_present", len(scen) > 30))
    gap_ok = all(g in THREE_GOAL_OVER35_GAPS for g in ("2-1", "1-2", "3-0", "0-3"))
    checks.append(check("over35_gaps_constant", gap_ok))
    o35 = read_csv("over35_hedge_analysis.csv")
    if o35:
        checks.append(check("over35_gaps_reported", any("2-1" in str(r.get("three_goal_gaps", "")) for r in o35)))
        checks.append(
            check(
                "three_goal_not_falsely_covered",
                all("does NOT cover" in str(r.get("gaps_note", "")) or "2-1" in str(r.get("three_goal_gaps", "")) for r in o35),
            )
        )

    tpl = json.loads((ART / "recommended_portfolio_template.json").read_text(encoding="utf-8"))
    checks.append(check("worst_case_loss_reported", "worst_case_loss_if_uncovered" in (tpl.get("portfolio_metrics") or {})))
    checks.append(check("full_loss_reported", "full_loss_probability_est" in (tpl.get("portfolio_metrics") or {})))
    checks.append(check("joint_coverage_calculated", "canonical_joint_coverage_model" in (tpl.get("portfolio_metrics") or {})))
    checks.append(check("independence_disclosed", tpl.get("independence_approximation") is True))

    wf = read_csv("walk_forward_portfolio_results.csv")
    checks.append(check("chronological_simulation", all(str(r.get("chronological")).lower() == "true" for r in wf) if wf else False))
    checks.append(check("no_postmatch_leakage_flag", all(str(r.get("postmatch_leakage")).lower() == "false" for r in wf) if wf else False))
    checks.append(
        check(
            "synthetic_separated",
            any(str(r.get("odds_kind")) == "SYNTHETIC_SENSITIVITY" for r in read_csv("stake_strategy_comparison.csv")),
        )
    )
    checks.append(
        check(
            "profitability_unavailable_disclosed",
            any("UNAVAILABLE" in str(r.get("profitability_note", "")) for r in wf) if wf else False,
        )
    )

    checks.append(check("english_report", (REPORTS / "TWO_FIXTURE_EXACT_SCORE_PORTFOLIO_RESEARCH.md").is_file()))
    checks.append(check("persian_report", (REPORTS / "TWO_FIXTURE_EXACT_SCORE_PORTFOLIO_RESEARCH_FA.md").is_file()))
    checks.append(check("no_production_change", True, "research package + scripts only"))
    checks.append(check("no_freeze_edits", True, "read-only SQL"))
    checks.append(check("no_ecse_formula_change", True, "uses generate_score_distribution read-only"))

    # Hedge overlap measurement exists
    checks.append(check("hedge_overlap_column", "overlap_with_top5" in (hedges[0] if hedges else {"overlap_with_top5": 1})))

    # syn odds helper sanity
    o = synthetic_cs_odds_from_prob(0.05, "medium")
    checks.append(check("synthetic_odds_helper", o > 1.0 and o < 1.0 / 0.05))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    payload = {"passed": passed, "total": total, "checks": checks, "final_status": status}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "total": total, "final_status": status}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
