"""Historical replay and value-pick research for goalscorer intelligence."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from worldcup_predictor.egie.goalscorer_intelligence.models import ReplayMetrics


def _mrr_for_group(grp: pd.DataFrame, score_col: str, target_col: str) -> float | None:
    positives = grp[grp[target_col] == 1]["player_id"].astype(int).tolist()
    if not positives:
        return None
    ranked = grp.sort_values(score_col, ascending=False)["player_id"].astype(int).tolist()
    for i, pid in enumerate(ranked, start=1):
        if pid in positives:
            return 1.0 / i
    return 0.0


def fixture_ranking_hits(
    df: pd.DataFrame,
    *,
    score_col: str,
    target_col: str = "target_anytime",
) -> ReplayMetrics:
    top1 = top3 = top5 = 0
    mrr_vals: list[float] = []
    evaluated = 0

    for _, grp in df.groupby("sportmonks_fixture_id"):
        positives = grp[grp[target_col] == 1]["player_id"].astype(int).tolist()
        if not positives:
            continue
        evaluated += 1
        ranked = grp.sort_values(score_col, ascending=False)
        top_ids = ranked.head(5)["player_id"].astype(int).tolist()
        if any(p in positives for p in top_ids[:1]):
            top1 += 1
        if any(p in positives for p in top_ids[:3]):
            top3 += 1
        if any(p in positives for p in top_ids[:5]):
            top5 += 1
        m = _mrr_for_group(grp, score_col, target_col)
        if m is not None:
            mrr_vals.append(m)

    n = evaluated or 1
    return ReplayMetrics(
        market=target_col,
        signal=score_col,
        fixtures_evaluated=evaluated,
        top1_hit=round(top1 / n, 4),
        top3_hit=round(top3 / n, 4),
        top5_hit=round(top5 / n, 4),
        mrr=round(float(np.mean(mrr_vals)), 4) if mrr_vals else None,
    )


def run_historical_replay(df: pd.DataFrame) -> dict[str, Any]:
    """Replay all bridged fixtures across signals and markets."""
    signals = {
        "composite_scorer": "composite_scorer_score",
        "ml_only": "ml_score",
        "odds_only": "odds_implied_anytime",
        "ml_odds_blend": None,
    }
    df = df.copy()
    df["ml_odds_blend"] = 0.6 * df["ml_score"].fillna(0) + 0.4 * df["odds_implied_anytime"].fillna(0)

    markets = {
        "anytime": "target_anytime",
        "first_goal": "target_first_goal",
    }

    results: dict[str, Any] = {"status": "ok", "markets": {}}
    for mkt, target in markets.items():
        sub = df[df[target].notna()] if target in df.columns else df
        if sub.empty:
            results["markets"][mkt] = {"status": "no_rows"}
            continue
        mkt_out: dict[str, Any] = {}
        for name, col in signals.items():
            if col is None:
                col = "ml_odds_blend"
            if col not in sub.columns:
                continue
            mkt_out[name] = fixture_ranking_hits(sub, score_col=col, target_col=target).to_dict()
        results["markets"][mkt] = mkt_out

    # value picks: players with value_gap >= 5 in top ML quartile per fixture
    value_results = run_value_pick_research(df)
    results["value_picks"] = value_results
    return results


def run_value_pick_research(df: pd.DataFrame, *, min_gap: float = 5.0) -> dict[str, Any]:
    """Identify ML >> book picks and measure hit rate vs random disagreement."""
    if df.empty or "value_gap" not in df.columns:
        return {"status": "no_data"}

    picks = df[df["is_value_pick"] == True].copy()  # noqa: E712
    if picks.empty:
        picks = df[df["value_gap"] >= min_gap].copy()

    picks["value_pick_hit"] = picks["target_anytime"].fillna(0).astype(int)

    # random disagreement baseline: players where ML and odds disagree (gap != 0) sampled
    disagree = df[df["value_gap"] != 0].copy()
    random_hit = float(disagree["target_anytime"].mean()) if len(disagree) else 0.0
    pick_hit = float(picks["value_pick_hit"].mean()) if len(picks) else 0.0

    by_tier: dict[str, Any] = {}
    if "confidence_tier" in picks.columns:
        for tier, grp in picks.groupby("confidence_tier"):
            by_tier[str(tier)] = {
                "picks": len(grp),
                "hit_rate": round(float(grp["target_anytime"].mean()), 4) if len(grp) else 0.0,
            }

    return {
        "status": "ok",
        "value_pick_count": len(picks),
        "value_pick_hit_rate": round(pick_hit, 4),
        "random_disagreement_hit_rate": round(random_hit, 4),
        "outperforms_random": pick_hit > random_hit,
        "by_confidence_tier": by_tier,
        "fixtures_with_value_picks": int(picks["sportmonks_fixture_id"].nunique()) if len(picks) else 0,
    }


def build_value_pick_dataset(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "sportmonks_fixture_id",
        "player_id",
        "player_name",
        "team_id",
        "ml_score",
        "ml_rank",
        "odds_rank",
        "value_gap",
        "composite_scorer_score",
        "confidence_tier",
        "target_anytime",
        "target_first_goal",
        "odds_implied_anytime",
    ]
    avail = [c for c in cols if c in df.columns]
    if "is_value_pick" in df.columns:
        picks = df[df["is_value_pick"] == True].copy()  # noqa: E712
    else:
        picks = df[df["value_gap"] >= 5].copy()
    return picks[avail].sort_values(["sportmonks_fixture_id", "value_gap"], ascending=[True, False])


def replay_by_confidence_tier(df: pd.DataFrame) -> dict[str, Any]:
    """Top-3 hit rate segmented by confidence tier (anytime, composite score)."""
    if "confidence_tier" not in df.columns:
        return {}
    out: dict[str, Any] = {}
    for tier, grp in df.groupby("confidence_tier"):
        # evaluate fixtures where at least one A-tier player exists in top composite
        hits = fixture_ranking_hits(grp, score_col="composite_scorer_score", target_col="target_anytime")
        out[str(tier)] = hits.to_dict()
    return out
