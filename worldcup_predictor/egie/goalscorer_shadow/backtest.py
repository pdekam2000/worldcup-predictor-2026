"""Goalscorer shadow backtest — top-k metrics per fixture."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from worldcup_predictor.egie.goalscorer_shadow.models import BacktestReport, TopKMetrics
from worldcup_predictor.egie.goalscorer_shadow.scoring import apply_baseline_scores, naive_uniform_scores, rank_players_per_fixture

MIN_FIXTURES = 30


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _topk_hits(
    ranked: pd.DataFrame,
    *,
    target_col: str,
    score_col: str,
    market: str,
    model: str,
    multi_positive: bool = True,
) -> TopKMetrics:
    metrics = TopKMetrics(market=market, model=model)
    fixtures = ranked["sportmonks_fixture_id"].unique()
    top1 = top3 = top5 = 0
    p1_num = p3_num = p5_num = 0
    mrr_sum = 0.0
    mrr_n = 0
    evaluated = 0

    for fid in fixtures:
        grp = ranked[ranked["sportmonks_fixture_id"] == fid].sort_values("rank")
        if grp.empty:
            continue
        positives = grp[grp[target_col] == 1]["player_id"].astype(int).tolist()
        if not positives and target_col != "target_anytime":
            continue
        if target_col == "target_anytime" and not positives:
            evaluated += 1
            continue
        evaluated += 1

        top_players = grp.head(5)["player_id"].astype(int).tolist()
        if multi_positive:
            if any(pid in positives for pid in top_players[:1]):
                top1 += 1
            if any(pid in positives for pid in top_players[:3]):
                top3 += 1
            if any(pid in positives for pid in top_players[:5]):
                top5 += 1
            p1_num += sum(1 for pid in top_players[:1] if pid in positives)
            p3_num += sum(1 for pid in top_players[:3] if pid in positives)
            p5_num += sum(1 for pid in top_players[:5] if pid in positives)
        else:
            actual = positives[0] if positives else None
            if actual is None:
                continue
            rank_of_actual = int(grp[grp["player_id"].astype(int) == actual]["rank"].iloc[0])
            if rank_of_actual == 1:
                top1 += 1
            if rank_of_actual <= 3:
                top3 += 1
            if rank_of_actual <= 5:
                top5 += 1
            p1_num += 1 if rank_of_actual == 1 else 0
            p3_num += 1 if rank_of_actual <= 3 else 0
            p5_num += 1 if rank_of_actual <= 5 else 0
            mrr_sum += 1.0 / rank_of_actual
            mrr_n += 1

    if evaluated == 0:
        return metrics

    metrics.fixtures_evaluated = evaluated
    metrics.top1_hit = round(top1 / evaluated, 4)
    metrics.top3_hit = round(top3 / evaluated, 4)
    metrics.top5_hit = round(top5 / evaluated, 4)
    metrics.precision_at_1 = round(p1_num / evaluated, 4)
    metrics.precision_at_3 = round(p3_num / (evaluated * 3), 4)
    metrics.precision_at_5 = round(p5_num / (evaluated * 5), 4)
    if mrr_n:
        metrics.mean_reciprocal_rank = round(mrr_sum / mrr_n, 4)
    metrics.top3_recall = metrics.top3_hit
    metrics.top5_recall = metrics.top5_hit
    return metrics


def feature_importance_proxy(df: pd.DataFrame, score_col: str = "combined_score") -> dict[str, float]:
    """Correlation of features with anytime target as importance proxy."""
    if df.empty or "target_anytime" not in df.columns:
        return {}
    cols = [
        "goals_per_90", "xg_per_90", "starter_probability", "goals_last_5",
        "recent_form_score", "team_strength_proxy", "lineup_status",
    ]
    out: dict[str, float] = {}
    y = df["target_anytime"].astype(float)
    for col in cols:
        if col not in df.columns:
            continue
        if col == "lineup_status":
            x = (df[col] == "starter").astype(float)
        else:
            x = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        if x.std() == 0:
            continue
        out[col] = round(float(np.corrcoef(x, y)[0, 1]), 4)
    return dict(sorted(out.items(), key=lambda kv: abs(kv[1]), reverse=True))


def run_backtest(df: pd.DataFrame) -> BacktestReport:
    scored = apply_baseline_scores(df)
    naive = naive_uniform_scores(scored)
    test = scored[scored["split"] == "test"].copy()
    naive_test = naive[naive["split"] == "test"].copy()
    limitations: list[str] = []

    if test.empty:
        test = scored[scored["split"] == "val"].copy()
        limitations.append("test split empty — used validation split")
    if test.empty:
        test = scored.copy()
        limitations.append("no temporal split — evaluated full sample")

    n_fixtures = int(test["sportmonks_fixture_id"].nunique())
    if n_fixtures < MIN_FIXTURES:
        limitations.append(f"only {n_fixtures} fixtures in eval split (min {MIN_FIXTURES} preferred)")

    models = [
        ("goals_per_90_score", "goals_per_90_baseline"),
        ("xg_per_90_score", "xg_per_90_baseline"),
        ("starter_weighted_score", "starter_weighted_baseline"),
        ("combined_score", "combined_baseline"),
        ("naive_score", "naive_uniform"),
    ]

    anytime: list[TopKMetrics] = []
    first_goal: list[TopKMetrics] = []
    most_likely: list[TopKMetrics] = []

    for score_col, model_name in models:
        base_df = naive_test if score_col == "naive_score" else test
        ranked = rank_players_per_fixture(base_df, score_col)
        anytime.append(_topk_hits(ranked, target_col="target_anytime", score_col=score_col, market="anytime", model=model_name, multi_positive=True))
        first_goal.append(_topk_hits(ranked, target_col="target_first_goal", score_col=score_col, market="first_goal", model=model_name, multi_positive=False))
        most_likely.append(_topk_hits(ranked, target_col="target_most_likely", score_col=score_col, market="most_likely", model=model_name, multi_positive=False))

    importance = feature_importance_proxy(test)

    report = BacktestReport(
        generated_at=_utc_now(),
        split={
            "train": int((scored["split"] == "train").sum()) if "split" in scored.columns else 0,
            "val": int((scored["split"] == "val").sum()) if "split" in scored.columns else 0,
            "test": int((scored["split"] == "test").sum()) if "split" in scored.columns else 0,
            "eval_fixtures": n_fixtures,
        },
        anytime=anytime,
        first_goal=first_goal,
        most_likely=most_likely,
        feature_importance_proxy=importance,
        limitations=limitations,
    )
    report.recommendation = _recommend(report)
    return report


def _recommend(report: BacktestReport) -> str:
    combined = next((m for m in report.anytime if m.model == "combined_baseline"), None)
    naive = next((m for m in report.anytime if m.model == "naive_uniform"), None)
    gp90 = next((m for m in report.anytime if m.model == "goals_per_90_baseline"), None)

    if not combined or combined.fixtures_evaluated < 20:
        return "GOALSCORER_INSUFFICIENT_DATA"

    c_top3 = combined.top3_hit or 0.0
    n_top3 = (naive.top3_hit if naive else 0.0) or 0.0
    g_top3 = (gp90.top3_hit if gp90 else 0.0) or 0.0

    if c_top3 < 0.15:
        return "GOALSCORER_NO_VALUE"
    if c_top3 >= 0.35 and c_top3 > max(n_top3, g_top3) + 0.03:
        return "GOALSCORER_HIGH_VALUE"
    if c_top3 >= 0.22:
        return "GOALSCORER_MEDIUM_VALUE"
    return "GOALSCORER_LOW_VALUE"
