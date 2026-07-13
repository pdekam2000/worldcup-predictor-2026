"""Paired historical backtest for ECSE tail distribution research."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from typing import Any, Callable

from worldcup_predictor.research.ecse_historical_replay.replay_engine import ReplayRow, iter_replay_rows
from worldcup_predictor.research.ecse_lambda_extraction import btts_prob_independent, devig_yes_no
from worldcup_predictor.research.ecse_market_prior.dataset import external_row_to_ecse_odds_features
from worldcup_predictor.research.ecse_rerank.features import winner_side
from worldcup_predictor.research.eeso.metrics import classify_named_league, hit_rate, implied_wde_direction
from worldcup_predictor.research.ecse_tail_forensics.buckets import (
    classify_fixture_outcomes,
    score_bucket,
    team_goals_bucket,
    top5_diagnostics,
    total_goals_bucket,
)
from worldcup_predictor.research.ecse_tail_forensics.calibration import (
    CalibrationAccumulator,
    brier_score,
    log_loss,
)
from worldcup_predictor.research.ecse_tail_forensics.constants import (
    ALL_METHODS,
    METHOD_CANONICAL_POISSON,
    TIME_SPLIT_TRAIN_END,
    TIME_SPLIT_VALIDATE_START,
    UNSUPPORTED_METHODS,
)
from worldcup_predictor.research.ecse_tail_forensics.distributions import (
    dist_bivariate_poisson,
    dist_btts_consistency,
    dist_canonical_poisson,
    dist_dixon_coles,
    dist_hybrid_tail,
    dist_league_variance,
    dist_negative_binomial,
    dist_tail_temperature,
    dist_underdog_floor,
    prob_map,
    tail_diagnostics,
    topn,
)
from worldcup_predictor.research.ecse_tail_forensics.lambda_audit import LambdaBiasAccumulator, LeagueLambdaBias


def _hit(actual: str, lines: list[str]) -> bool:
    return actual in lines


def _er_hit(lines: list[str], actual_er: str) -> bool:
    return any(winner_side(s) == actual_er for s in lines)


def compute_league_multipliers_from_conn(conn: sqlite3.Connection) -> dict[str, float]:
    """Train-set observed/predicted total goals ratio per league code."""
    obs: dict[str, float] = defaultdict(float)
    pred: dict[str, float] = defaultdict(float)
    n: dict[str, int] = defaultdict(int)
    for row in iter_replay_rows(conn):
        if row.event_date >= TIME_SPLIT_TRAIN_END:
            continue
        lg = row.league or "unknown"
        obs[lg] += row.actual_home + row.actual_away
        pred[lg] += row.lambda_total
        n[lg] += 1
    mult: dict[str, float] = {}
    for lg, cnt in n.items():
        if cnt < 50:
            mult[lg] = 1.0
        else:
            mult[lg] = min(max(obs[lg] / max(pred[lg], 1e-6), 0.85), 1.20)
    return mult


def compute_league_multipliers(rows: list[ReplayRow]) -> dict[str, float]:
    """Train-set observed/predicted total goals ratio per league code."""
    obs: dict[str, float] = defaultdict(float)
    pred: dict[str, float] = defaultdict(float)
    n: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.event_date >= TIME_SPLIT_TRAIN_END:
            continue
        lg = row.league or "unknown"
        obs[lg] += row.actual_home + row.actual_away
        pred[lg] += row.lambda_total
        n[lg] += 1
    mult: dict[str, float] = {}
    for lg, cnt in n.items():
        if cnt < 50:
            mult[lg] = 1.0
        else:
            mult[lg] = min(max(obs[lg] / max(pred[lg], 1e-6), 0.85), 1.20)
    return mult


def build_method_distributions(
    row: ReplayRow,
    *,
    league_multipliers: dict[str, float],
    odds_features: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    lh, la = row.lambda_home, row.lambda_away
    lm = league_multipliers.get(row.league, 1.0)
    return {
        METHOD_CANONICAL_POISSON: dist_canonical_poisson(lh, la),
        "dixon_coles": dist_dixon_coles(lh, la),
        "bivariate_poisson": dist_bivariate_poisson(lh, la),
        "negative_binomial": dist_negative_binomial(lh, la),
        "league_variance": dist_league_variance(lh, la, league_multiplier=lm),
        "tail_temperature": dist_tail_temperature(lh, la),
        "underdog_floor": dist_underdog_floor(lh, la, odds_home=row.odds_home, odds_away=row.odds_away),
        "btts_consistency": dist_btts_consistency(lh, la, odds_features=odds_features),
        "hybrid_tail": dist_hybrid_tail(
            lh, la, odds_home=row.odds_home, odds_away=row.odds_away, odds_features=odds_features
        ),
    }


def run_tail_forensics_backtest(
    conn: sqlite3.Connection,
    *,
    max_fixtures: int | None = None,
    build_dataset: bool = True,
) -> dict[str, Any]:
    """Single-pass paired backtest across research distributions."""
    league_mult = compute_league_multipliers_from_conn(conn)
    n_fixtures = 0
    er_hits: dict[str, Counter[str]] = defaultdict(Counter)
    log_loss_sum: dict[str, float] = defaultdict(float)
    brier_sum: dict[str, float] = defaultdict(float)
    paired_wlt: dict[str, dict[str, int]] = defaultdict(lambda: {"wins": 0, "losses": 0, "ties": 0})
    hits: dict[str, Counter[str]] = defaultdict(Counter)
    cal_total_goals = CalibrationAccumulator()
    cal_home_goals = CalibrationAccumulator()
    cal_away_goals = CalibrationAccumulator()
    cal_btts = CalibrationAccumulator()
    cal_high_tail = CalibrationAccumulator()
    cal_clean_sheet = CalibrationAccumulator()

    lambda_global = LambdaBiasAccumulator()
    lambda_league = LeagueLambdaBias()

    segment_hits: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    segment_n: Counter[str] = Counter()
    league_hits: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    league_n: Counter[str] = Counter()

    time_split_hits: dict[str, dict[str, Counter[str]]] = {"train": defaultdict(Counter), "validate": defaultdict(Counter)}
    time_split_n: Counter[str] = Counter()

    dataset_rows: list[dict[str, Any]] = []
    miss_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in iter_replay_rows(conn):
        if max_fixtures and n_fixtures >= max_fixtures:
            break
        n_fixtures += 1
        actual = row.actual_score
        actual_er = winner_side(actual) or "draw"
        outcomes = classify_fixture_outcomes(
            actual_score=actual,
            home_goals=row.actual_home,
            away_goals=row.actual_away,
            odds_home=row.odds_home,
            odds_away=row.odds_away,
            lambda_home=row.lambda_home,
            lambda_away=row.lambda_away,
        )
        odds_features = None  # replay row lacks full feature dict; BTTS from row odds if present in raw - skip

        dists = build_method_distributions(row, league_multipliers=league_mult, odds_features=odds_features)
        canonical_dist = dists[METHOD_CANONICAL_POISSON]
        canon_pm = prob_map(canonical_dist)
        prob_actual = canon_pm.get(actual, 0.0)
        top5_diag = top5_diagnostics(topn(canonical_dist, 5))

        if build_dataset:
            dataset_rows.append(
                {
                    "fixture_id": row.fixture_key,
                    "league": row.league,
                    "kickoff": row.kickoff,
                    "actual_score": actual,
                    "actual_bucket": outcomes["score_bucket"],
                    "lambda_home": row.lambda_home,
                    "lambda_away": row.lambda_away,
                    "total_lambda": row.lambda_total,
                    "lambda_gap": outcomes["lambda_gap"],
                    "prob_actual": prob_actual,
                    "actual_rank": row.actual_rank,
                    "in_top1": row.top1 == actual,
                    "in_top3": actual in topn(canonical_dist, 3),
                    "in_top5": actual in topn(canonical_dist, 5),
                    "in_top10": row.actual_rank <= 10,
                    "outside_top10": row.actual_rank > 10,
                    "top5_clean_sheet_count": top5_diag["top5_clean_sheet_count"],
                    "top5_btts_count": top5_diag["top5_btts_count"],
                    "entropy": row.entropy,
                    "top3_mass": row.top3_mass,
                    "top5_mass": row.top5_mass,
                    "wde_direction": implied_wde_direction(row.odds_home, row.odds_draw, row.odds_away),
                    "btts_actual": outcomes["btts_yes"],
                    "end_result": actual_er,
                }
            )

        model_btts = btts_prob_independent(row.lambda_home, row.lambda_away)
        lambda_global.add(
            lambda_home=row.lambda_home,
            lambda_away=row.lambda_away,
            actual_home=row.actual_home,
            actual_away=row.actual_away,
            odds_home=row.odds_home,
            odds_away=row.odds_away,
            market_btts_yes=None,
            model_btts=model_btts,
            top5_hit=row.top5_hit,
            score_bucket=outcomes["score_bucket"],
            actual_rank=row.actual_rank,
        )
        lambda_league.add(
            row.league,
            lambda_home=row.lambda_home,
            lambda_away=row.lambda_away,
            actual_home=row.actual_home,
            actual_away=row.actual_away,
            odds_home=row.odds_home,
            odds_away=row.odds_away,
            market_btts_yes=None,
            model_btts=model_btts,
            top5_hit=row.top5_hit,
            score_bucket=outcomes["score_bucket"],
            actual_rank=row.actual_rank,
        )

        # Calibration on canonical only
        tg = row.actual_home + row.actual_away
        cal_total_goals.add(total_goals_bucket(tg), canon_pm.get(actual, 0.0), True)
        for g in range(7):
            cal_total_goals.add(
                f"total_eq_{g}",
                sum(canon_pm.get(f"{h}-{a}", 0.0) for h in range(8) for a in range(8) if h + a == g),
                tg == g,
            )
        cal_home_goals.add(team_goals_bucket(row.actual_home), sum(canon_pm.get(f"{h}-{row.actual_away}", 0.0) for h in range(8)), True)
        cal_away_goals.add(team_goals_bucket(row.actual_away), sum(canon_pm.get(f"{row.actual_home}-{a}", 0.0) for a in range(8)), True)
        cal_btts.add("btts_yes", sum(p for k, p in canon_pm.items() if "-" in k and all(int(x) > 0 for x in k.split("-"))), outcomes["btts_yes"])
        cal_high_tail.add("high_score_tail", sum(canon_pm.get(s, 0.0) for s in canon_pm if score_bucket(s) == "HIGH_SCORE_TAIL"), outcomes["score_bucket"] == "HIGH_SCORE_TAIL")
        cal_clean_sheet.add("clean_sheet_home", sum(canon_pm.get(f"{h}-0", 0.0) for h in range(8)), row.actual_away == 0)

        canon_hit5 = _hit(actual, topn(canonical_dist, 5))
        split_key = "validate" if row.event_date >= TIME_SPLIT_VALIDATE_START else "train"
        time_split_n[split_key] += 1

        for method, dist in dists.items():
            if method in UNSUPPORTED_METHODS:
                continue
            pm = prob_map(dist)
            p_act = pm.get(actual, 0.0)
            t1, t3, t5, t10 = topn(dist, 1), topn(dist, 3), topn(dist, 5), topn(dist, 10)
            if _hit(actual, t1):
                hits[method]["top1"] += 1
            if _hit(actual, t3):
                hits[method]["top3"] += 1
            if _hit(actual, t5):
                hits[method]["top5"] += 1
            if _hit(actual, t10):
                hits[method]["top10"] += 1
            if _er_hit(t5, actual_er):
                er_hits[method]["top5"] += 1
            log_loss_sum[method] += log_loss(p_act)
            brier_sum[method] += brier_score(p_act)

            h5 = _hit(actual, t5)
            if method != METHOD_CANONICAL_POISSON:
                if h5 and not canon_hit5:
                    paired_wlt[method]["wins"] += 1
                elif canon_hit5 and not h5:
                    paired_wlt[method]["losses"] += 1
                else:
                    paired_wlt[method]["ties"] += 1
            if h5:
                time_split_hits[split_key][method]["top5"] += 1

        # Segments
        segments = _segment_keys(row, outcomes)
        for seg in segments:
            segment_n[seg] += 1
            for method, dist in dists.items():
                if _hit(actual, topn(dist, 5)):
                    segment_hits[seg][method]["top5"] += 1

        nl = classify_named_league(row)
        if nl:
            league_n[nl] += 1
            for method, dist in dists.items():
                if _hit(actual, topn(dist, 5)):
                    league_hits[nl][method]["top5"] += 1

        # Miss casebook sampling
        if not row.top5_hit:
            bucket = outcomes["score_bucket"]
            key = bucket.lower()
            if len(miss_samples[key]) < 5:
                miss_samples[key].append(
                    {
                        "match": row.match,
                        "league": row.league,
                        "actual": actual,
                        "canonical_top5": topn(canonical_dist, 5),
                        "actual_rank": row.actual_rank,
                        "prob_actual": prob_actual,
                        "lambda_home": row.lambda_home,
                        "lambda_away": row.lambda_away,
                        "tail_diag": tail_diagnostics(canonical_dist),
                    }
                )

    def rates(method: str) -> dict[str, float]:
        return {k: hit_rate(hits[method][k], n_fixtures) for k in ("top1", "top3", "top5", "top10")}

    baseline_top5 = hit_rate(hits[METHOD_CANONICAL_POISSON]["top5"], n_fixtures)
    lifts = {
        m: round(rates(m)["top5"] - baseline_top5, 3)
        for m in dists
        if m != METHOD_CANONICAL_POISSON
    }
    best_method = max(lifts.items(), key=lambda x: x[1]) if lifts else (METHOD_CANONICAL_POISSON, 0.0)

    return {
        "paired_fixtures": n_fixtures,
        "league_multipliers_sample": dict(list(league_mult.items())[:15]),
        "hit_rates_pct": {m: rates(m) for m in dists if m not in UNSUPPORTED_METHODS},
        "end_result_top5_pct": {m: hit_rate(er_hits[m]["top5"], n_fixtures) for m in dists},
        "log_loss_mean": {m: round(log_loss_sum[m] / n_fixtures, 6) for m in dists},
        "brier_mean": {m: round(brier_sum[m] / n_fixtures, 6) for m in dists},
        "top5_lift_vs_canonical_pp": lifts,
        "paired_top5_comparison": dict(paired_wlt),
        "best_method": {"method": best_method[0], "top5_lift_pp": best_method[1]},
        "calibration": {
            "total_goals": cal_total_goals.report(),
            "home_goals": cal_home_goals.report(),
            "away_goals": cal_away_goals.report(),
            "btts": cal_btts.report(),
            "high_score_tail": cal_high_tail.report(),
            "clean_sheet_home": cal_clean_sheet.report(),
        },
        "lambda_bias_global": lambda_global.summary(),
        "lambda_bias_by_league": lambda_league.report(),
        "segment_analysis": {
            seg: {
                "n": segment_n[seg],
                "top5_hit_rate_pct": {m: hit_rate(segment_hits[seg][m]["top5"], segment_n[seg]) for m in dists},
            }
            for seg in sorted(segment_n.keys())
        },
        "named_league_breakdown": {
            lg: {
                "n": league_n[lg],
                "canonical_top5": hit_rate(league_hits[lg][METHOD_CANONICAL_POISSON]["top5"], league_n[lg]),
                "best_alt_top5": max(
                    (hit_rate(league_hits[lg][m]["top5"], league_n[lg]), m)
                    for m in dists
                    if m != METHOD_CANONICAL_POISSON
                )[0]
                if league_n[lg]
                else 0.0,
            }
            for lg in league_n
        },
        "time_split": {
            split: {
                "n": time_split_n[split],
                "top5_hit_rate_pct": {
                    m: hit_rate(time_split_hits[split][m]["top5"], time_split_n[split]) for m in dists
                },
            }
            for split in ("train", "validate")
        },
        "unsupported_methods": list(UNSUPPORTED_METHODS),
        "dataset_rows": dataset_rows,
        "miss_samples": miss_samples,
    }


def _segment_keys(row: ReplayRow, outcomes: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    fav_odds = outcomes["favourite_odds"]
    if fav_odds < 1.30:
        keys.append("fav_odds_lt_1_30")
    elif fav_odds < 1.60:
        keys.append("fav_odds_1_30_1_60")
    else:
        keys.append("balanced_odds")
    if not outcomes["favourite_is_home"] and fav_odds < 1.60:
        keys.append("strong_away_favourite")
    if row.lambda_total < 2.25:
        keys.append("expected_total_under_2_25")
    elif row.lambda_total <= 3.0:
        keys.append("expected_total_2_25_3_0")
    else:
        keys.append("expected_total_over_3_0")
    if outcomes["btts_yes"]:
        keys.append("btts_yes_market")
    else:
        keys.append("btts_no_market")
    if outcomes["lambda_gap"] >= 1.0:
        keys.append("large_lambda_gap")
    else:
        keys.append("small_lambda_gap")
    if row.entropy >= 2.0:
        keys.append("high_entropy")
    else:
        keys.append("low_entropy")
    if outcomes["score_bucket"] == "HIGH_SCORE_TAIL":
        keys.append("high_score_tail_actual")
    return keys
