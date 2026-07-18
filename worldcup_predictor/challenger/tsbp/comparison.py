"""Extended prematch comparison for TSBP vs canonical."""

from __future__ import annotations

import math
from typing import Any

from worldcup_predictor.challenger.tsbp.constants import SNAPSHOT_PARITY_FAILED

TSBP_CONFLICT_CLASSES = (
    "STRONG_AGREEMENT",
    "MODERATE_AGREEMENT",
    "DIRECTION_CONFLICT",
    "DRAW_CALIBRATION_CONFLICT",
    "TOTAL_GOALS_CONFLICT",
    "SCORE_DISTRIBUTION_CONFLICT",
    "GOAL_MARKET_CONFLICT",
    SNAPSHOT_PARITY_FAILED,
    "INSUFFICIENT_DATA",
)


def _js_divergence(p: dict[str, float], q: dict[str, float]) -> float | None:
    keys = set(p) | set(q)
    if not keys:
        return None

    def _norm(d):
        s = sum(max(0.0, float(d.get(k, 0.0))) for k in keys) or 1.0
        return {k: max(1e-12, float(d.get(k, 0.0)) / s) for k in keys}

    pn, qn = _norm(p), _norm(q)
    m = {k: 0.5 * (pn[k] + qn[k]) for k in keys}

    def _kl(a, b):
        return sum(a[k] * math.log(a[k] / b[k]) for k in keys)

    return 0.5 * _kl(pn, m) + 0.5 * _kl(qn, m)


def _overlap(a: list[str], b: list[str]) -> int:
    return len(set(a) & set(b))


def build_tsbp_prematch_comparison(
    canonical: dict[str, Any],
    tsbp_env: dict[str, Any],
    *,
    snapshot_parity_ok: bool = True,
) -> dict[str, Any]:
    if not snapshot_parity_ok:
        return {
            "conflict_class": SNAPSHOT_PARITY_FAILED,
            "snapshot_parity_ok": False,
            "exclude_from_paired_comparison": True,
        }

    out = tsbp_env.get("output_probabilities") or {}
    c_dir = canonical.get("wde_decision") or canonical.get("decision_1x2")
    t_dir = out.get("decision_1x2") or out.get("predicted_direction")
    c_hda = canonical.get("hda") or {}
    t_hda = out.get("hda") or {
        "home": out.get("home_probability"),
        "draw": out.get("draw_probability"),
        "away": out.get("away_probability"),
    }

    if not c_dir or not t_dir:
        conflict = "INSUFFICIENT_DATA"
    elif c_dir != t_dir:
        conflict = "DIRECTION_CONFLICT"
    else:
        c_draw = float(c_hda.get("draw") or 0)
        t_draw = float(t_hda.get("draw") or 0)
        if abs(c_draw - t_draw) >= 0.12:
            conflict = "DRAW_CALIBRATION_CONFLICT"
        else:
            c_ou = str(canonical.get("ou25") or "").lower()
            t_ou = str(out.get("ou25_selection") or "").lower()
            if c_ou and t_ou and (("over" in c_ou) != ("over" in t_ou)):
                conflict = "TOTAL_GOALS_CONFLICT"
            else:
                c_top1 = str(canonical.get("ecse_top1") or "")
                t_top1 = str(out.get("top1_score") or "")
                if c_top1 and t_top1 and c_top1 != t_top1:
                    conflict = "SCORE_DISTRIBUTION_CONFLICT"
                elif c_top1 and t_top1 and c_top1 == t_top1:
                    conflict = "STRONG_AGREEMENT"
                else:
                    conflict = "MODERATE_AGREEMENT"

    c_scores = list(canonical.get("ecse_top5") or canonical.get("top5_scores") or [])
    if isinstance(c_scores, list) and c_scores and isinstance(c_scores[0], dict):
        c_scores = [x.get("score") for x in c_scores]
    t_top10 = [x.get("score") for x in (out.get("top10") or [])]
    t_top5 = t_top10[:5]
    t_top3 = t_top10[:3]

    # probability distance (L1 on HDA)
    labs = ("home", "draw", "away")
    prob_dist = sum(abs(float(c_hda.get(l) or 0) - float(t_hda.get(l) or 0)) for l in labs)

    c_dist = {str(s): 1.0 / max(1, len(c_scores)) for s in c_scores} if c_scores else {}
    t_dist = {x["score"]: float(x["probability"]) for x in (out.get("top10") or []) if x.get("score")}

    return {
        "conflict_class": conflict,
        "snapshot_parity_ok": True,
        "exclude_from_paired_comparison": False,
        "same_1x2_direction": c_dir == t_dir,
        "probability_distance_l1": round(prob_dist, 6),
        "draw_probability_difference": round(float(t_hda.get("draw") or 0) - float(c_hda.get("draw") or 0), 6),
        "favourite_probability_difference": round(
            max(float(t_hda.get("home") or 0), float(t_hda.get("away") or 0))
            - max(float(c_hda.get("home") or 0), float(c_hda.get("away") or 0)),
            6,
        ),
        "btts_agreement": str(canonical.get("btts") or "").lower() == str(out.get("btts_selection") or "").lower(),
        "ou_agreement": ("over" in str(canonical.get("ou25") or "").lower()) == ("over" in str(out.get("ou25_selection") or "").lower())
        if canonical.get("ou25") and out.get("ou25_selection")
        else None,
        "expected_total_difference": None,  # canonical may not expose λ
        "top1_agreement": str(canonical.get("ecse_top1") or "") == str(out.get("top1_score") or ""),
        "top3_overlap": _overlap([str(x) for x in (c_scores[:3] if c_scores else [])], [str(x) for x in t_top3]),
        "top5_overlap": _overlap([str(x) for x in (c_scores[:5] if c_scores else [])], [str(x) for x in t_top5]),
        "top10_overlap": _overlap([str(x) for x in c_scores], [str(x) for x in t_top10]) if c_scores else None,
        "js_divergence_top_scores": _js_divergence(c_dist, t_dist) if c_dist and t_dist else None,
        "tsbp_entropy": out.get("entropy"),
        "tsbp_draw_score_mass": round(
            sum(float(x["probability"]) for x in (out.get("top10") or []) if x.get("score") in {"0-0", "1-1", "2-2", "3-3"}),
            6,
        ),
        "tsbp_high_score_tail_mass": round(
            sum(
                float(x["probability"])
                for x in (out.get("top10") or [])
                if x.get("score")
                and sum(int(p) for p in str(x["score"]).split("-") if p.isdigit()) >= 4
            ),
            6,
        ),
        "winner_before_result": None,
    }
