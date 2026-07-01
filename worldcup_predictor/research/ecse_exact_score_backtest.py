"""PHASE ECSE-1E — Exact score distribution backtest (evaluation only)."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_score_distribution import (
    MAX_GOALS,
    METHOD_VERSION as DIST_METHOD,
    OTHER_SCORELINE,
    generate_score_distribution,
    poisson_pmf,
    scoreline_label,
)

BACKTEST_VERSION = "ECSE-1E-v1"
LOG_LOSS_FLOOR = 1e-12
EXPECTED_LAMBDA_ROWS = 168_233

FIXTURE_META_SQL = """
    SELECT
        l.registry_fixture_id,
        l.lambda_home,
        l.lambda_away,
        l.lambda_total,
        l.data_quality_score,
        r.home_goals,
        r.away_goals,
        d.league,
        d.season,
        d.ft_home_closing,
        d.ft_away_closing
    FROM ecse_lambda_features l
    INNER JOIN historical_fixture_results r
        ON r.registry_fixture_id = l.registry_fixture_id
    LEFT JOIN ecse_training_dataset d
        ON d.registry_fixture_id = l.registry_fixture_id
    ORDER BY l.registry_fixture_id
"""

DISTRIBUTION_TABLE_POISSON = "ecse_score_distributions"
DISTRIBUTION_TABLE_DC = "ecse_score_distributions_dc"
DISTRIBUTION_TABLE_M1 = "ecse_score_distributions_m1"
ALLOWED_DISTRIBUTION_TABLES = frozenset(
    {DISTRIBUTION_TABLE_POISSON, DISTRIBUTION_TABLE_DC, DISTRIBUTION_TABLE_M1}
)

DISTRIBUTION_STREAM_SQL = f"""
    SELECT
        registry_fixture_id,
        scoreline,
        rank,
        probability,
        home_goals,
        away_goals
    FROM {DISTRIBUTION_TABLE_POISSON}
    ORDER BY registry_fixture_id, rank
"""


def distribution_stream_sql(table: str) -> str:
    if table not in ALLOWED_DISTRIBUTION_TABLES:
        raise ValueError(f"unsupported distribution table: {table}")
    return f"""
        SELECT
            registry_fixture_id,
            scoreline,
            rank,
            probability,
            home_goals,
            away_goals
        FROM {table}
        ORDER BY registry_fixture_id, rank
    """


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")



def actual_scoreline(home_goals: int, away_goals: int) -> str:
    if home_goals > MAX_GOALS or away_goals > MAX_GOALS:
        return OTHER_SCORELINE
    return scoreline_label(home_goals, away_goals)


def quality_bucket(score: float) -> str:
    if score < 0.40:
        return "low_lt_0_40"
    if score < 0.60:
        return "med_0_40_0_60"
    return "high_gte_0_60"


def lambda_total_bucket(lambda_total: float) -> str:
    if lambda_total < 2.5:
        return "low_lt_2_5"
    if lambda_total <= 3.5:
        return "med_2_5_3_5"
    return "high_gt_3_5"


def odds_band(ft_home: float | None, ft_away: float | None) -> str:
    odds = [o for o in (ft_home, ft_away) if o is not None and o >= 1.0]
    if not odds:
        return "unknown"
    fav = min(odds)
    if fav < 1.80:
        return "favorite_lt_1_80"
    if fav <= 2.50:
        return "mid_1_80_2_50"
    return "longshot_gt_2_50"


def multiclass_brier(prob_by_scoreline: dict[str, float], actual: str) -> float:
    return sum((p - (1.0 if sl == actual else 0.0)) ** 2 for sl, p in prob_by_scoreline.items())


@dataclass
class FixtureEval:
    registry_fixture_id: int
    actual: str
    actual_home: int
    actual_away: int
    predicted_top1: str
    actual_rank: int
    prob_actual: float
    log_loss: float
    brier: float
    top1_hit: bool
    top3_hit: bool
    top5_hit: bool
    top10_hit: bool
    league: str | None
    season: str | None
    data_quality_score: float
    lambda_total: float
    odds_band: str


@dataclass
class BucketAccumulator:
    n: int = 0
    top1: int = 0
    top3: int = 0
    top5: int = 0
    top10: int = 0
    prob_actual_sum: float = 0.0
    log_loss_sum: float = 0.0
    brier_sum: float = 0.0

    def add(self, ev: FixtureEval) -> None:
        self.n += 1
        self.top1 += int(ev.top1_hit)
        self.top3 += int(ev.top3_hit)
        self.top5 += int(ev.top5_hit)
        self.top10 += int(ev.top10_hit)
        self.prob_actual_sum += ev.prob_actual
        self.log_loss_sum += ev.log_loss
        self.brier_sum += ev.brier

    def summary(self) -> dict[str, Any]:
        if self.n == 0:
            return {"n": 0}
        return {
            "n": self.n,
            "top1_hit_rate_pct": round(100.0 * self.top1 / self.n, 4),
            "top3_hit_rate_pct": round(100.0 * self.top3 / self.n, 4),
            "top5_hit_rate_pct": round(100.0 * self.top5 / self.n, 4),
            "top10_hit_rate_pct": round(100.0 * self.top10 / self.n, 4),
            "avg_prob_actual": round(self.prob_actual_sum / self.n, 6),
            "avg_log_loss": round(self.log_loss_sum / self.n, 6),
            "avg_brier": round(self.brier_sum / self.n, 6),
        }


def _evaluate_fixture(
    meta: dict[str, Any],
    dist_rows: list[dict[str, Any]],
) -> FixtureEval | None:
    if not dist_rows:
        return None
    prob_map = {r["scoreline"]: float(r["probability"]) for r in dist_rows}
    rank_map = {r["scoreline"]: int(r["rank"]) for r in dist_rows}
    top1 = min(dist_rows, key=lambda r: int(r["rank"]))["scoreline"]

    actual_h = int(meta["home_goals"])
    actual_a = int(meta["away_goals"])
    actual = actual_scoreline(actual_h, actual_a)
    prob_actual = prob_map.get(actual, LOG_LOSS_FLOOR)
    prob_actual = max(prob_actual, LOG_LOSS_FLOOR)
    actual_rank = rank_map.get(actual, 999)

    return FixtureEval(
        registry_fixture_id=int(meta["registry_fixture_id"]),
        actual=actual,
        actual_home=actual_h,
        actual_away=actual_a,
        predicted_top1=top1,
        actual_rank=actual_rank,
        prob_actual=prob_actual,
        log_loss=-math.log(prob_actual),
        brier=multiclass_brier(prob_map, actual),
        top1_hit=actual_rank == 1,
        top3_hit=actual_rank <= 3,
        top5_hit=actual_rank <= 5,
        top10_hit=actual_rank <= 10,
        league=meta.get("league"),
        season=meta.get("season"),
        data_quality_score=float(meta["data_quality_score"]),
        lambda_total=float(meta["lambda_total"]),
        odds_band=odds_band(meta.get("ft_home_closing"), meta.get("ft_away_closing")),
    )


def _baseline_historical_mode(conn: sqlite3.Connection, fixture_ids: set[int]) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT home_goals || '-' || away_goals AS scoreline, COUNT(1) AS c
        FROM historical_fixture_results r
        INNER JOIN ecse_lambda_features l ON l.registry_fixture_id = r.registry_fixture_id
        GROUP BY scoreline
        ORDER BY c DESC
        LIMIT 1
        """
    ).fetchone()
    mode_score = row[0] if row else "1-1"
    hits = conn.execute(
        """
        SELECT COUNT(1) FROM historical_fixture_results r
        INNER JOIN ecse_lambda_features l ON l.registry_fixture_id = r.registry_fixture_id
        WHERE r.home_goals || '-' || r.away_goals = ?
        """,
        (mode_score,),
    ).fetchone()[0]
    n = len(fixture_ids)
    return {
        "name": "historical_mode",
        "predicted_score": mode_score,
        "top1_hit_rate_pct": round(100.0 * hits / max(n, 1), 4),
        "n": n,
    }


def _baseline_naive_poisson(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT AVG(lambda_total) / 2.0 AS half
        FROM ecse_lambda_features
        """
    ).fetchone()
    half = float(row[0] or 1.59)
    dist = generate_score_distribution(half, half)
    top1 = dist[0]["scoreline"]
    return {
        "name": "naive_poisson_global_avg",
        "lambda_home": round(half, 4),
        "lambda_away": round(half, 4),
        "predicted_score": top1,
    }


def _baseline_market_favorite(evaluations: list[FixtureEval], meta_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Heuristic favorite score from available 1X2 closing odds."""
    hits = 0
    n = 0
    for ev in evaluations:
        meta = meta_by_id.get(ev.registry_fixture_id, {})
        fh = meta.get("ft_home_closing")
        fa = meta.get("ft_away_closing")
        pred: str | None = None
        if fh is not None and fa is not None:
            n += 1
            if fh + 0.15 < fa:
                pred = "1-0"
            elif fa + 0.15 < fh:
                pred = "0-1"
            else:
                pred = "1-1"
        elif fh is not None:
            n += 1
            pred = "1-0" if fh < 2.0 else "1-1"
        elif fa is not None:
            n += 1
            pred = "0-1" if fa < 2.0 else "1-1"
        else:
            continue
        if ev.actual == pred:
            hits += 1
    return {
        "name": "market_favorite_score_heuristic",
        "top1_hit_rate_pct": round(100.0 * hits / max(n, 1), 4),
        "n": n,
        "rules": "both odds: fav 1-0/0-1/1-1; single odds: short 1-0 or 0-1 else 1-1",
    }


def _miss_analysis(evaluations: list[FixtureEval]) -> dict[str, Any]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    low_00_10 = 0
    high_00_10_n = 0
    over3_pred = 0
    over3_pred_miss = 0

    for ev in evaluations:
        pair_counts[(ev.predicted_top1, ev.actual)] += 1
        if ev.actual in ("0-0", "1-0", "0-1"):
            high_00_10_n += 1
            if ev.actual_rank > 5 or ev.prob_actual < 0.05:
                low_00_10 += 1
        pred_h, pred_a = _parse_score(ev.predicted_top1)
        if pred_h is not None and (pred_h + pred_a) >= 3:
            over3_pred += 1
            if (ev.actual_home + ev.actual_away) < 3:
                over3_pred_miss += 1

    top_pairs = [
        {"predicted": p, "actual": a, "count": c}
        for (p, a), c in pair_counts.most_common(15)
    ]
    return {
        "top_predicted_actual_pairs": top_pairs,
        "predicted_1_1_actual_2_1": pair_counts.get(("1-1", "2-1"), 0),
        "predicted_2_1_actual_1_1": pair_counts.get(("2-1", "1-1"), 0),
        "underestimate_low_score_rate_pct": round(100.0 * low_00_10 / max(high_00_10_n, 1), 4),
        "underestimate_low_score_n": high_00_10_n,
        "overestimate_3plus_when_actual_under_3_pct": round(
            100.0 * over3_pred_miss / max(over3_pred, 1), 4
        ),
        "overestimate_3plus_predictions": over3_pred,
    }


LOW_SCORE_ACTUALS = frozenset({"0-0", "1-0", "0-1", "1-1"})
DC_LOW_SCORE_ACTUALS = LOW_SCORE_ACTUALS


def _parse_score(scoreline: str) -> tuple[int | None, int | None]:
    if scoreline == OTHER_SCORELINE or "-" not in scoreline:
        return None, None
    h, a = scoreline.split("-", 1)
    return int(h), int(a)


def _low_score_metrics(evaluations: list[FixtureEval]) -> dict[str, Any]:
    acc = BucketAccumulator()
    for ev in evaluations:
        if ev.actual in LOW_SCORE_ACTUALS:
            acc.add(ev)
    return acc.summary()


def run_exact_score_backtest(
    conn: sqlite3.Connection,
    *,
    distribution_table: str = DISTRIBUTION_TABLE_POISSON,
    distribution_method: str | None = None,
    full_breakdown: bool = True,
) -> dict[str, Any]:
    if distribution_method is None:
        distribution_method = (
            "ECSE-1D-B-v1" if distribution_table == DISTRIBUTION_TABLE_POISSON else "ECSE-1F-v1"
        )

    meta_rows = [dict(r) for r in conn.execute(FIXTURE_META_SQL)]
    meta_by_id = {int(m["registry_fixture_id"]): m for m in meta_rows}

    evaluations: list[FixtureEval] = []
    current_id: int | None = None
    current_dist: list[dict[str, Any]] = []

    for row in conn.execute(distribution_stream_sql(distribution_table)):
        fid = int(row["registry_fixture_id"])
        if current_id is not None and fid != current_id:
            ev = _evaluate_fixture(meta_by_id[current_id], current_dist)
            if ev:
                evaluations.append(ev)
            current_dist = []
        current_id = fid
        current_dist.append(dict(row))

    if current_id is not None and current_dist:
        ev = _evaluate_fixture(meta_by_id[current_id], current_dist)
        if ev:
            evaluations.append(ev)

    overall = BucketAccumulator()
    by_league: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)
    by_season: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)
    by_quality: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)
    by_lambda: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)
    by_odds: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)

    for ev in evaluations:
        overall.add(ev)
        if not full_breakdown:
            continue
        by_league[ev.league or "unknown"].add(ev)
        by_season[str(ev.season or "unknown")].add(ev)
        by_quality[quality_bucket(ev.data_quality_score)].add(ev)
        by_lambda[lambda_total_bucket(ev.lambda_total)].add(ev)
        by_odds[ev.odds_band].add(ev)

    fixture_ids = {ev.registry_fixture_id for ev in evaluations}
    baselines: list[dict[str, Any]] = []
    if full_breakdown and distribution_table == DISTRIBUTION_TABLE_POISSON:
        baselines = [
            _baseline_historical_mode(conn, fixture_ids),
            _baseline_naive_poisson(conn),
            _baseline_market_favorite(evaluations, meta_by_id),
        ]
        naive = baselines[1]
        naive_hits = sum(1 for ev in evaluations if ev.actual == naive["predicted_score"])
        naive["top1_hit_rate_pct"] = round(100.0 * naive_hits / max(len(evaluations), 1), 4)

    league_top = []
    if full_breakdown:
        league_top = sorted(
            ((lg, acc.summary()) for lg, acc in by_league.items()),
            key=lambda x: x[1].get("n", 0),
            reverse=True,
        )[:20]

    result: dict[str, Any] = {
        "backtest_version": BACKTEST_VERSION,
        "distribution_table": distribution_table,
        "distribution_method": distribution_method,
        "generated_at_utc": _utc_now(),
        "fixtures_evaluated": len(evaluations),
        "overall": overall.summary(),
        "low_score_actuals": _low_score_metrics(evaluations),
        "miss_analysis": _miss_analysis(evaluations),
    }
    if full_breakdown:
        result.update(
            {
                "baselines": baselines,
                "by_season": {k: v.summary() for k, v in sorted(by_season.items())},
                "by_data_quality_bucket": {k: v.summary() for k, v in sorted(by_quality.items())},
                "by_lambda_total_bucket": {k: v.summary() for k, v in sorted(by_lambda.items())},
                "by_odds_band": {k: v.summary() for k, v in sorted(by_odds.items())},
                "by_league_top20": {lg: stats for lg, stats in league_top},
            }
        )
    return result


def compare_backtest_summaries(poisson: dict[str, Any], dc: dict[str, Any]) -> dict[str, Any]:
    """Delta DC minus Poisson (positive = DC improvement for hit rates / prob)."""
    p = poisson["overall"]
    d = dc["overall"]
    pl = poisson.get("low_score_actuals", {})
    dl = dc.get("low_score_actuals", {})

    def delta(key: str, *, lower_is_better: bool = False) -> float:
        pv = float(p.get(key, 0))
        dv = float(d.get(key, 0))
        diff = round(dv - pv, 6)
        if lower_is_better:
            improved = diff < 0
        else:
            improved = diff > 0
        return diff

    metrics = {
        "top1_hit_rate_pct": delta("top1_hit_rate_pct"),
        "top3_hit_rate_pct": delta("top3_hit_rate_pct"),
        "top5_hit_rate_pct": delta("top5_hit_rate_pct"),
        "top10_hit_rate_pct": delta("top10_hit_rate_pct"),
        "avg_prob_actual": delta("avg_prob_actual"),
        "avg_log_loss": delta("avg_log_loss", lower_is_better=True),
        "avg_brier": delta("avg_brier", lower_is_better=True),
    }
    low_score = {
        "avg_prob_actual_delta": round(
            float(dl.get("avg_prob_actual", 0)) - float(pl.get("avg_prob_actual", 0)), 6
        ),
        "top1_hit_rate_pct_delta": round(
            float(dl.get("top1_hit_rate_pct", 0)) - float(pl.get("top1_hit_rate_pct", 0)), 4
        ),
    }
    improved_count = sum(
        1
        for k, v in metrics.items()
        if (k in ("avg_log_loss", "avg_brier") and v < 0) or (k not in ("avg_log_loss", "avg_brier") and v > 0)
    )
    verdict = "improved" if improved_count >= 4 else "mixed" if improved_count >= 2 else "degraded"
    return {
        "poisson": p,
        "dixon_coles": d,
        "delta_dc_minus_poisson": metrics,
        "low_score_actuals_delta": low_score,
        "miss_analysis_poisson": poisson.get("miss_analysis", {}),
        "miss_analysis_dc": dc.get("miss_analysis", {}),
        "verdict": verdict,
        "metrics_improved_count": improved_count,
    }


def verify_join_integrity(conn: sqlite3.Connection) -> dict[str, Any]:
    joined = conn.execute(
        """
        SELECT COUNT(DISTINCT d.registry_fixture_id)
        FROM ecse_score_distributions d
        INNER JOIN historical_fixture_results r
            ON r.registry_fixture_id = d.registry_fixture_id
        INNER JOIN ecse_lambda_features l
            ON l.registry_fixture_id = d.registry_fixture_id
        """
    ).fetchone()[0]
    lambda_n = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]
    prob_off = conn.execute(
        """
        SELECT COUNT(1) FROM (
            SELECT registry_fixture_id, ABS(SUM(probability) - 1.0) AS delta
            FROM ecse_score_distributions
            GROUP BY registry_fixture_id
            HAVING delta > 1e-6
        )
        """
    ).fetchone()[0]
    return {
        "joined_fixtures": joined,
        "lambda_rows": lambda_n,
        "join_coverage_pct": round(100.0 * joined / max(lambda_n, 1), 4),
        "fixtures_prob_sum_off": prob_off,
    }


def verify_hit_rate_sample(conn: sqlite3.Connection, sample_id: int = 1) -> dict[str, Any]:
    meta = dict(
        conn.execute(
            """
            SELECT l.registry_fixture_id, r.home_goals, r.away_goals
            FROM ecse_lambda_features l
            INNER JOIN historical_fixture_results r
                ON r.registry_fixture_id = l.registry_fixture_id
            WHERE l.registry_fixture_id = ?
            """,
            (sample_id,),
        ).fetchone()
    )
    rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT scoreline, rank, probability
            FROM ecse_score_distributions
            WHERE registry_fixture_id = ?
            ORDER BY rank
            """,
            (sample_id,),
        )
    ]
    actual = actual_scoreline(int(meta["home_goals"]), int(meta["away_goals"]))
    rank_map = {r["scoreline"]: int(r["rank"]) for r in rows}
    prob_map = {r["scoreline"]: float(r["probability"]) for r in rows}
    rank = rank_map.get(actual, 999)
    return {
        "registry_fixture_id": sample_id,
        "actual": actual,
        "rank": rank,
        "prob_actual": prob_map.get(actual),
        "top1": rows[0]["scoreline"] if rows else None,
        "top1_hit": rank == 1,
        "top3_hit": rank <= 3,
    }
