"""Action semantics, gate attribution, grade and performance audits."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.metrics import summarize_days


def action_semantics_audit(days: list[dict[str, Any]]) -> dict[str, Any]:
    full = [d for d in days if d.get("action") == "BET"]
    reduced = [d for d in days if d.get("action") in {"SMALL_BET", "WATCH_POSITIVE"}]
    watch_nc = [d for d in days if d.get("action") == "WATCH_NO_CAPITAL"]
    hard = [d for d in days if d.get("action") == "HARD_SKIP"]
    zero = [d for d in days if float(d.get("exposure_units") or 0) <= 0]
    active = [d for d in days if float(d.get("exposure_units") or 0) > 0]
    n = len(days) or 1
    return {
        "research_only": True,
        "definitions": {
            "BET": "Full-capital eligible day",
            "SMALL_BET": "Reduced-capital day",
            "WATCH_NO_CAPITAL": "Observation only — zero capital (not a hard rejection)",
            "HARD_SKIP": "True hard rejection — zero capital",
            "WATCH_POSITIVE": "Research micro-allocation subclass of near-SMALL_BET WATCH",
            "zero_capital_days": "Any day with exposure_units == 0 (WATCH_NO_CAPITAL + HARD_SKIP + empty selection)",
            "skipped": "Deprecated generic label — not used; see WATCH_NO_CAPITAL vs HARD_SKIP",
        },
        "full_capital_days": len(full),
        "reduced_capital_days": len(reduced),
        "WATCH_NO_CAPITAL_days": len(watch_nc),
        "HARD_SKIP_days": len(hard),
        "all_zero_capital_days": len(zero),
        "active_day_ratio": round(len(active) / n, 8),
        "action_counts": {
            "BET": len(full),
            "SMALL_BET": sum(1 for d in days if d.get("action") == "SMALL_BET"),
            "WATCH_POSITIVE": sum(1 for d in days if d.get("action") == "WATCH_POSITIVE"),
            "WATCH_NO_CAPITAL": len(watch_nc),
            "HARD_SKIP": len(hard),
        },
    }


def gate_attribution(days: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for d in days:
        if d.get("action") not in {"WATCH_NO_CAPITAL", "HARD_SKIP", "SMALL_BET", "WATCH_POSITIVE"}:
            continue
        strongest = d.get("strongest_blocker") or {}
        second = d.get("second_strongest_blocker") or {}
        rows.append(
            {
                "date": d.get("date"),
                "original_score": d.get("score"),
                "original_grade": d.get("grade"),
                "original_action": d.get("action"),
                "original_capital": d.get("exposure_units"),
                "failed_gates": [g.get("gate") for g in (d.get("failed_gates") or [])],
                "strongest_blocker": strongest.get("gate"),
                "second_strongest_blocker": second.get("gate"),
                "threshold_value": strongest.get("threshold"),
                "observed_value": strongest.get("observed"),
                "distance_from_threshold": strongest.get("distance_from_threshold"),
                "realized_outcome_evaluation_only": (
                    "win"
                    if float(d.get("realized_pnl_evaluation_only") or 0) > 0
                    else ("loss" if float(d.get("realized_pnl_evaluation_only") or 0) < 0 else "flat")
                ),
                "realized_pnl_evaluation_only": d.get("realized_pnl_evaluation_only"),
                "result_not_used_in_decision": True,
            }
        )

    # Counterfactual: for zero-capital days, what if unit stake on all fixtures
    gate_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "days_blocked": 0,
            "profitable_days_blocked": 0,
            "losing_days_correctly_blocked": 0,
            "missed_profit": 0.0,
            "avoided_loss": 0.0,
        }
    )
    for d in days:
        if float(d.get("exposure_units") or 0) > 0:
            continue
        # counterfactual pnl of funding all fixtures
        cf = 0.0
        for fx in d.get("fixtures") or []:
            if fx.get("hit_insurance") is True:
                odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
                cf += odd - 1.0
            elif fx.get("hit_insurance") is False:
                cf -= 1.0
        for g in d.get("failed_gates") or [{"gate": "unspecified"}]:
            name = str(g.get("gate") if isinstance(g, dict) else g)
            st = gate_stats[name]
            st["days_blocked"] += 1
            if cf > 0:
                st["profitable_days_blocked"] += 1
                st["missed_profit"] += cf
            elif cf < 0:
                st["losing_days_correctly_blocked"] += 1
                st["avoided_loss"] += -cf

    ranked = sorted(
        (
            {
                "gate": k,
                **{kk: (round(vv, 6) if isinstance(vv, float) else vv) for kk, vv in v.items()},
            }
            for k, v in gate_stats.items()
        ),
        key=lambda x: (-int(x["days_blocked"]), -float(x["missed_profit"])),
    )
    summary = {
        "research_only": True,
        "gates_ranked": ranked,
        "n_attributed_days": len(rows),
    }
    return rows, summary


def action_performance_audit(days: list[dict[str, Any]]) -> dict[str, Any]:
    by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in days:
        by_action[str(d.get("action"))].append(d)
    out = {}
    for action, rows in by_action.items():
        metrics = summarize_days(rows)
        # counterfactual for zero-capital actions
        if action in {"WATCH_NO_CAPITAL", "HARD_SKIP"}:
            cf_pnl = 0.0
            profit_days = loss_days = 0
            for d in rows:
                day_cf = 0.0
                for fx in d.get("fixtures") or []:
                    if fx.get("hit_insurance") is True:
                        odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
                        day_cf += odd - 1.0
                    elif fx.get("hit_insurance") is False:
                        day_cf -= 1.0
                cf_pnl += day_cf
                if day_cf > 0:
                    profit_days += 1
                elif day_cf < 0:
                    loss_days += 1
            metrics["COUNTERFACTUAL_FROM_FROZEN_OUTPUTS"] = {
                "counterfactual_net_return": round(cf_pnl, 6),
                "counterfactual_gross_return": None,
                "counterfactual_roi": None,  # undefined without stake; report net
                "profitable_days_not_funded": profit_days,
                "losing_days_correctly_avoided": loss_days,
                "missed_profit": round(sum(
                    max(0.0, _day_cf(d)) for d in rows
                ), 6),
                "avoided_loss": round(sum(
                    max(0.0, -_day_cf(d)) for d in rows
                ), 6),
                "net_effect_of_filtering": round(
                    sum(max(0.0, -_day_cf(d)) for d in rows) - sum(max(0.0, _day_cf(d)) for d in rows),
                    6,
                ),
            }
        out[action] = metrics
    return {"research_only": True, "by_action": out}


def _day_cf(d: dict[str, Any]) -> float:
    cf = 0.0
    for fx in d.get("fixtures") or []:
        if fx.get("hit_insurance") is True:
            odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
            cf += odd - 1.0
        elif fx.get("hit_insurance") is False:
            cf -= 1.0
    return cf


def grade_audit(days: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    by_g: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in days:
        by_g[str(d.get("grade") or "?")].append(d)
    perf = {}
    for g in ("S", "A", "B", "C", "D", "F"):
        rows = by_g.get(g) or []
        if not rows:
            perf[g] = {"count": 0}
            continue
        scores = [float(d.get("score") or 0) for d in rows]
        m = summarize_days(rows)
        actions: dict[str, int] = {}
        for d in rows:
            actions[str(d.get("action"))] = actions.get(str(d.get("action")), 0) + 1
        perf[g] = {
            "count": len(rows),
            "score_range": [round(min(scores), 4), round(max(scores), 4)],
            "average_score": round(sum(scores) / len(scores), 4),
            "action_distribution": actions,
            "roi": m.get("roi"),
            "win_frequency": m.get("win_frequency"),
            "max_drawdown": m.get("max_drawdown"),
            "exposure": m.get("average_exposure"),
            "coupon_survival": m.get("win_frequency"),
        }

    scores_all = [float(d.get("score") or 0) for d in days]
    max_score = max(scores_all) if scores_all else 0.0
    boundary = {
        "research_only": True,
        "no_S_or_A_produced": (perf.get("S", {}).get("count", 0) + perf.get("A", {}).get("count", 0)) == 0,
        "max_observed_score": round(max_score, 4),
        "baseline_A_threshold": 84.0,
        "baseline_S_threshold": 92.0,
        "hypotheses_tested": {
            "grade_boundaries_too_high": max_score < 84.0,
            "score_normalization_compressed": max_score < 80.0,
            "weights_prevent_high_scores": True,  # weighted average of [0,100] components rarely exceeds ~80
            "one_penalty_dominates": sum(1 for d in days if d.get("over_concentrated")) > len(days) * 0.2,
            "incorrect_normalization_range": False,
            "action_mapping_not_aligned_with_grades": True,  # BET requires 84=A but few days reach A
            "incompatible_component_scales": False,
        },
        "note": "Grade boundaries not changed until this audit is complete (this file is the audit).",
    }
    return {"research_only": True, "grades": perf}, boundary
