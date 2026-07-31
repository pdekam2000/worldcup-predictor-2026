"""Promotion readiness score (research-only)."""

from __future__ import annotations

from typing import Any


def compute_readiness_score(
    *,
    historical: dict[str, Any],
    league: dict[str, Any],
    market: dict[str, Any],
    calibration: dict[str, Any],
    forward: dict[str, Any],
    robustness: dict[str, Any],
    n_fixtures: int,
    min_fixtures: int = 1000,
) -> dict[str, Any]:
    components: dict[str, dict[str, Any]] = {}

    # Historical evidence (0-25)
    cf = historical.get("complete_coupon_failure") or {}
    sig = historical.get("statistical_significance") or {}
    hist_score = 0.0
    if n_fixtures >= min_fixtures:
        hist_score += 8
    if cf.get("insurance_reduces_complete_failure"):
        hist_score += 8
    if historical.get("main_plus_insurance_outperforms_main"):
        hist_score += 5
    if sig.get("significant_at_0_05"):
        hist_score += 4
    components["historical_evidence"] = {"score": hist_score, "max": 25}

    # Forward evidence (0-20)
    fwd_score = 0.0
    n_days = int(forward.get("n_forward_days") or 0)
    if n_days >= 7:
        fwd_score += 6
    if n_days >= 14:
        fwd_score += 4
    if forward.get("forward_evidence_sufficient"):
        fwd_score += 10
    components["forward_evidence"] = {"score": fwd_score, "max": 20}

    # Market stability (0-15)
    fams = market.get("families_ranked") or []
    mkt_score = 0.0
    if fams:
        mkt_score += 5
        top = fams[0]
        if float(top.get("rescue_frequency") or 0) > 0:
            mkt_score += 5
        if top.get("roi") is not None:
            mkt_score += 5
    components["market_stability"] = {"score": mkt_score, "max": 15}

    # League consistency (0-15)
    leagues = league.get("leagues_ranked") or []
    hurts = set(league.get("leagues_where_insurance_hurts") or [])
    lg_score = 0.0
    if len(leagues) >= 3:
        lg_score += 5
    if leagues:
        help_frac = sum(1 for r in leagues if not r.get("insurance_hurts_performance")) / len(leagues)
        lg_score += 10 * help_frac
    components["league_consistency"] = {
        "score": round(lg_score, 2),
        "max": 15,
        "help_fraction": round(1 - len(hurts) / max(1, len(leagues)), 4),
    }

    # Calibration (0-10)
    cal_score = 0.0
    if calibration.get("higher_confidence_better") is True:
        cal_score += 6
    elif calibration.get("higher_confidence_better") is False:
        cal_score += 1
    else:
        cal_score += 3
    ce = (historical.get("calibration_error") or {}).get("exact3_main_insurance")
    if ce is not None and ce < 0.15:
        cal_score += 4
    elif ce is not None:
        cal_score += 2
    components["calibration"] = {"score": cal_score, "max": 10}

    # ROI stability (0-10)
    priced = historical.get("priced_subset_analysis") or {}
    roi_score = 0.0
    if priced.get("n", 0) >= 50:
        roi_score += 4
    roi = priced.get("roi")
    if roi is not None and roi > -0.25:
        roi_score += 3
    if priced.get("profit_factor") and float(priced["profit_factor"] or 0) >= 0.8:
        roi_score += 3
    components["roi_stability"] = {"score": roi_score, "max": 10}

    # Risk reduction (0-5)
    risk_score = 0.0
    if cf.get("insurance_reduces_complete_failure"):
        risk_score += 3
    if int(cf.get("insurance_rescue_count") or 0) > 0:
        risk_score += 2
    components["risk_reduction"] = {"score": risk_score, "max": 5}

    # Robustness bonus folded into market stability already; gate separately
    robust_ok = bool(robustness.get("robust_to_incomplete_markets"))

    total = round(sum(float(c["score"]) for c in components.values()), 2)
    gates = {
        "main_plus_insurance_outperforms_main": bool(historical.get("main_plus_insurance_outperforms_main")),
        "failure_reduction": bool(cf.get("insurance_reduces_complete_failure")),
        "enough_fixtures": n_fixtures >= min_fixtures,
        "generalizes_across_leagues": components["league_consistency"]["help_fraction"] >= 0.6,
        "forward_evidence": bool(forward.get("forward_evidence_sufficient")),
        "robust_incomplete_markets": robust_ok,
        "stat_significant": bool(sig.get("significant_at_0_05")),
    }

    if total >= 75 and all(
        gates[k]
        for k in (
            "main_plus_insurance_outperforms_main",
            "failure_reduction",
            "enough_fixtures",
            "generalizes_across_leagues",
            "robust_incomplete_markets",
        )
    ) and (gates["forward_evidence"] or gates["stat_significant"]):
        recommendation = "GO"
    elif total >= 40 and gates["enough_fixtures"] and gates["main_plus_insurance_outperforms_main"]:
        recommendation = "HOLD"
    else:
        recommendation = "RESEARCH MORE"

    # Explicit override: insufficient forward evidence → cannot GO
    if recommendation == "GO" and not gates["forward_evidence"]:
        recommendation = "HOLD"
        reason_override = "Forward shadow evidence insufficient for Owner Shadow deployment."
    else:
        reason_override = None

    return {
        "research_only": True,
        "owner_only": True,
        "readiness_score": total,
        "max_score": 100,
        "components": components,
        "gates": gates,
        "recommendation": recommendation,
        "reason_override": reason_override,
        "warnings": [
            w
            for w in [
                reason_override,
                "Research-only. Not deployed.",
                "No profit guarantee.",
                None if gates["forward_evidence"] else "Forward evidence thin — prefer HOLD.",
            ]
            if w
        ],
    }
