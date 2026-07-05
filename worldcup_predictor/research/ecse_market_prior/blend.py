"""Shadow strategy transforms — no production ECSE mutation."""

from __future__ import annotations

import random
from typing import Literal, Sequence

from worldcup_predictor.research.ecse_market_prior.probability_space import parse_scoreline
from worldcup_predictor.research.ecse_score_distribution import MAX_GOALS, scoreline_label

DiversificationPolicy = Literal[
    "market_not_in_ecse",
    "highest_blended",
    "draw_risk",
    "tail_margin",
]


def ecse_distribution_dict(ecse_dist: Sequence[dict]) -> dict[str, float]:
    return {str(e["scoreline"]): float(e["probability"]) for e in ecse_dist}


def blend_distributions(
    ecse_probs: dict[str, float],
    market_probs: dict[str, float],
    alpha: float,
) -> dict[str, float]:
    alpha = max(0.0, min(float(alpha), 1.0))
    keys = set(ecse_probs) | set(market_probs)
    out = {k: (1.0 - alpha) * ecse_probs.get(k, 0.0) + alpha * market_probs.get(k, 0.0) for k in keys}
    total = sum(out.values())
    if total <= 0:
        return ecse_probs
    return {k: v / total for k, v in out.items()}


def top_n_from_probs(probs: dict[str, float], n: int) -> list[str]:
    return [s for s, _ in sorted(probs.items(), key=lambda x: x[1], reverse=True)[:n]]


def strategy_b_blend_topn(
    ecse_probs: dict[str, float],
    market_probs: dict[str, float],
    alpha: float,
    n: int = 3,
) -> list[str]:
    blended = blend_distributions(ecse_probs, market_probs, alpha)
    return top_n_from_probs(blended, n)


def strategy_c_diversified_top3(
    ecse_top10: Sequence[str],
    ecse_probs: dict[str, float],
    market_probs: dict[str, float],
    *,
    policy: DiversificationPolicy = "market_not_in_ecse",
    alpha: float = 0.15,
) -> list[str]:
    if len(ecse_top10) < 2:
        return list(ecse_top10[:3])
    keep = [ecse_top10[0], ecse_top10[1]]
    used = set(keep)

    if policy == "market_not_in_ecse":
        candidates = [
            (s, market_probs.get(s, 0.0))
            for s in market_probs
            if s not in used and s != "OTHER"
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        third = candidates[0][0] if candidates else ecse_top10[2] if len(ecse_top10) > 2 else keep[-1]
    elif policy == "highest_blended":
        blended = blend_distributions(ecse_probs, market_probs, alpha)
        third = next((s for s, _ in sorted(blended.items(), key=lambda x: x[1], reverse=True) if s not in used), keep[-1])
    elif policy == "draw_risk":
        drawish = [s for s in market_probs if parse_scoreline(s) and parse_scoreline(s)[0] == parse_scoreline(s)[1]]
        drawish.sort(key=lambda s: market_probs.get(s, 0.0), reverse=True)
        third = next((s for s in drawish if s not in used), ecse_top10[2] if len(ecse_top10) > 2 else keep[-1])
    else:  # tail_margin
        high_margin = [
            s
            for s in market_probs
            if parse_scoreline(s) and abs(parse_scoreline(s)[0] - parse_scoreline(s)[1]) >= 2
        ]
        high_margin.sort(key=lambda s: market_probs.get(s, 0.0), reverse=True)
        third = next((s for s in high_margin if s not in used), ecse_top10[2] if len(ecse_top10) > 2 else keep[-1])

    out = keep + [third]
    # pad to 3 unique
    for s in ecse_top10:
        if len(out) >= 3:
            break
        if s not in out:
            out.append(s)
    return out[:3]


def strategy_d_tail_calibration(
    ecse_probs: dict[str, float],
    market_probs: dict[str, float],
    *,
    tail_boost: float = 0.12,
) -> dict[str, float]:
    """Boost high-margin and draw scores using market tail mass; renormalize."""
    out = dict(ecse_probs)
    for score, mp in market_probs.items():
        parsed = parse_scoreline(score)
        if not parsed:
            continue
        h, a = parsed
        margin = abs(h - a)
        if margin >= 2 or h == a:
            out[score] = out.get(score, 0.0) + tail_boost * mp
    total = sum(out.values())
    if total <= 0:
        return ecse_probs
    return {k: v / total for k, v in out.items()}


def random_score_prior(seed: int, grid_scores: Sequence[str]) -> dict[str, float]:
    rng = random.Random(seed)
    weights = [rng.random() for _ in grid_scores]
    s = sum(weights)
    return {score: w / s for score, w in zip(grid_scores, weights)}


def global_unconditional_prior(rows_raw_scores: Sequence[str]) -> dict[str, float]:
    from collections import Counter

    c = Counter(rows_raw_scores)
    total = sum(c.values())
    return {k: v / total for k, v in c.items()}


def favorite_broad_prior(fav_side: str) -> dict[str, float]:
    scores = []
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            scores.append(scoreline_label(h, a))
    probs = {}
    for s in scores:
        p = parse_scoreline(s)
        if not p:
            continue
        h, a = p
        if fav_side == "HOME":
            if h > a:
                probs[s] = 0.12
            elif h == a:
                probs[s] = 0.08
            else:
                probs[s] = 0.04
        else:
            if a > h:
                probs[s] = 0.12
            elif h == a:
                probs[s] = 0.08
            else:
                probs[s] = 0.04
    total = sum(probs.values())
    return {k: v / total for k, v in probs.items()}


def shuffled_neighbor_prior(market_probs: dict[str, float], seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    items = list(market_probs.items())
    rng.shuffle(items)
    s = sum(v for _, v in items) or 1.0
    return {k: v / s for k, v in items}
