"""Walk-forward evaluation, agreement analysis, and diagnostics."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas
from worldcup_predictor.research.ecse_market_prior.blend import (
    ecse_distribution_dict,
    favorite_broad_prior,
    global_unconditional_prior,
    random_score_prior,
    shuffled_neighbor_prior,
    strategy_b_blend_topn,
    strategy_c_diversified_top3,
    strategy_d_tail_calibration,
    top_n_from_probs,
)
from worldcup_predictor.research.ecse_market_prior.dataset import external_row_to_ecse_odds_features
from worldcup_predictor.research.ecse_market_prior.types import MarketPriorRow
from worldcup_predictor.research.ecse_market_prior.neighbors import (
    _regularized_cov_inverse,
    find_neighbors,
)
from worldcup_predictor.research.ecse_market_prior.probability_space import (
    favorite_margin_abs,
    parse_scoreline,
)
from worldcup_predictor.research.ecse_market_prior.score_prior import align_market_prior_to_ecse_grid, build_market_prior
from worldcup_predictor.research.ecse_market_prior.segment_weighting import filter_pool_by_segment
from worldcup_predictor.research.ecse_market_prior.time_weighting import TimeScheme, apply_time_weights
from worldcup_predictor.research.ecse_score_distribution import OTHER_SCORELINE, generate_score_distribution

DistanceMetric = Literal["euclidean", "weighted_euclidean", "mahalanobis"]
MAX_PAST_POOL = 4000


@dataclass
class EvalRow:
    target: MarketPriorRow
    actual: str
    ecse_top1: str
    ecse_top3: list[str]
    ecse_top5: list[str]
    ecse_top10: list[str]
    ecse_probs: dict[str, float]
    market_top3: list[str]
    market_top5: list[str]
    market_top10: list[str]
    market_probs: dict[str, float]
    strategy_top3: dict[str, list[str]]
    lambda_home: float
    lambda_away: float


def _hit(actual: str, picks: Sequence[str]) -> bool:
    return actual in picks


def _margin_of_score(score: str, fav_side: str) -> int:
    p = parse_scoreline(score)
    if not p:
        return 0
    return favorite_margin_abs(p[0], p[1], fav_side)  # type: ignore[arg-type]


def build_ecse_for_row(row: MarketPriorRow, raw_json: dict[str, Any]) -> tuple[list[dict], dict[str, float], float, float] | None:
    features = external_row_to_ecse_odds_features(raw_json)
    features["registry_fixture_id"] = 0
    lam = extract_lambdas(features)
    if not lam or lam.get("lambda_home") is None or lam.get("lambda_away") is None:
        return None
    lh = float(lam["lambda_home"])
    la = float(lam["lambda_away"])
    dist = generate_score_distribution(lh, la)
    if not dist:
        return None
    probs = ecse_distribution_dict(dist)
    return dist, probs, lh, la


def evaluate_predictions(actual: str, top1: str, top3: Sequence[str], top5: Sequence[str]) -> dict[str, bool]:
    return {
        "top1_hit": _hit(actual, [top1]),
        "top3_hit": _hit(actual, top3),
        "top5_hit": _hit(actual, top5),
    }


def aggregate_rates(rows: Sequence[dict[str, bool]]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {"n": 0}
    return {
        "n": n,
        "top1_hit_pct": round(100.0 * sum(r["top1_hit"] for r in rows) / n, 2),
        "top3_hit_pct": round(100.0 * sum(r["top3_hit"] for r in rows) / n, 2),
        "top5_hit_pct": round(100.0 * sum(r["top5_hit"] for r in rows) / n, 2),
    }


def log_loss(actual: str, probs: dict[str, float], floor: float = 1e-12) -> float:
    p = max(probs.get(actual, 0.0), floor)
    return -math.log(p)


def brier_score(actual: str, probs: dict[str, float]) -> float:
    return sum((p - (1.0 if s == actual else 0.0)) ** 2 for s, p in probs.items())


def set_overlap(a: Sequence[str], b: Sequence[str]) -> int:
    return len(set(a) & set(b))


def agreement_bucket(ecse_top3: Sequence[str], market_top3: Sequence[str]) -> str:
    overlap = set_overlap(ecse_top3, market_top3)
    if overlap == 3:
        return "full_3_3"
    if overlap == 2:
        return "partial_2_3"
    if overlap == 1:
        return "partial_1_3"
    return "none_0_3"


@dataclass
class WalkForwardResult:
    config: dict[str, Any]
    train_metrics: dict[str, Any] = field(default_factory=dict)
    validation_metrics: dict[str, Any] = field(default_factory=dict)
    holdout_metrics: dict[str, Any] = field(default_factory=dict)
    agreement_analysis: dict[str, Any] = field(default_factory=dict)
    margin_analysis: dict[str, Any] = field(default_factory=dict)
    negative_controls: dict[str, Any] = field(default_factory=dict)
    k_comparison: dict[str, Any] = field(default_factory=dict)
    time_weighting_comparison: dict[str, Any] = field(default_factory=dict)
    tuned_alpha: float = 0.0
    eval_rows_sample: list[dict[str, Any]] = field(default_factory=list)


def _chronological_splits(
    rows: Sequence[MarketPriorRow],
    train_frac: float = 0.60,
    val_frac: float = 0.15,
) -> tuple[list[int], list[int], list[int]]:
    n = len(rows)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    train_idx = list(range(train_end))
    val_idx = list(range(train_end, val_end))
    holdout_idx = list(range(val_end, n))
    return train_idx, val_idx, holdout_idx


def _evaluate_split(
    dataset: Sequence[MarketPriorRow],
    eval_indices: Sequence[int],
    *,
    k: int = 250,
    metric: DistanceMetric = "euclidean",
    time_scheme: TimeScheme = "equal",
    segment_min_n: int = 100,
    alpha: float = 0.15,
    strategy: str = "baseline",
    diversification_policy: str = "market_not_in_ecse",
    raw_json_by_hash: dict[str, dict[str, Any]] | None = None,
    max_eval: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_json_by_hash = raw_json_by_hash or {}
    per_fixture: list[dict[str, Any]] = []
    baseline_rows: list[dict[str, bool]] = []
    strategy_rows: list[dict[str, bool]] = []
    agreement_groups: dict[str, list[dict[str, bool]]] = defaultdict(list)
    margin_cases: list[dict[str, Any]] = []

    indices = list(eval_indices)
    if max_eval and len(indices) > max_eval:
        step = max(len(indices) // max_eval, 1)
        indices = indices[::step][:max_eval]

    for idx in indices:
        target = dataset[idx]
        past = [dataset[i] for i in range(idx)]
        if len(past) > MAX_PAST_POOL:
            past = past[-MAX_PAST_POOL:]
        if len(past) < segment_min_n:
            continue

        pool, seg_used, seg_fallback = filter_pool_by_segment(past, target, min_n=segment_min_n)
        cov_inv = None
        if metric == "mahalanobis" and len(pool) >= 50:
            vecs = [(r.prob_fav, r.prob_draw, r.prob_dog) for r in pool[:5000]]
            cov_inv = _regularized_cov_inverse(vecs)

        matches = find_neighbors(target, pool, k=min(k, len(pool)), metric=metric)
        time_w = apply_time_weights([m.row.fixture_date for m in matches], target.fixture_date, time_scheme)
        for m, tw in zip(matches, time_w):
            m.weight *= tw
        matches = [m for m in matches if m.weight > 0]
        if not matches:
            continue

        prior = build_market_prior(
            target,
            matches,
            segment_used=seg_used,
            segment_fallback=seg_fallback,
        )

        raw = raw_json_by_hash.get(target.row_hash, {})
        ecse = build_ecse_for_row(target, raw) if raw else None
        if not ecse:
            # minimal odds-only ECSE from 1x2 implied rates
            features = external_row_to_ecse_odds_features(
                {
                    "oddsFT_1": target.odds_home,
                    "oddsFT_X": target.odds_draw,
                    "oddsFT_2": target.odds_away,
                    "oddsFT_Over_2_5": None,
                    "oddsFT_BTTS_Yes": None,
                }
            )
            lam = extract_lambdas(features)
            if not lam:
                continue
            dist = generate_score_distribution(float(lam["lambda_home"]), float(lam["lambda_away"]))
            ecse_probs = ecse_distribution_dict(dist)
        else:
            _, ecse_probs, _, _ = ecse

        ecse_top10 = top_n_from_probs(ecse_probs, 10)
        ecse_top5 = ecse_top10[:5]
        ecse_top3 = ecse_top10[:3]
        ecse_top1 = ecse_top10[0]
        market_probs = align_market_prior_to_ecse_grid(prior, target, ecse_probs.keys())
        market_top10 = top_n_from_probs(market_probs, 10)
        market_top3 = market_top10[:3]

        actual = target.raw_score
        base_eval = evaluate_predictions(actual, ecse_top1, ecse_top3, ecse_top5)
        baseline_rows.append(base_eval)

        if strategy == "baseline":
            strat_top3 = ecse_top3
        elif strategy == "all":
            strat_top3 = ecse_top3
        elif strategy == "blend":
            strat_top3 = strategy_b_blend_topn(ecse_probs, market_probs, alpha, 3)
        elif strategy == "diversify":
            strat_top3 = strategy_c_diversified_top3(
                ecse_top10, ecse_probs, market_probs, policy=diversification_policy, alpha=alpha
            )
        elif strategy == "tail":
            tail_probs = strategy_d_tail_calibration(ecse_probs, market_probs)
            strat_top3 = top_n_from_probs(tail_probs, 3)
        else:
            strat_top3 = ecse_top3

        strat_eval = evaluate_predictions(actual, strat_top3[0], strat_top3, ecse_top5)
        strategy_rows.append(strat_eval)

        bucket = agreement_bucket(ecse_top3, market_top3)
        agreement_groups[bucket].append(base_eval)

        actual_margin = favorite_margin_abs(target.home_goals, target.away_goals, target.fav_side)
        top3_margins = [_margin_of_score(s, target.fav_side) for s in ecse_top3]
        if base_eval["top1_hit"] is False and actual_margin > max(top3_margins + [0]):
            margin_cases.append(
                {
                    "actual": actual,
                    "actual_margin": actual_margin,
                    "ecse_top3": ecse_top3,
                    "market_top3": market_top3,
                    "max_top3_margin": max(top3_margins),
                }
            )

        per_fixture.append(
            {
                "row_hash": target.row_hash,
                "fixture_date": target.fixture_date,
                "actual": actual,
                "ecse_top3": ecse_top3,
                "market_top3": market_top3,
                "strategy_top3": strat_top3,
                "agreement": bucket,
                **base_eval,
            }
        )

    return per_fixture, {
        "baseline": aggregate_rates(baseline_rows),
        "strategy": aggregate_rates(strategy_rows),
        "agreement": {k: aggregate_rates(v) for k, v in agreement_groups.items()},
        "margin_underestimated_cases": len(margin_cases),
        "margin_case_sample": margin_cases[:10],
    }


def _evaluate_holdout_comprehensive(
    dataset: Sequence[MarketPriorRow],
    eval_indices: Sequence[int],
    *,
    k: int,
    alpha: float,
    raw_json_by_hash: dict[str, dict[str, Any]],
    max_eval: int,
    time_scheme: TimeScheme = "equal",
) -> dict[str, Any]:
    indices = list(eval_indices)
    if max_eval and len(indices) > max_eval:
        step = max(len(indices) // max_eval, 1)
        indices = indices[::step][:max_eval]

    strategy_rows: dict[str, list[dict[str, bool]]] = {
        "A_baseline_ecse": [],
        "B_market_blend": [],
        "C_diversified_top3": [],
        "D_tail_calibration": [],
    }
    agreement_groups: dict[str, list[dict[str, bool]]] = defaultdict(list)
    margin_cases: list[dict[str, Any]] = []
    per_fixture: list[dict[str, Any]] = []

    for idx in indices:
        target = dataset[idx]
        past = dataset[max(0, idx - MAX_PAST_POOL) : idx]
        if len(past) < 100:
            continue
        pool, seg_used, seg_fallback = filter_pool_by_segment(past, target, min_n=100)
        search_pool = pool if len(pool) >= 100 else past
        matches = find_neighbors(target, search_pool, k=min(k, len(search_pool)))
        time_w = apply_time_weights([m.row.fixture_date for m in matches], target.fixture_date, time_scheme)
        for m, tw in zip(matches, time_w):
            m.weight *= tw
        matches = [m for m in matches if m.weight > 0]
        if not matches:
            continue

        prior = build_market_prior(target, matches, segment_used=seg_used, segment_fallback=seg_fallback)
        raw = raw_json_by_hash.get(target.row_hash, {})
        ecse = build_ecse_for_row(target, raw) if raw else None
        if not ecse:
            lam = extract_lambdas(
                external_row_to_ecse_odds_features(
                    {
                        "oddsFT_1": target.odds_home,
                        "oddsFT_X": target.odds_draw,
                        "oddsFT_2": target.odds_away,
                    }
                )
            )
            if not lam:
                continue
            ecse_probs = ecse_distribution_dict(
                generate_score_distribution(float(lam["lambda_home"]), float(lam["lambda_away"]))
            )
        else:
            _, ecse_probs, _, _ = ecse

        ecse_top10 = top_n_from_probs(ecse_probs, 10)
        ecse_top5 = ecse_top10[:5]
        ecse_top3 = ecse_top10[:3]
        ecse_top1 = ecse_top10[0]
        market_probs = align_market_prior_to_ecse_grid(prior, target, ecse_probs.keys())
        market_top3 = top_n_from_probs(market_probs, 3)
        actual = target.raw_score
        base_eval = evaluate_predictions(actual, ecse_top1, ecse_top3, ecse_top5)
        strategy_rows["A_baseline_ecse"].append(base_eval)

        blend_top3 = strategy_b_blend_topn(ecse_probs, market_probs, alpha, 3)
        div_top3 = strategy_c_diversified_top3(ecse_top10, ecse_probs, market_probs, alpha=alpha)
        tail_top3 = top_n_from_probs(strategy_d_tail_calibration(ecse_probs, market_probs), 3)
        strategy_rows["B_market_blend"].append(evaluate_predictions(actual, blend_top3[0], blend_top3, ecse_top5))
        strategy_rows["C_diversified_top3"].append(evaluate_predictions(actual, div_top3[0], div_top3, ecse_top5))
        strategy_rows["D_tail_calibration"].append(evaluate_predictions(actual, tail_top3[0], tail_top3, ecse_top5))

        bucket = agreement_bucket(ecse_top3, market_top3)
        agreement_groups[bucket].append(base_eval)
        actual_margin = favorite_margin_abs(target.home_goals, target.away_goals, target.fav_side)
        top3_margins = [_margin_of_score(s, target.fav_side) for s in ecse_top3]
        if not base_eval["top1_hit"] and actual_margin > max(top3_margins + [0]):
            margin_cases.append({"actual": actual, "actual_margin": actual_margin, "ecse_top3": ecse_top3})
        if len(per_fixture) < 25:
            per_fixture.append(
                {"fixture_date": target.fixture_date, "actual": actual, "ecse_top3": ecse_top3, "market_top3": market_top3, "agreement": bucket}
            )

    return {
        "strategies": {
            name: {
                ("baseline" if name == "A_baseline_ecse" else "strategy"): aggregate_rates(rows),
                "n_evaluated": len(rows),
            }
            for name, rows in strategy_rows.items()
        },
        "agreement": {k: aggregate_rates(v) for k, v in agreement_groups.items()},
        "margin_underestimated_cases": len(margin_cases),
        "margin_case_sample": margin_cases[:10],
        "per_fixture_sample": per_fixture,
        "baseline_summary": aggregate_rates(strategy_rows["A_baseline_ecse"]),
    }


def tune_alpha_validation(
    dataset: Sequence[MarketPriorRow],
    val_indices: Sequence[int],
    *,
    k: int,
    alphas: Sequence[float],
    raw_json_by_hash: dict[str, dict[str, Any]],
    max_eval: int = 150,
) -> float:
    best_alpha = 0.0
    best_top3 = -1.0
    for alpha in alphas:
        _, metrics = _evaluate_split(
            dataset,
            val_indices,
            k=k,
            alpha=alpha,
            strategy="blend",
            raw_json_by_hash=raw_json_by_hash,
            max_eval=max_eval,
        )
        top3 = metrics["strategy"].get("top3_hit_pct", 0.0)
        if top3 > best_top3:
            best_top3 = top3
            best_alpha = alpha
    return best_alpha


def run_walk_forward_shadow(
    dataset: Sequence[MarketPriorRow],
    raw_json_by_hash: dict[str, dict[str, Any]],
    *,
    k_values: Sequence[int] = (25, 50, 100, 250, 500, 1000),
    max_eval_per_split: int = 350,
) -> WalkForwardResult:
    train_idx, val_idx, holdout_idx = _chronological_splits(dataset)
    alphas = [0.0, 0.10, 0.15, 0.20, 0.25]
    tuned_alpha = tune_alpha_validation(
        dataset, val_idx, k=250, alphas=alphas, raw_json_by_hash=raw_json_by_hash, max_eval=150
    )

    result = WalkForwardResult(
        config={
            "train_n": len(train_idx),
            "validation_n": len(val_idx),
            "holdout_n": len(holdout_idx),
            "walk_forward_rule": "neighbors from indices < target index only; past pool capped",
            "max_past_pool": MAX_PAST_POOL,
            "max_eval_per_split": max_eval_per_split,
        },
        tuned_alpha=tuned_alpha,
    )

    holdout_block = _evaluate_holdout_comprehensive(
        dataset, holdout_idx, k=250, alpha=tuned_alpha, raw_json_by_hash=raw_json_by_hash, max_eval=max_eval_per_split
    )
    result.holdout_metrics = {
        "baseline": holdout_block["baseline_summary"],
        "strategies": holdout_block["strategies"],
        "n_evaluated": holdout_block["baseline_summary"].get("n", 0),
    }
    result.agreement_analysis = holdout_block["agreement"]
    result.margin_analysis = {
        "underestimated_count": holdout_block["margin_underestimated_cases"],
        "sample": holdout_block["margin_case_sample"],
    }
    result.eval_rows_sample = holdout_block["per_fixture_sample"]

    _, val_metrics = _evaluate_split(
        dataset, val_idx, k=250, strategy="baseline", raw_json_by_hash=raw_json_by_hash, max_eval=120
    )
    result.validation_metrics = val_metrics
    result.train_metrics = {"note": "train split reserved; metrics on val/holdout for runtime"}

    k_comp = {}
    for k in k_values:
        _, metrics = _evaluate_split(
            dataset, holdout_idx, k=k, strategy="baseline", raw_json_by_hash=raw_json_by_hash, max_eval=120
        )
        k_comp[str(k)] = metrics["baseline"]
    result.k_comparison = k_comp

    tw_comp = {}
    for scheme in ("equal", "decay_365d", "last_2_seasons"):
        block = _evaluate_holdout_comprehensive(
            dataset,
            holdout_idx,
            k=250,
            alpha=tuned_alpha,
            raw_json_by_hash=raw_json_by_hash,
            max_eval=120,
            time_scheme=scheme,  # type: ignore[arg-type]
        )
        tw_comp[scheme] = block["strategies"]["B_market_blend"].get("strategy", {})
    result.time_weighting_comparison = tw_comp

    neg: dict[str, list] = defaultdict(list)
    rng_scores = [f"{h}-{a}" for h in range(8) for a in range(8)]
    for idx in holdout_idx[:80]:
        target = dataset[idx]
        past = dataset[max(0, idx - MAX_PAST_POOL) : idx]
        if len(past) < 100:
            continue
        matches = find_neighbors(target, past, k=250)
        prior = build_market_prior(target, matches)
        raw = raw_json_by_hash.get(target.row_hash, {})
        ecse = build_ecse_for_row(target, raw) if raw else None
        if not ecse:
            continue
        _, ecse_probs, _, _ = ecse
        actual = target.raw_score
        ecse_top3 = top_n_from_probs(ecse_probs, 3)
        ev = evaluate_predictions(actual, ecse_top3[0], ecse_top3, ecse_top3)
        neg["ecse_baseline"].append(ev)
        rand_top3 = top_n_from_probs(random_score_prior(hash(target.row_hash) % 9999, rng_scores), 3)
        neg["random_prior"].append(evaluate_predictions(actual, rand_top3[0], rand_top3, rand_top3))
        glob = top_n_from_probs(global_unconditional_prior([r.raw_score for r in past]), 3)
        neg["global_unconditional"].append(evaluate_predictions(actual, glob[0], glob, glob))
        shuf = top_n_from_probs(shuffled_neighbor_prior(prior.score_probs_home_away, hash(target.row_hash)), 3)
        neg["shuffled_neighbors"].append(evaluate_predictions(actual, shuf[0], shuf, shuf))
    result.negative_controls = {k: aggregate_rates(v) for k, v in neg.items()}

    return result


def production_fixture_diagnostics(
    *,
    fixture_id: int,
    match_name: str,
    odds_home: float | None,
    odds_draw: float | None,
    odds_away: float | None,
    ecse_top3: Sequence[str],
    dataset: Sequence[MarketPriorRow],
) -> dict[str, Any]:
    if not all(x and x > 1.0 for x in (odds_home, odds_draw, odds_away)):
        return {
            "fixture_id": fixture_id,
            "match": match_name,
            "status": "NO_VALID_ODDS_CONTEXT",
        }

    from worldcup_predictor.research.ecse_market_prior.probability_space import (
        favorite_frame_probs,
        favorite_side,
        margin_normalized_probs,
    )
    from worldcup_predictor.research.ecse_market_prior.types import MarketPriorRow

    p_h, p_d, p_a = margin_normalized_probs(float(odds_home), float(odds_draw), float(odds_away))
    side = favorite_side(float(odds_home), float(odds_away))
    _, p_fav, p_draw_fav, p_dog, (pf, pd, pu) = favorite_frame_probs(
        float(odds_home), float(odds_draw), float(odds_away)
    )
    # synthetic target row for neighbor search
    target = MarketPriorRow(
        row_hash=f"prod-{fixture_id}",
        fixture_date="2099-01-01",
        kickoff_utc="2099-01-01",
        league="WC2026",
        country="International",
        source_file="production",
        home_team=match_name.split(" vs ")[0] if " vs " in match_name else match_name,
        away_team=match_name.split(" vs ")[1] if " vs " in match_name else "",
        odds_home=float(odds_home),
        odds_draw=float(odds_draw),
        odds_away=float(odds_away),
        p_home=p_h,
        p_draw=p_d,
        p_away=p_a,
        fav_side=side,
        p_favorite=p_fav,
        p_draw_fav=p_draw_fav,
        p_underdog=p_dog,
        prob_fav=pf,
        prob_draw=pd,
        prob_dog=pu,
        home_goals=0,
        away_goals=0,
        raw_score="0-0",
        norm_score="0-0",
        fav_result="DRAW",
        btts_actual=0,
        over_25_actual=0,
        total_goals=0,
        winning_margin=0,
        segment="national_teams",
    )

    pool, seg_used, seg_fallback = filter_pool_by_segment(dataset, target, min_n=50)
    matches = find_neighbors(target, pool if len(pool) >= 50 else list(dataset), k=250)
    prior = build_market_prior(target, matches, segment_used=seg_used, segment_fallback=seg_fallback)
    market_top5 = prior.top_scores_home_away[:5]
    market_top3 = market_top5[:3]
    overlap = set_overlap(ecse_top3, market_top3)
    if overlap == 3:
        agreement = "HIGH_AGREEMENT"
    elif overlap == 2:
        agreement = "MEDIUM_AGREEMENT"
    elif overlap == 1:
        agreement = "LOW_AGREEMENT"
    else:
        agreement = "LOW_AGREEMENT"

    return {
        "fixture_id": fixture_id,
        "match": match_name,
        "odds": {"home": odds_home, "draw": odds_draw, "away": odds_away},
        "fav_side": side,
        "segment_used": seg_used,
        "segment_fallback": seg_fallback,
        "national_team_warning": seg_fallback or seg_used == "global",
        "neighbor_count": prior.neighbor_count,
        "effective_n": prior.effective_n,
        "market_prior_top5": market_top5,
        "ecse_top3": list(ecse_top3),
        "set_overlap": overlap,
        "agreement_class": agreement,
        "market_top3_fav_norm": prior.top_scores_home_away[:3],
        "market_fav_win_pct": prior.favorite_win_pct,
        "market_draw_pct": prior.draw_pct,
        "market_dog_win_pct": prior.underdog_win_pct,
    }
