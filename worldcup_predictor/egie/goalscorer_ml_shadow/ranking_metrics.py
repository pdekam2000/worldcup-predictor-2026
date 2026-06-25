"""Per-fixture ranking metrics for goalscorer ML shadow."""

from __future__ import annotations

import pandas as pd

from worldcup_predictor.egie.goalscorer_ml_shadow.models import RankingMetrics, TARGETS


def rank_by_score(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    out = df.copy()
    out["rank"] = (
        out.groupby("sportmonks_fixture_id")[score_col]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    return out


def compute_ranking_metrics(
    df: pd.DataFrame,
    *,
    score_col: str,
    target_col: str,
    market: str,
    model: str,
    multi_positive: bool = True,
) -> RankingMetrics:
    metrics = RankingMetrics(market=market, model=model)
    if df.empty or score_col not in df.columns:
        return metrics

    ranked = rank_by_score(df, score_col)
    fixtures = ranked["sportmonks_fixture_id"].unique()
    top1 = top3 = top5 = 0
    p1 = p3 = p5 = 0
    mrr_sum = 0.0
    mrr_n = 0
    evaluated = 0

    for fid in fixtures:
        grp = ranked[ranked["sportmonks_fixture_id"] == fid].sort_values("rank")
        positives = grp[grp[target_col] == 1]["player_id"].astype(int).tolist()
        if not positives and not multi_positive:
            continue
        evaluated += 1
        top_ids = grp.head(5)["player_id"].astype(int).tolist()

        if multi_positive:
            if any(pid in positives for pid in top_ids[:1]):
                top1 += 1
            if any(pid in positives for pid in top_ids[:3]):
                top3 += 1
            if any(pid in positives for pid in top_ids[:5]):
                top5 += 1
            p1 += sum(1 for pid in top_ids[:1] if pid in positives)
            p3 += sum(1 for pid in top_ids[:3] if pid in positives)
            p5 += sum(1 for pid in top_ids[:5] if pid in positives)
        else:
            if not positives:
                continue
            actual = positives[0]
            rank = int(grp[grp["player_id"].astype(int) == actual]["rank"].iloc[0])
            if rank == 1:
                top1 += 1
            if rank <= 3:
                top3 += 1
            if rank <= 5:
                top5 += 1
            p1 += 1 if rank == 1 else 0
            p3 += 1 if rank <= 3 else 0
            p5 += 1 if rank <= 5 else 0
            mrr_sum += 1.0 / rank
            mrr_n += 1

    if evaluated == 0:
        return metrics

    metrics.fixtures_evaluated = evaluated
    metrics.top1_hit = round(top1 / evaluated, 4)
    metrics.top3_hit = round(top3 / evaluated, 4)
    metrics.top5_hit = round(top5 / evaluated, 4)
    metrics.precision_at_1 = round(p1 / evaluated, 4)
    metrics.precision_at_3 = round(p3 / (evaluated * 3), 4)
    metrics.precision_at_5 = round(p5 / (evaluated * 5), 4)
    metrics.recall_at_3 = metrics.top3_hit
    metrics.recall_at_5 = metrics.top5_hit
    if mrr_n:
        metrics.mrr = round(mrr_sum / mrr_n, 4)
    return metrics


def evaluate_all_markets(
    test_df: pd.DataFrame,
    score_columns: dict[str, str],
) -> list[RankingMetrics]:
    results: list[RankingMetrics] = []
    for market, target_col in TARGETS.items():
        multi = market == "anytime"
        for model, col in score_columns.items():
            results.append(
                compute_ranking_metrics(
                    test_df,
                    score_col=col,
                    target_col=target_col,
                    market=market,
                    model=model,
                    multi_positive=multi,
                )
            )
    return results
