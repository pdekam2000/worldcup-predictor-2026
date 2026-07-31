"""WATCH_POSITIVE vs WATCH_REJECT split research — prematch-only classification."""

from __future__ import annotations

import copy
from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import BASELINE_POLICY
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.metrics import summarize_days
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
    replay_all_days,
)


def research_watch_split(
    fixtures_train: list[dict[str, Any]],
    fixtures_val: list[dict[str, Any]],
    *,
    base_policy: dict[str, Any] | None = None,
    ratios: tuple[float, ...] = (0.05, 0.10, 0.15, 0.20),
) -> dict[str, Any]:
    """
    Classify WATCH days into POSITIVE / REJECT using prematch gates only.
    Micro-allocation ratios tested on validation for selection; train for generation.
    """
    pol0 = copy.deepcopy(base_policy or BASELINE_POLICY)
    # Force micro off first to identify WATCH pool under baseline-like thresholds
    pol0["watch_micro_allocation_ratio"] = 0.0

    train_by_ratio = []
    val_by_ratio = []
    for r in ratios:
        pol_t = copy.deepcopy(pol0)
        pol_t["watch_micro_allocation_ratio"] = float(r)
        pol_t["watch_positive_score_slack"] = 6.0
        td = replay_all_days(fixtures_train, policy=pol_t)
        tm = summarize_days(td)
        pos_t = [d for d in td if d.get("action") == "WATCH_POSITIVE"]
        rej_t = [d for d in td if d.get("action") == "WATCH_NO_CAPITAL"]
        train_by_ratio.append(
            {
                "WATCH_POSITIVE_count": len(pos_t),
                "WATCH_REJECT_count": len(rej_t),
                "allocation_ratio_tested": r,
                "roi": tm.get("roi"),
                "max_drawdown": tm.get("max_drawdown"),
                "average_exposure": tm.get("average_exposure"),
                "profitable_WATCH_POSITIVE_rate": round(
                    sum(1 for d in pos_t if float(d.get("realized_pnl_evaluation_only") or 0) > 0)
                    / max(1, len(pos_t)),
                    6,
                ),
                "losing_WATCH_POSITIVE_rate": round(
                    sum(1 for d in pos_t if float(d.get("realized_pnl_evaluation_only") or 0) < 0)
                    / max(1, len(pos_t)),
                    6,
                ),
            }
        )
        pol_v = copy.deepcopy(pol0)
        pol_v["watch_micro_allocation_ratio"] = float(r)
        pol_v["watch_positive_score_slack"] = 6.0
        vd = replay_all_days(fixtures_val, policy=pol_v)
        vm = summarize_days(vd)
        pos_v = [d for d in vd if d.get("action") == "WATCH_POSITIVE"]
        rej_v = [d for d in vd if d.get("action") == "WATCH_NO_CAPITAL"]
        val_by_ratio.append(
            {
                "WATCH_POSITIVE_count": len(pos_v),
                "WATCH_REJECT_count": len(rej_v),
                "allocation_ratio_tested": r,
                "roi": vm.get("roi"),
                "max_drawdown": vm.get("max_drawdown"),
                "average_exposure": vm.get("average_exposure"),
                "active_day_ratio": vm.get("active_day_ratio"),
                "profitable_WATCH_POSITIVE_rate": round(
                    sum(1 for d in pos_v if float(d.get("realized_pnl_evaluation_only") or 0) > 0)
                    / max(1, len(pos_v)),
                    6,
                ),
                "losing_WATCH_POSITIVE_rate": round(
                    sum(1 for d in pos_v if float(d.get("realized_pnl_evaluation_only") or 0) < 0)
                    / max(1, len(pos_v)),
                    6,
                ),
                "validation_rank_proxy": round(
                    float(vm.get("roi") or -1)
                    - 0.01 * float(vm.get("max_drawdown") or 0)
                    + 0.05 * float(vm.get("active_day_ratio") or 0),
                    8,
                ),
            }
        )

    best = max(val_by_ratio, key=lambda x: float(x.get("validation_rank_proxy") or -9e9))
    locked_ratio = float(best["allocation_ratio_tested"])

    # Full-pool counts under locked ratio on train+val (not holdout)
    pol_locked = copy.deepcopy(pol0)
    pol_locked["watch_micro_allocation_ratio"] = locked_ratio
    combined = list(fixtures_train) + list(fixtures_val)
    cd = replay_all_days(combined, policy=pol_locked)

    return {
        "research_only": True,
        "classification_uses_prematch_only": True,
        "results_not_used_for_classification": True,
        "ratios_tested": list(ratios),
        "by_ratio_training": train_by_ratio,
        "by_ratio_validation": val_by_ratio,
        "ROI_by_ratio": {str(x["allocation_ratio_tested"]): x.get("roi") for x in val_by_ratio},
        "drawdown_by_ratio": {str(x["allocation_ratio_tested"]): x.get("max_drawdown") for x in val_by_ratio},
        "exposure_by_ratio": {str(x["allocation_ratio_tested"]): x.get("average_exposure") for x in val_by_ratio},
        "best_ratio_on_validation": locked_ratio,
        "final_locked_ratio": locked_ratio,
        "WATCH_POSITIVE_count": sum(1 for d in cd if d.get("action") == "WATCH_POSITIVE"),
        "WATCH_REJECT_count": sum(1 for d in cd if d.get("action") == "WATCH_NO_CAPITAL"),
        "WATCH_POSITIVE_rules": {
            "score_near_SMALL_BET": "score >= SMALL_BET - slack",
            "slack": 6.0,
            "residual_risk_ok": "low_residual_risk >= 45",
            "insurance_contribution_ok": ">= 10",
            "league_reliability_ok": ">= 40",
            "correlation_ok": "not over_concentrated",
            "eligible_fixtures": ">= 1",
            "hard_gate_failures": "<= 1",
        },
        "WATCH_REJECT_rules": {
            "zero_capital": True,
            "applies_when": "WATCH_NO_CAPITAL and not WATCH_POSITIVE criteria",
        },
    }
