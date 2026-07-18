"""Evaluate frozen TSBP predictions against confirmed results (no regeneration)."""

from __future__ import annotations

import math
from typing import Any


def _clip(p: float, eps: float = 1e-15) -> float:
    return min(1 - eps, max(eps, float(p)))


def evaluate_tsbp_freeze(outputs: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """actual: home_goals, away_goals, score, result_1x2, btts (bool), over25 (bool)."""
    out = outputs or {}
    hda = out.get("hda") or {
        "home": out.get("home_probability"),
        "draw": out.get("draw_probability"),
        "away": out.get("away_probability"),
    }
    y = actual.get("result_1x2")
    p_vec = {k: _clip(float(hda.get(k) or 0)) for k in ("home", "draw", "away")}
    z = sum(p_vec.values()) or 1.0
    p_vec = {k: v / z for k, v in p_vec.items()}
    ll_1x2 = -math.log(p_vec.get(y, 1e-15)) if y else None
    brier_1x2 = sum((p_vec[k] - (1.0 if y == k else 0.0)) ** 2 for k in p_vec) if y else None
    # RPS
    rps = None
    if y:
        cum_p = cum_y = 0.0
        rps = 0.0
        for lab in ("home", "draw", "away"):
            cum_p += p_vec[lab]
            cum_y += 1.0 if y == lab else 0.0
            rps += (cum_p - cum_y) ** 2

    btts_y = 1 if actual.get("btts") else 0
    btts_p = _clip(float(out.get("btts_yes") or 0.5))
    ou_y = 1 if actual.get("over25") else 0
    ou_p = _clip(float(out.get("ou25_over") or 0.5))

    score = actual.get("score")
    top10 = [t.get("score") for t in (out.get("top10") or [])]
    top_probs = {t.get("score"): float(t.get("probability") or 0) for t in (out.get("top10") or [])}
    actual_p = top_probs.get(score)
    if actual_p is None:
        used = sum(top_probs.values())
        actual_p = max(1e-15, (1.0 - used) / max(1.0, 64 - len(top_probs)))
    nll = -math.log(_clip(actual_p))

    return {
        "hit_1x2": out.get("decision_1x2") == y,
        "brier_1x2": brier_1x2,
        "logloss_1x2": ll_1x2,
        "rps_1x2": rps,
        "hit_btts": (out.get("btts_selection") == "yes") == bool(actual.get("btts")),
        "brier_btts": (btts_p - btts_y) ** 2,
        "logloss_btts": -(btts_y * math.log(btts_p) + (1 - btts_y) * math.log(1 - btts_p)),
        "hit_ou25": (("over" in str(out.get("ou25_selection"))) and bool(actual.get("over25")))
        or (("under" in str(out.get("ou25_selection"))) and not bool(actual.get("over25"))),
        "brier_ou25": (ou_p - ou_y) ** 2,
        "logloss_ou25": -(ou_y * math.log(ou_p) + (1 - ou_y) * math.log(1 - ou_p)),
        "top1_hit": bool(top10) and top10[0] == score,
        "top3_hit": score in top10[:3],
        "top5_hit": score in top10[:5],
        "top10_hit": score in top10[:10],
        "actual_rank": (top10.index(score) + 1) if score in top10 else "OUTSIDE_TOP10",
        "actual_score_probability": actual_p,
        "exact_score_nll": nll,
        "regenerated": False,
    }


def paired_canonical_comparison(
    canonical_metrics: dict[str, Any] | None,
    tsbp_metrics: dict[str, Any],
) -> dict[str, Any]:
    c = canonical_metrics or {}
    both_1x2 = bool(c.get("hit_1x2")) and bool(tsbp_metrics.get("hit_1x2"))
    only_c = bool(c.get("hit_1x2")) and not bool(tsbp_metrics.get("hit_1x2"))
    only_t = bool(tsbp_metrics.get("hit_1x2")) and not bool(c.get("hit_1x2"))
    neither = not bool(c.get("hit_1x2")) and not bool(tsbp_metrics.get("hit_1x2"))
    return {
        "both_correct_1x2": both_1x2,
        "canonical_only_correct_1x2": only_c,
        "tsbp_only_correct_1x2": only_t,
        "both_wrong_1x2": neither,
        "lower_brier_winner": (
            "tsbp"
            if (tsbp_metrics.get("brier_1x2") is not None and c.get("brier_1x2") is not None and tsbp_metrics["brier_1x2"] < c["brier_1x2"])
            else ("canonical" if c.get("brier_1x2") is not None else "unknown")
        ),
        "lower_logloss_winner": (
            "tsbp"
            if (tsbp_metrics.get("logloss_1x2") is not None and c.get("logloss_1x2") is not None and tsbp_metrics["logloss_1x2"] < c["logloss_1x2"])
            else ("canonical" if c.get("logloss_1x2") is not None else "unknown")
        ),
    }
