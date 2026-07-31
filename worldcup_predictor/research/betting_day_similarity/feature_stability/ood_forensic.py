"""OOD forensic analysis — research-only, no retune."""

from __future__ import annotations

from typing import Any

import numpy as np


def ood_day_analysis(
    hold_days: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    policy_rows: list[dict[str, Any]],
    *,
    feature_names: list[str],
    train_mean: np.ndarray,
    train_std: np.ndarray,
) -> dict[str, Any]:
    """Investigate OOD days on holdout with evaluation-only outcomes."""
    by_date = {r["vienna_date"]: r for r in policy_rows}
    ood_rows = []
    for day, an in zip(hold_days, analyses):
        ood = an.get("ood") or {}
        level = ood.get("ood_level") or "in_distribution"
        if level == "in_distribution":
            continue
        prow = by_date.get(day["vienna_date"]) or {}
        feats = day.get("features") or {}
        # Features farthest from train mean (z-score)
        triggers = []
        for j, name in enumerate(feature_names):
            v = feats.get(name)
            if v is None or np.isnan(v):
                triggers.append({"feature": name, "reason": "missing", "z": None})
                continue
            std = float(train_std[j]) if float(train_std[j]) > 1e-9 else 1.0
            z = abs((float(v) - float(train_mean[j])) / std)
            if z >= 2.0:
                triggers.append({"feature": name, "reason": "zscore", "z": round(z, 4)})
        triggers.sort(key=lambda x: -(x["z"] or 0))
        base_pnl = float(prow.get("baseline_pnl") or 0)
        overlay_pnl = float(prow.get("overlay_pnl") or 0)
        missed = max(0.0, base_pnl - overlay_pnl) if base_pnl > overlay_pnl else 0.0
        avoided = max(0.0, overlay_pnl - base_pnl) if overlay_pnl > base_pnl else 0.0
        # If OOD skip and baseline was profitable, missed profit = baseline pnl
        if ood.get("ood_level") == "strongly_out_of_distribution" and base_pnl > 0 and overlay_pnl == 0:
            missed = base_pnl
            avoided = 0.0
        if ood.get("ood_level") == "strongly_out_of_distribution" and base_pnl < 0 and overlay_pnl == 0:
            avoided = -base_pnl
            missed = 0.0
        ood_rows.append(
            {
                "vienna_date": day.get("vienna_date"),
                "ood_level": level,
                "ood_reasons": ood.get("reasons"),
                "triggering_features": triggers[:10],
                "nn_distance": an.get("nn_distance") or ood.get("nn_distance"),
                "centroid_distance": ood.get("centroid_distance"),
                "similarity_score": (an.get("similarity") or {}).get("day_similarity_quality_score"),
                "recommendation": (an.get("similarity") or {}).get("recommendation"),
                "regime_id": an.get("regime_id"),
                "baseline_action": day.get("baseline_action"),
                "overlay_action": prow.get("overlay_action"),
                "overlay_day_action": prow.get("overlay_day_action"),
                "baseline_exposure": day.get("baseline_exposure"),
                "overlay_exposure": prow.get("overlay_exposure"),
                "baseline_pnl_evaluation_only": base_pnl,
                "overlay_pnl_evaluation_only": overlay_pnl,
                "profitable_under_baseline": base_pnl > 0,
                "would_betting_have_been_correct": base_pnl > 0,
                "missed_profit_evaluation_only": round(missed, 6),
                "avoided_loss_evaluation_only": round(avoided, 6),
                "ood_justified_heuristic": bool(base_pnl < 0) or bool(triggers[:3]),
            }
        )

    # False OOD classification (evaluation labels only)
    # True OOD: flagged OOD and baseline day losing
    # False OOD: flagged OOD and baseline day profitable
    # False Safe: in-distribution but baseline losing heavily? use: not OOD but should have skipped (baseline loss)
    # Correct Safe: not OOD and baseline non-losing
    tp = fp = tn = fn = 0
    for day, an in zip(hold_days, analyses):
        ood = (an.get("ood") or {}).get("ood_level") != "in_distribution"
        prow = by_date.get(day["vienna_date"]) or {}
        base_pnl = float(prow.get("baseline_pnl") or 0)
        # "should skip" = baseline losing day
        should_skip = base_pnl < 0
        if ood and should_skip:
            tp += 1  # true OOD / correctly skipped hostile
        elif ood and not should_skip:
            fp += 1  # false OOD
        elif (not ood) and (not should_skip):
            tn += 1  # correct safe
        else:
            fn += 1  # false safe

    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    specificity = tn / max(1, tn + fp)
    false_alarm = fp / max(1, tp + fp)

    return {
        "research_only": True,
        "n_ood_days": len(ood_rows),
        "days": ood_rows,
        "false_ood_metrics": {
            "true_ood": tp,
            "false_ood": fp,
            "false_safe": fn,
            "correct_safe": tn,
            "precision": round(precision, 8),
            "recall": round(recall, 8),
            "specificity": round(specificity, 8),
            "false_alarm_rate": round(false_alarm, 8),
            "ood_too_aggressive": false_alarm >= 0.40 or (fp > tp),
            "note": "Labels use baseline-day PnL as hostile proxy; evaluation-only.",
        },
        "total_missed_profit": round(sum(d["missed_profit_evaluation_only"] for d in ood_rows), 6),
        "total_avoided_loss": round(sum(d["avoided_loss_evaluation_only"] for d in ood_rows), 6),
    }
