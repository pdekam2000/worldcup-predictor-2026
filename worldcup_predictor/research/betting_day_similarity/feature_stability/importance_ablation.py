"""Feature importance and ablation forensics — research-only, no deployment."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from worldcup_predictor.research.betting_day_similarity.feature_stability import FEATURE_GROUPS


def estimate_feature_importance(
    feature_names: list[str],
    *,
    instability_ranked: list[dict[str, Any]],
    drift_ranked: list[dict[str, Any]],
    ood_trigger_counts: dict[str, int],
    ablation_delta_roi: dict[str, float] | None = None,
) -> dict[str, Any]:
    inst = {r["feature"]: float(r["instability_score"]) for r in instability_ranked}
    drift = {r["feature"]: float(r["drift_rank_score"]) for r in drift_ranked}
    rows = []
    for name in feature_names:
        ood_c = int(ood_trigger_counts.get(name, 0))
        abl = float((ablation_delta_roi or {}).get(name, 0.0))
        # Higher score = more influential in deterioration / detection
        score = (
            0.30 * inst.get(name, 0.0)
            + 0.30 * drift.get(name, 0.0)
            + 0.25 * (ood_c / max(1.0, max(ood_trigger_counts.values()) if ood_trigger_counts else 1))
            + 0.15 * abs(abl)
        )
        rows.append(
            {
                "feature": name,
                "importance_score": round(score, 8),
                "instability": round(inst.get(name, 0.0), 8),
                "drift": round(drift.get(name, 0.0), 8),
                "ood_trigger_count": ood_c,
                "ablation_roi_delta": round(abl, 8),
            }
        )
    rows.sort(key=lambda r: -r["importance_score"])
    return {
        "research_only": True,
        "ranked": rows,
        "top_for_ood_detection": sorted(rows, key=lambda r: -r["ood_trigger_count"])[:15],
        "top_for_drift": rows[:15],
    }


def _metrics_from_cmp(cmp: dict[str, Any]) -> dict[str, Any]:
    ov = cmp.get("baseline_plus_similarity_overlay") or {}
    base = cmp.get("baseline_portfolio") or {}
    return {
        "overlay_roi": ov.get("roi"),
        "baseline_roi": base.get("roi"),
        "overlay_max_drawdown": ov.get("max_drawdown"),
        "baseline_max_drawdown": base.get("max_drawdown"),
        "overlay_average_exposure": ov.get("average_exposure"),
        "overlay_active_day_ratio": ov.get("active_day_ratio"),
        "ood_proxy": None,
    }


def run_feature_ablation(
    feature_names: list[str],
    *,
    evaluate_subset: Callable[[list[str]], dict[str, Any]],
    max_single_features: int = 24,
) -> dict[str, Any]:
    """
    Ablation: drop one feature / one group, recompute holdout overlay metrics.
    evaluate_subset(feature_list) -> policy comparison dict on holdout.
    """
    baseline = evaluate_subset(feature_names)
    base_m = _metrics_from_cmp(baseline)
    base_roi = base_m["overlay_roi"] if base_m["overlay_roi"] is not None else -9.0

    # Rank candidates by prior instability if available via full set only — take first N features
    singles = []
    for name in feature_names[:max_single_features]:
        subset = [f for f in feature_names if f != name]
        cmp = evaluate_subset(subset)
        m = _metrics_from_cmp(cmp)
        roi = m["overlay_roi"] if m["overlay_roi"] is not None else -9.0
        singles.append(
            {
                "removed_feature": name,
                **m,
                "roi_delta_vs_full": round(roi - base_roi, 8),
                "helps_when_removed": roi > base_roi,
            }
        )
    singles.sort(key=lambda r: -float(r["roi_delta_vs_full"]))

    groups = []
    for gname, members in FEATURE_GROUPS.items():
        drop = set(members)
        subset = [f for f in feature_names if f not in drop]
        if len(subset) < 5:
            continue
        cmp = evaluate_subset(subset)
        m = _metrics_from_cmp(cmp)
        roi = m["overlay_roi"] if m["overlay_roi"] is not None else -9.0
        groups.append(
            {
                "removed_group": gname,
                "removed_count": len([f for f in feature_names if f in drop]),
                **m,
                "roi_delta_vs_full": round(roi - base_roi, 8),
                "helps_when_removed": roi > base_roi,
                "hurts_when_removed": roi < base_roi,
            }
        )
    groups.sort(key=lambda r: -float(r["roi_delta_vs_full"]))

    return {
        "research_only": True,
        "full_feature_baseline": base_m,
        "single_feature_ablation": singles,
        "group_ablation": groups,
        "groups_that_hurt": [g["removed_group"] for g in groups if g["hurts_when_removed"]],
        "groups_that_help_when_removed": [g["removed_group"] for g in groups if g["helps_when_removed"]],
    }


def discover_minimal_feature_set(
    feature_names: list[str],
    importance_ranked: list[dict[str, Any]],
    *,
    evaluate_subset: Callable[[list[str]], dict[str, Any]],
    sizes: tuple[int, ...] = (72, 40, 25, 15, 10),
) -> dict[str, Any]:
    ranked_names = [r["feature"] for r in importance_ranked]
    # Prefer least unstable / most important for retention: importance already ranked high=influential;
    # for minimal stable set keep LOW instability. Re-rank by ascending instability if present.
    # Use reverse of importance for "stable keepers": features with low importance_score that are stable.
    # Spec: smallest stable subset that preserves DD without hurting ROI → keep top-stable (low instability).
    # We'll keep features with lowest instability among importance list by sorting importance ascending for keep set.
    keep_order = list(reversed(ranked_names))  # least important/unstable first as keepers? 
    # Better: importance report has instability — keep features with lowest instability
    keep_order = [
        r["feature"]
        for r in sorted(importance_ranked, key=lambda x: (x.get("instability", 0), x.get("drift", 0)))
    ]

    results = []
    full = evaluate_subset(feature_names)
    full_m = _metrics_from_cmp(full)
    full_roi = full_m["overlay_roi"]
    full_dd = float(full_m["overlay_max_drawdown"] or 0)

    for n in sizes:
        n_eff = min(n, len(feature_names))
        subset = keep_order[:n_eff] if n_eff < len(feature_names) else list(feature_names)
        # Ensure we always include subset of size n_eff from stable order
        if n_eff < len(feature_names):
            subset = keep_order[:n_eff]
        cmp = evaluate_subset(subset)
        m = _metrics_from_cmp(cmp)
        roi = m["overlay_roi"]
        dd = float(m["overlay_max_drawdown"] or 0)
        results.append(
            {
                "feature_count": n_eff,
                "features": subset,
                **m,
                "roi_vs_full_delta": None if roi is None or full_roi is None else round(roi - full_roi, 8),
                "drawdown_vs_full_delta": round(dd - full_dd, 8),
                "preserves_drawdown": dd <= full_dd + 0.25,
                "does_not_hurt_roi": (roi is not None and full_roi is not None and roi >= full_roi - 0.02),
            }
        )

    # Recommend smallest that preserves DD and doesn't hurt ROI much vs FULL overlay
    recommended = None
    for r in sorted(results, key=lambda x: x["feature_count"]):
        if r["preserves_drawdown"] and r["does_not_hurt_roi"]:
            recommended = r
            break
    if recommended is None:
        # fallback: best ROI among reduced sets
        candidates = [r for r in results if r["feature_count"] < len(feature_names)]
        recommended = max(candidates, key=lambda x: (x["overlay_roi"] is not None, x["overlay_roi"] or -9)) if candidates else results[0]

    return {
        "research_only": True,
        "not_deployed": True,
        "sizes_evaluated": results,
        "recommended_minimal": {
            "feature_count": recommended["feature_count"],
            "features": recommended["features"],
            "metrics": {k: recommended[k] for k in recommended if k != "features"},
        },
        "note": "Research candidate only. Does not modify locked Similarity Overlay.",
    }
