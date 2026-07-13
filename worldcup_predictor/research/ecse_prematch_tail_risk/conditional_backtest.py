"""Conditional tail correction backtest — detector routes, not actual labels."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from worldcup_predictor.research.ecse_prematch_tail_risk.constants import TIER_HIGH, TIER_VERY_HIGH
from worldcup_predictor.research.ecse_prematch_tail_risk.models import TailRiskPrediction, tier_from_probability
from worldcup_predictor.research.ecse_rerank.features import winner_side
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.ecse_tail_forensics.distributions import dist_hybrid_tail, topn
from worldcup_predictor.research.eeso.metrics import hit_rate, topn_contains_end_result


def conditional_top5_lines(
    row: dict[str, Any],
    *,
    prediction: TailRiskPrediction,
) -> tuple[list[str], str]:
    """Return Top5 lines and routing reason. Canonical unless detector HIGH/VERY_HIGH."""
    dist = generate_score_distribution(float(row["lambda_home"]), float(row["lambda_away"]))
    canonical = topn(dist, 5)
    if prediction.tail_risk_tier in (TIER_HIGH, TIER_VERY_HIGH):
        corrected = topn(
            dist_hybrid_tail(
                float(row["lambda_home"]),
                float(row["lambda_away"]),
                odds_home=float(row["odds_home"]),
                odds_away=float(row["odds_away"]),
            ),
            5,
        )
        return corrected, "TAIL_CORRECTION_APPLIED"
    return canonical, "CANONICAL"


def run_conditional_backtest(
    validate_rows: list[dict[str, Any]],
    predictions: list[TailRiskPrediction],
) -> dict[str, Any]:
    """Out-of-time conditional correction vs canonical."""
    n = len(validate_rows)
    if n != len(predictions):
        raise ValueError("predictions length mismatch")

    canon_hits = Counter()
    cond_hits = Counter()
    canon_er = cond_er = 0
    pos_hits_canon = Counter()
    pos_hits_cond = Counter()
    neg_hits_canon = Counter()
    neg_hits_cond = Counter()
    pos_n = neg_n = 0
    by_league_canon: dict[str, Counter] = defaultdict(Counter)
    by_league_cond: dict[str, Counter] = defaultdict(Counter)
    by_league_n: Counter[str] = Counter()

    for row, pred in zip(validate_rows, predictions):
        actual = row["actual_score"]
        actual_er = winner_side(actual) or "draw"
        dist = generate_score_distribution(float(row["lambda_home"]), float(row["lambda_away"]))
        canon5 = topn(dist, 5)
        cond5, route = conditional_top5_lines(row, prediction=pred)
        canon3 = topn(dist, 3)
        cond3 = cond5[:3]
        canon1 = topn(dist, 1)

        if actual in canon1:
            canon_hits["top1"] += 1
        if actual in canon3:
            canon_hits["top3"] += 1
        if actual in canon5:
            canon_hits["top5"] += 1
        if actual in cond5[:1]:
            cond_hits["top1"] += 1
        if actual in cond3:
            cond_hits["top3"] += 1
        if actual in cond5:
            cond_hits["top5"] += 1
        if topn_contains_end_result(canon5, actual_er):
            canon_er += 1
        if topn_contains_end_result(cond5, actual_er):
            cond_er += 1

        is_pos = pred.tail_risk_tier in (TIER_HIGH, TIER_VERY_HIGH)
        if is_pos:
            pos_n += 1
            if actual in canon5:
                pos_hits_canon["top5"] += 1
            if actual in cond5:
                pos_hits_cond["top5"] += 1
        else:
            neg_n += 1
            if actual in canon5:
                neg_hits_canon["top5"] += 1
            if actual in cond5:
                neg_hits_cond["top5"] += 1

        lg = row.get("league") or "unknown"
        by_league_n[lg] += 1
        if actual in canon5:
            by_league_canon[lg]["top5"] += 1
        if actual in cond5:
            by_league_cond[lg]["top5"] += 1

    canon_rates = {k: hit_rate(v, n) for k, v in canon_hits.items()}
    cond_rates = {k: hit_rate(v, n) for k, v in cond_hits.items()}
    global_lift = round(cond_rates.get("top5", 0) - canon_rates.get("top5", 0), 3)

    return {
        "oot_fixtures": n,
        "detector_positive_fixtures": pos_n,
        "detector_negative_fixtures": neg_n,
        "canonical_hit_rates_pct": canon_rates,
        "conditional_hit_rates_pct": cond_rates,
        "global_top5_lift_pp": global_lift,
        "global_top3_lift_pp": round(cond_rates.get("top3", 0) - canon_rates.get("top3", 0), 3),
        "global_top1_lift_pp": round(cond_rates.get("top1", 0) - canon_rates.get("top1", 0), 3),
        "end_result_top5_canonical_pct": hit_rate(canon_er, n),
        "end_result_top5_conditional_pct": hit_rate(cond_er, n),
        "detector_positive_top5_canonical_pct": hit_rate(pos_hits_canon["top5"], pos_n) if pos_n else 0.0,
        "detector_positive_top5_conditional_pct": hit_rate(pos_hits_cond["top5"], pos_n) if pos_n else 0.0,
        "conditional_top5_lift_on_positive_pp": round(
            hit_rate(pos_hits_cond["top5"], pos_n) - hit_rate(pos_hits_canon["top5"], pos_n), 3
        )
        if pos_n
        else 0.0,
        "non_tail_top5_canonical_pct": hit_rate(neg_hits_canon["top5"], neg_n) if neg_n else 0.0,
        "non_tail_top5_conditional_pct": hit_rate(neg_hits_cond["top5"], neg_n) if neg_n else 0.0,
        "non_tail_degradation_pp": round(
            hit_rate(neg_hits_cond["top5"], neg_n) - hit_rate(neg_hits_canon["top5"], neg_n), 3
        )
        if neg_n
        else 0.0,
        "league_breakdown": {
            lg: {
                "n": by_league_n[lg],
                "canonical_top5": hit_rate(by_league_canon[lg]["top5"], by_league_n[lg]),
                "conditional_top5": hit_rate(by_league_cond[lg]["top5"], by_league_n[lg]),
                "lift_pp": round(
                    hit_rate(by_league_cond[lg]["top5"], by_league_n[lg])
                    - hit_rate(by_league_canon[lg]["top5"], by_league_n[lg]),
                    3,
                ),
            }
            for lg in sorted(by_league_n.keys(), key=lambda x: -by_league_n[x])[:15]
        },
    }
