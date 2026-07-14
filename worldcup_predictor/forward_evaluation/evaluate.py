"""Phase 7B Parts I/J — Market and exact-score rank evaluation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.forward_evaluation.constants import (
    EVAL_COMPLETE,
    HIT,
    MISS,
    NOT_EVALUATED_UNAVAILABLE,
    UNAVAILABLE,
)
from worldcup_predictor.forward_evaluation.context import build_prediction_context


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _norm_sel(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).lower().strip().replace(" ", "_")
    mapping = {
        "home": "home_win",
        "away": "away_win",
        "1": "home_win",
        "x": "draw",
        "2": "away_win",
        "yes": "yes",
        "no": "no",
        "over": "over_2_5",
        "under": "under_2_5",
        "over_2.5": "over_2_5",
        "under_2.5": "under_2_5",
    }
    return mapping.get(text, text)


def _compare(pred: str | None, actual: str | None) -> str:
    if pred is None or actual is None:
        return UNAVAILABLE
    p = _norm_sel(pred)
    a = _norm_sel(actual)
    if p is None or a is None:
        return UNAVAILABLE
    return HIT if p == a else MISS


def _market_hit(
    pred: str | None,
    actual: str | None,
    *,
    execution_status: str | None = None,
) -> str:
    if execution_status and str(execution_status).upper() in {"UNAVAILABLE", "NOT_AVAILABLE", "SKIPPED"}:
        return NOT_EVALUATED_UNAVAILABLE
    if not pred:
        return NOT_EVALUATED_UNAVAILABLE
    return _compare(pred, actual)


def _rank_hits(actual_score: str, ranks: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(ranks, key=lambda r: int(r["rank"]))
    scores = [str(r["score"]) for r in ordered]
    top1 = HIT if scores and scores[0] == actual_score else MISS if scores else UNAVAILABLE
    top3 = HIT if actual_score in scores[:3] else MISS if scores else UNAVAILABLE
    top5 = HIT if actual_score in scores[:5] else MISS if scores else UNAVAILABLE
    actual_rank = "OUTSIDE_TOP5"
    prob = None
    for row in ordered:
        if str(row["score"]) == actual_score:
            actual_rank = str(int(row["rank"]))
            prob = row.get("probability")
            break
    return {
        "ecse_top1_hit": top1,
        "ecse_top3_hit": top3,
        "ecse_top5_hit": top5,
        "actual_score_rank": actual_rank,
        "actual_score_probability": prob,
    }


def evaluate_frozen_prediction(
    eval_conn: sqlite3.Connection,
    *,
    prediction_id: str,
    prod_conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    existing = eval_conn.execute(
        "SELECT prediction_id FROM market_evaluations WHERE prediction_id=?",
        (prediction_id,),
    ).fetchone()
    if existing:
        return {"evaluated": False, "reason": "already_evaluated", "prediction_id": prediction_id}

    frozen = eval_conn.execute(
        "SELECT * FROM frozen_predictions WHERE prediction_id=?", (prediction_id,)
    ).fetchone()
    if not frozen:
        return {"evaluated": False, "reason": "prediction_not_found", "prediction_id": prediction_id}
    frozen = dict(frozen)
    fid = int(frozen["fixture_id"])

    actual = eval_conn.execute("SELECT * FROM actual_results WHERE fixture_id=?", (fid,)).fetchone()
    if not actual:
        return {"evaluated": False, "reason": "result_pending", "prediction_id": prediction_id}
    actual = dict(actual)

    ranks = [
        dict(r)
        for r in eval_conn.execute(
            "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
            (prediction_id,),
        ).fetchall()
    ]
    rank_eval = _rank_hits(str(actual["actual_score"]), ranks)

    wde_hit = _compare(frozen.get("wde_decision"), actual.get("actual_1x2"))
    ft_hit = _compare(frozen.get("ft_marginal_direction"), actual.get("actual_1x2"))
    eff_hit = _compare(frozen.get("effective_1x2"), actual.get("actual_1x2"))
    btts_hit = _market_hit(
        frozen.get("btts_prediction"),
        actual.get("actual_btts"),
        execution_status=frozen.get("btts_execution_status"),
    )
    ou_hit = _market_hit(
        frozen.get("ou25_prediction"),
        actual.get("actual_ou25"),
        execution_status=frozen.get("ou_execution_status"),
    )

    from worldcup_predictor.forward_evaluation.result_record import EVALUATION_VERSION

    eval_conn.execute(
        """
        INSERT INTO market_evaluations (
            prediction_id, fixture_id, wde_hit, ft_marginal_hit, effective_1x2_hit,
            btts_hit, ou25_hit, ecse_top1_hit, ecse_top3_hit, ecse_top5_hit,
            actual_score_rank, actual_score_probability, evaluation_timestamp,
            prediction_scope, validation_tier, content_hash, result_content_hash,
            evaluation_version, evaluator_source, eligibility_class,
            wde_evaluation_status, btts_evaluation_status, ou_evaluation_status,
            ft_marginal_evaluation_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prediction_id,
            fid,
            wde_hit,
            ft_hit,
            eff_hit,
            btts_hit,
            ou_hit,
            rank_eval["ecse_top1_hit"],
            rank_eval["ecse_top3_hit"],
            rank_eval["ecse_top5_hit"],
            rank_eval["actual_score_rank"],
            rank_eval["actual_score_probability"],
            _utc_now(),
            frozen.get("prediction_scope"),
            frozen.get("validation_tier"),
            frozen.get("content_hash"),
            actual.get("result_content_hash"),
            EVALUATION_VERSION,
            "forward_evaluation.evaluate",
            None,
            "EVALUATED" if wde_hit in (HIT, MISS) else NOT_EVALUATED_UNAVAILABLE,
            "EVALUATED" if btts_hit in (HIT, MISS) else btts_hit,
            "EVALUATED" if ou_hit in (HIT, MISS) else ou_hit,
            "EVALUATED" if ft_hit in (HIT, MISS) else NOT_EVALUATED_UNAVAILABLE,
        ),
    )
    ctx = build_prediction_context({**frozen, **rank_eval, "rank_1_score": ranks[0]["score"] if ranks else None})
    eval_conn.execute(
        """
        INSERT OR REPLACE INTO prediction_context (
            prediction_id, competition, tier, odds_regime, entropy_bucket, top3_mass_bucket,
            top5_mass_bucket, conflict_class, market_agreement_class, data_quality_class,
            freshness_class, bookmaker_count_bucket, lambda_bucket, favorite_class
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prediction_id,
            ctx.get("competition"),
            ctx.get("tier"),
            ctx.get("odds_regime"),
            ctx.get("entropy_bucket"),
            ctx.get("top3_mass_bucket"),
            ctx.get("top5_mass_bucket"),
            ctx.get("conflict_class"),
            ctx.get("market_agreement_class"),
            ctx.get("data_quality_class"),
            ctx.get("freshness_class"),
            ctx.get("bookmaker_count_bucket"),
            ctx.get("lambda_bucket"),
            ctx.get("favorite_class"),
        ),
    )
    eval_conn.execute(
        "UPDATE frozen_predictions SET evaluation_status=? WHERE prediction_id=?",
        (EVAL_COMPLETE, prediction_id),
    )
    eval_conn.commit()
    return {
        "evaluated": True,
        "prediction_id": prediction_id,
        "fixture_id": fid,
        "evaluation_version": EVALUATION_VERSION,
        **rank_eval,
        "wde_hit": wde_hit,
        "ft_marginal_hit": ft_hit,
        "btts_hit": btts_hit,
        "ou25_hit": ou_hit,
    }


def rank_distribution(eval_conn: sqlite3.Connection, *, days: int | None = None) -> dict[str, int]:
    query = """
        SELECT actual_score_rank, COUNT(*) AS c
        FROM market_evaluations
        WHERE actual_score_rank IS NOT NULL
    """
    params: list[Any] = []
    if days is not None:
        query += " AND evaluation_timestamp >= datetime('now', ?)"
        params.append(f"-{int(days)} days")
    query += " GROUP BY actual_score_rank"
    rows = eval_conn.execute(query, params).fetchall()
    out = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "OUTSIDE_TOP5": 0}
    for row in rows:
        key = str(row["actual_score_rank"])
        out[key] = int(row["c"])
    return out
