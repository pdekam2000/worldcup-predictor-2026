"""Build score and outcome priors from weighted historical neighbors."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from worldcup_predictor.research.ecse_market_prior.types import MarketPriorRow
from worldcup_predictor.research.ecse_market_prior.neighbors import NeighborMatch, effective_sample_size
from worldcup_predictor.research.ecse_market_prior.probability_space import reorient_score_to_home_away


@dataclass
class MarketPriorBundle:
    neighbor_count: int
    effective_n: float
    segment_used: str
    segment_fallback: bool
    score_probs_home_away: dict[str, float]
    score_probs_fav_norm: dict[str, float]
    favorite_win_pct: float
    draw_pct: float
    underdog_win_pct: float
    btts_yes_pct: float
    over_25_pct: float
    total_goals_mean: float
    margin_distribution: dict[str, float]
    top_scores_home_away: list[str]


def _weighted_counter(
    matches: Sequence[NeighborMatch],
    value_fn,
) -> tuple[Counter, float]:
    counter: Counter = Counter()
    total_w = 0.0
    for m in matches:
        w = float(m.weight)
        if w <= 0:
            continue
        counter[value_fn(m.row)] += w
        total_w += w
    return counter, total_w


def build_market_prior(
    target: MarketPriorRow,
    matches: Sequence[NeighborMatch],
    *,
    segment_used: str = "global",
    segment_fallback: bool = False,
    top_n: int = 10,
) -> MarketPriorBundle:
    score_counter, total_w = _weighted_counter(matches, lambda r: r.raw_score)
    fav_counter, _ = _weighted_counter(matches, lambda r: r.norm_score)
    outcome_counter, _ = _weighted_counter(matches, lambda r: r.fav_result)
    btts_counter, _ = _weighted_counter(matches, lambda r: r.btts_actual)
    ou_counter, _ = _weighted_counter(matches, lambda r: r.over_25_actual)
    margin_counter, _ = _weighted_counter(matches, lambda r: str(r.winning_margin))
    goals_sum = sum(m.weight * m.row.total_goals for m in matches)

    score_probs = {k: v / total_w for k, v in score_counter.items()} if total_w else {}
    fav_probs = {k: v / total_w for k, v in fav_counter.items()} if total_w else {}
    margin_probs = {k: v / total_w for k, v in margin_counter.items()} if total_w else {}

    def pct(counter: Counter, key) -> float:
        return 100.0 * counter.get(key, 0.0) / total_w if total_w else 0.0

    top_scores = [s for s, _ in sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:top_n]]

    return MarketPriorBundle(
        neighbor_count=len(matches),
        effective_n=round(effective_sample_size([m.weight for m in matches]), 3),
        segment_used=segment_used,
        segment_fallback=segment_fallback,
        score_probs_home_away=score_probs,
        score_probs_fav_norm=fav_probs,
        favorite_win_pct=round(pct(outcome_counter, "WIN"), 2),
        draw_pct=round(pct(outcome_counter, "DRAW"), 2),
        underdog_win_pct=round(pct(outcome_counter, "LOSS"), 2),
        btts_yes_pct=round(pct(btts_counter, 1), 2),
        over_25_pct=round(pct(ou_counter, 1), 2),
        total_goals_mean=round(goals_sum / total_w, 3) if total_w else 0.0,
        margin_distribution=margin_probs,
        top_scores_home_away=top_scores,
    )


def align_market_prior_to_ecse_grid(
    prior: MarketPriorBundle,
    target: MarketPriorRow,
    ecse_scorelines: Sequence[str],
) -> dict[str, float]:
    aligned: dict[str, float] = {s: 0.0 for s in ecse_scorelines}
    for score, prob in prior.score_probs_home_away.items():
        if score in aligned:
            aligned[score] += prob
    # map favorite-normalized scores back to home-away if missing direct key
    for norm_score, prob in prior.score_probs_fav_norm.items():
        ha = reorient_score_to_home_away(norm_score, target.fav_side)
        if ha in aligned:
            aligned[ha] += prob
    total = sum(aligned.values())
    if total <= 0:
        return aligned
    return {k: v / total for k, v in aligned.items()}
