"""PHASE ECSE-X2-M1 — Backtest baseline vs M1 and special 1-1 quadrant analysis."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from worldcup_predictor.research.ecse_exact_score_backtest import (
    BucketAccumulator,
    FixtureEval,
    _evaluate_fixture,
    distribution_stream_sql,
    quality_bucket,
    run_exact_score_backtest,
)
from worldcup_predictor.research.ecse_x2_m1.constants import (
    SPECIAL_BTTS_YES_MIN,
    SPECIAL_UNDER_25_MIN,
    TABLE_NAME,
)
from worldcup_predictor.research.ecse_x2_m1.constants import BASELINE_TABLE

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

M1_META_SQL = f"""
    SELECT DISTINCT
        registry_fixture_id,
        p_btts_yes,
        p_over_25,
        dominant_quadrant,
        market_source
    FROM {TABLE_NAME}
"""


@dataclass
class RankComparison:
    registry_fixture_id: int
    actual: str
    baseline_rank: int
    m1_rank: int
    baseline_prob: float
    m1_prob: float
    p_btts_yes: float | None
    p_under_25: float | None


def _load_m1_meta(conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in conn.execute(M1_META_SQL):
        fid = int(row["registry_fixture_id"])
        p_over = row["p_over_25"]
        out[fid] = {
            "p_btts_yes": row["p_btts_yes"],
            "p_over_25": p_over,
            "p_under_25": (1.0 - float(p_over)) if p_over is not None else None,
            "dominant_quadrant": row["dominant_quadrant"],
            "market_source": row["market_source"],
        }
    return out


def _evaluate_stream(
    conn: sqlite3.Connection,
    table: str,
    meta_by_id: dict[int, dict[str, Any]],
) -> list[FixtureEval]:
    evaluations: list[FixtureEval] = []
    current_id: int | None = None
    current_dist: list[dict[str, Any]] = []

    for row in conn.execute(distribution_stream_sql(table)):
        fid = int(row["registry_fixture_id"])
        if current_id is not None and fid != current_id:
            ev = _evaluate_fixture(meta_by_id.get(current_id, {}), current_dist)
            if ev:
                evaluations.append(ev)
            current_dist = []
        current_id = fid
        current_dist.append(dict(row))

    if current_id is not None and current_dist:
        ev = _evaluate_fixture(meta_by_id.get(current_id, {}), current_dist)
        if ev:
            evaluations.append(ev)
    return evaluations


def _confidence_bucket(p_btts_yes: float | None, p_over: float | None) -> str:
    if p_btts_yes is None or p_over is None:
        return "unknown"
    spread = max(p_btts_yes, 1 - p_btts_yes, p_over, 1 - p_over)
    if spread >= 0.62:
        return "high_ge_62"
    if spread >= 0.55:
        return "med_55_62"
    return "low_lt_55"


def run_m1_comparison_backtest(conn: sqlite3.Connection) -> dict[str, Any]:
    """Compare Poisson baseline table vs M1 filtered table."""
    baseline = run_exact_score_backtest(
        conn,
        distribution_table=BASELINE_TABLE,
        distribution_method="ECSE-1D-B-v1",
        full_breakdown=True,
    )
    m1 = run_exact_score_backtest(
        conn,
        distribution_table=TABLE_NAME,
        distribution_method="ECSE-X2-M1-v1",
        full_breakdown=True,
    )

    from worldcup_predictor.research.ecse_exact_score_backtest import compare_backtest_summaries

    comparison = compare_backtest_summaries(baseline, m1)
    comparison["label"] = "m1_minus_baseline"
    comparison["delta"] = comparison.get("delta_dc_minus_poisson", {})
    comparison["baseline_table"] = BASELINE_TABLE
    comparison["m1_table"] = TABLE_NAME

    meta_rows = [dict(r) for r in conn.execute(FIXTURE_META_SQL)]
    meta_by_id = {int(m["registry_fixture_id"]): m for m in meta_rows}
    m1_meta = _load_m1_meta(conn)

    baseline_evals = _evaluate_stream(conn, BASELINE_TABLE, meta_by_id)
    m1_evals = _evaluate_stream(conn, TABLE_NAME, meta_by_id)
    m1_by_id = {ev.registry_fixture_id: ev for ev in m1_evals}

    by_quadrant: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)
    by_confidence: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)
    by_quality: dict[str, BucketAccumulator] = defaultdict(BucketAccumulator)

    rank_shifts: list[RankComparison] = []
    for bev in baseline_evals:
        mev = m1_by_id.get(bev.registry_fixture_id)
        if not mev:
            continue
        mm = m1_meta.get(bev.registry_fixture_id, {})
        quad = str(mm.get("dominant_quadrant") or "unknown")
        by_quadrant[quad].add(mev)
        by_confidence[_confidence_bucket(mm.get("p_btts_yes"), mm.get("p_over_25"))].add(mev)
        by_quality[quality_bucket(bev.data_quality_score)].add(mev)

        rank_shifts.append(
            RankComparison(
                registry_fixture_id=bev.registry_fixture_id,
                actual=bev.actual,
                baseline_rank=bev.actual_rank,
                m1_rank=mev.actual_rank,
                baseline_prob=bev.prob_actual,
                m1_prob=mev.prob_actual,
                p_btts_yes=mm.get("p_btts_yes"),
                p_under_25=mm.get("p_under_25"),
            )
        )

    special = [
        rc
        for rc in rank_shifts
        if (rc.p_btts_yes or 0) > SPECIAL_BTTS_YES_MIN
        and (rc.p_under_25 or 0) > SPECIAL_UNDER_25_MIN
    ]
    special_n = len(special)
    special_11_hits = sum(1 for rc in special if rc.actual == "1-1")
    special_11_baseline_top1 = sum(
        1 for rc in special if rc.actual == "1-1" and rc.baseline_rank == 1
    )
    special_11_m1_top1 = sum(1 for rc in special if rc.actual == "1-1" and rc.m1_rank == 1)
    special_11_baseline_avg_rank = (
        sum(rc.baseline_rank for rc in special if rc.actual == "1-1") / max(special_11_hits, 1)
    )
    special_11_m1_avg_rank = (
        sum(rc.m1_rank for rc in special if rc.actual == "1-1") / max(special_11_hits, 1)
    )
    rank_improved = sum(1 for rc in rank_shifts if rc.m1_rank < rc.baseline_rank)
    rank_worsened = sum(1 for rc in rank_shifts if rc.m1_rank > rc.baseline_rank)

    success_threshold = _evaluate_success_threshold(comparison["delta"])

    return {
        "phase": "ECSE-X2-M1",
        "baseline": baseline,
        "m1": m1,
        "comparison": comparison,
        "by_quadrant": {k: v.summary() for k, v in sorted(by_quadrant.items())},
        "by_confidence_bucket": {k: v.summary() for k, v in sorted(by_confidence.items())},
        "by_data_quality_bucket_m1": {k: v.summary() for k, v in sorted(by_quality.items())},
        "rank_shift": {
            "improved": rank_improved,
            "worsened": rank_worsened,
            "unchanged": len(rank_shifts) - rank_improved - rank_worsened,
        },
        "special_yes_under_quadrant": {
            "criteria": f"btts_yes>{SPECIAL_BTTS_YES_MIN} and under_25>{SPECIAL_UNDER_25_MIN}",
            "fixtures": special_n,
            "actual_1_1_hits": special_11_hits,
            "actual_1_1_hit_rate_pct": round(100.0 * special_11_hits / max(special_n, 1), 4),
            "baseline_1_1_top1_when_actual": special_11_baseline_top1,
            "m1_1_1_top1_when_actual": special_11_m1_top1,
            "baseline_1_1_avg_rank_when_actual": round(special_11_baseline_avg_rank, 3),
            "m1_1_1_avg_rank_when_actual": round(special_11_m1_avg_rank, 3),
        },
        "success_threshold": success_threshold,
    }


def _evaluate_success_threshold(delta: dict[str, Any]) -> dict[str, Any]:
    d_top1 = float(delta.get("top1_hit_rate_pct", 0))
    d_top3 = float(delta.get("top3_hit_rate_pct", 0))
    d_logloss = float(delta.get("avg_log_loss", 0))
    met = []
    if d_top1 >= 0.5:
        met.append("top1_ge_0_5pp")
    if d_top3 >= 1.0:
        met.append("top3_ge_1_0pp")
    if d_logloss < -0.0005:
        met.append("log_loss_improved")
    return {
        "top1_delta_pp": d_top1,
        "top3_delta_pp": d_top3,
        "log_loss_delta": d_logloss,
        "criteria_met": met,
        "passed": len(met) > 0,
    }
