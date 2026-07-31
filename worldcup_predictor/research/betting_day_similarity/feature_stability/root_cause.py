"""Component contribution and failure root-cause attribution — research-only."""

from __future__ import annotations

from typing import Any, Callable


def component_contribution(
    *,
    evaluate_variant: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """
    Replay variants:
      full_overlay | no_ood | no_regime | no_similarity_score | baseline_only
    evaluate_variant(name) -> metrics dict with overlay/baseline fields.
    """
    variants = ["baseline_only", "full_overlay", "no_ood", "no_regime", "no_similarity_score"]
    results = {}
    for v in variants:
        results[v] = evaluate_variant(v)

    full = results["full_overlay"]
    base = results["baseline_only"]
    no_ood = results["no_ood"]
    no_reg = results["no_regime"]
    no_sim = results["no_similarity_score"]

    def roi(d: dict[str, Any]) -> float:
        r = d.get("roi")
        return float(r) if r is not None else -9.0

    attributions = {
        "ood_filtering_roi_impact": round(roi(full) - roi(no_ood), 8),
        "regime_filtering_roi_impact": round(roi(full) - roi(no_reg), 8),
        "similarity_score_roi_impact": round(roi(full) - roi(no_sim), 8),
        "full_overlay_vs_baseline_roi": round(roi(full) - roi(base), 8),
        "ood_filtering_dd_impact": round(
            float(full.get("max_drawdown") or 0) - float(no_ood.get("max_drawdown") or 0), 8
        ),
        "full_overlay_vs_baseline_dd": round(
            float(full.get("max_drawdown") or 0) - float(base.get("max_drawdown") or 0), 8
        ),
    }
    return {
        "research_only": True,
        "variants": results,
        "attributions": attributions,
        "interpretation": {
            "negative_ood_roi_impact_means_ood_hurts_roi": attributions["ood_filtering_roi_impact"] < 0,
            "capital_reduction_primary": abs(attributions["full_overlay_vs_baseline_roi"]) > 0.05,
        },
    }


def failure_root_cause(
    *,
    false_ood: dict[str, Any],
    component: dict[str, Any],
    drift: dict[str, Any],
    stability: dict[str, Any],
    ablation: dict[str, Any],
    holdout_cmp: dict[str, Any],
) -> dict[str, Any]:
    causes = []
    fo = false_ood.get("false_ood_metrics") or {}
    attr = component.get("attributions") or {}

    missed = float(false_ood.get("total_missed_profit") or 0)
    avoided = float(false_ood.get("total_avoided_loss") or 0)
    fp = int(fo.get("false_ood") or 0)
    tp = int(fo.get("true_ood") or 0)

    causes.append(
        {
            "cause": "Too many false OOD / skipped profitable days",
            "impact_score": round(missed + 10.0 * fp, 4),
            "evidence": {
                "false_ood": fp,
                "true_ood": tp,
                "false_alarm_rate": fo.get("false_alarm_rate"),
                "missed_profit": missed,
                "avoided_loss": avoided,
            },
        }
    )
    causes.append(
        {
            "cause": "OOD filtering ROI drag",
            "impact_score": round(abs(min(0.0, float(attr.get("ood_filtering_roi_impact") or 0))) * 100, 4),
            "evidence": {"ood_filtering_roi_impact": attr.get("ood_filtering_roi_impact")},
        }
    )
    causes.append(
        {
            "cause": "Capital reduction / over-restrictive overlay",
            "impact_score": round(abs(min(0.0, float(attr.get("full_overlay_vs_baseline_roi") or 0))) * 100, 4),
            "evidence": {
                "full_overlay_vs_baseline_roi": attr.get("full_overlay_vs_baseline_roi"),
                "baseline_roi": (holdout_cmp.get("baseline_portfolio") or {}).get("roi"),
                "overlay_roi": (holdout_cmp.get("baseline_plus_similarity_overlay") or {}).get("roi"),
                "baseline_exposure": (holdout_cmp.get("baseline_portfolio") or {}).get("average_exposure"),
                "overlay_exposure": (holdout_cmp.get("baseline_plus_similarity_overlay") or {}).get("average_exposure"),
            },
        }
    )
    top_drift = (drift.get("top_drifted") or [])[:5]
    causes.append(
        {
            "cause": "Feature distribution drift (train→holdout)",
            "impact_score": round(20.0 + 2.0 * len(top_drift), 4),
            "evidence": {"top_drifted_features": top_drift},
        }
    )
    top_unstable = (stability.get("top_unstable") or [])[:5]
    causes.append(
        {
            "cause": "Poor feature stability",
            "impact_score": round(15.0 + float(stability.get("ranked_by_instability", [{}])[0].get("instability_score", 0) if stability.get("ranked_by_instability") else 0), 4),
            "evidence": {"top_unstable_features": top_unstable},
        }
    )
    hurt_groups = ablation.get("groups_that_help_when_removed") or []
    causes.append(
        {
            "cause": "Noisy feature groups hurting overlay",
            "impact_score": round(8.0 * len(hurt_groups), 4),
            "evidence": {"groups_help_when_removed": hurt_groups},
        }
    )
    causes.append(
        {
            "cause": "Regime instability / coarse regime count",
            "impact_score": 12.0,
            "evidence": {"note": "Locked regime count=3; forensic checks silhouette/stability separately"},
        }
    )
    causes.append(
        {
            "cause": "Small analog count / over-sensitive similarity",
            "impact_score": round(abs(min(0.0, float(attr.get("similarity_score_roi_impact") or 0))) * 80, 4),
            "evidence": {"similarity_score_roi_impact": attr.get("similarity_score_roi_impact")},
        }
    )

    causes.sort(key=lambda c: -float(c["impact_score"]))
    primary = causes[0] if causes else {"cause": "unknown"}

    recommendations = [
        {
            "priority": "Very high priority",
            "recommendation": "Recalibrate OOD detector to reduce false alarms on profitable days",
            "expected_impact": "High — recover missed profit without giving back all DD gains",
            "expected_risk": "Medium — may reintroduce some losing days",
            "implementation_complexity": "Medium",
            "do_not_implement_in_this_phase": True,
        },
        {
            "priority": "High priority",
            "recommendation": "Shrink to a stable minimal feature subset (remove high-drift groups first)",
            "expected_impact": "Medium/High — may preserve DD with less ROI damage",
            "expected_risk": "Low/Medium",
            "implementation_complexity": "Medium",
            "do_not_implement_in_this_phase": True,
        },
        {
            "priority": "High priority",
            "recommendation": "Separate exposure reduction from hard OOD skips",
            "expected_impact": "High — keep risk control without zeroing profitable days",
            "expected_risk": "Medium",
            "implementation_complexity": "Medium",
            "do_not_implement_in_this_phase": True,
        },
        {
            "priority": "Medium priority",
            "recommendation": "Revisit regime count / stability with train-only silhouette constraints",
            "expected_impact": "Medium",
            "expected_risk": "Low",
            "implementation_complexity": "Low",
            "do_not_implement_in_this_phase": True,
        },
        {
            "priority": "Low priority",
            "recommendation": "Re-audit cosine vs mixed after feature pruning (do not retune yet)",
            "expected_impact": "Low/Medium",
            "expected_risk": "Low",
            "implementation_complexity": "Low",
            "do_not_implement_in_this_phase": True,
        },
    ]

    return {
        "research_only": True,
        "ranked_causes": causes,
        "primary_root_cause": primary.get("cause"),
        "recommendations": recommendations,
        "not_implemented": True,
    }
