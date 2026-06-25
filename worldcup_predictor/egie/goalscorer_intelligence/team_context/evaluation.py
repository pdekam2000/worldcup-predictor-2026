"""Feature group evaluation and importance for Phase 54R."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from worldcup_predictor.egie.goalscorer_intelligence.team_context.models import (
    BASELINE_54Q_UEFA_TOP3,
    ELITE_THRESHOLD,
    FEATURE_GROUPS,
    TEAM_CONTEXT_COLUMNS,
    UEFA_LEAGUE_IDS,
    WC_LEAGUE_ID,
    FeatureVerdict,
)
from worldcup_predictor.egie.goalscorer_intelligence.validation import fixture_ranking_hits
from worldcup_predictor.egie.goalscorer_ml_shadow.features import prepare_features, split_data
from worldcup_predictor.egie.goalscorer_ml_shadow.ranking_metrics import compute_ranking_metrics


def _prepare_group_frame(df: pd.DataFrame, group_name: str) -> pd.DataFrame:
    out = prepare_features(df)
    out["odds_implied_feature"] = pd.to_numeric(
        out.get("implied_probability_anytime"), errors="coerce"
    ).fillna(0.0)
    cols = FEATURE_GROUPS[group_name]
    for col in cols:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def _train_score_group(train: pd.DataFrame, test: pd.DataFrame, group_name: str) -> pd.DataFrame:
    cols = list(FEATURE_GROUPS[group_name])
    scaler = StandardScaler()
    X_train = scaler.fit_transform(train[cols].values)
    y_train = train["target_anytime"].astype(int).values
    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    model.fit(X_train, y_train)
    scored = test.copy()
    scored["group_score"] = model.predict_proba(scaler.transform(scored[cols].values))[:, 1]
    return scored


def evaluate_feature_groups(df: pd.DataFrame) -> dict[str, Any]:
    """Train/eval each feature group on temporal test split."""
    train, _, test = split_data(df)
    train_p = _prepare_group_frame(train, "player_only")
    test_p = _prepare_group_frame(test, "player_only")

    results: dict[str, Any] = {}
    for group in FEATURE_GROUPS:
        tr = _prepare_group_frame(train, group)
        te = _prepare_group_frame(test, group)
        scored = _train_score_group(tr, te, group)
        hits = fixture_ranking_hits(scored, score_col="group_score", target_col="target_anytime")
        rank_m = compute_ranking_metrics(
            scored,
            score_col="group_score",
            target_col="target_anytime",
            market="anytime",
            model=group,
        )
        results[group] = {
            "fixtures_evaluated": hits.fixtures_evaluated,
            "top1_hit": hits.top1_hit,
            "top3_hit": hits.top3_hit,
            "top5_hit": hits.top5_hit,
            "mrr": hits.mrr,
            "ranking_metrics": rank_m.to_dict(),
        }
    return results


def team_feature_importance(df: pd.DataFrame) -> dict[str, Any]:
    """Ablation study on team features using player_team model."""
    train, _, test = split_data(df)
    tr = _prepare_group_frame(train, "player_team")
    te = _prepare_group_frame(test, "player_team")
    baseline_scored = _train_score_group(tr, te, "player_team")
    baseline = fixture_ranking_hits(baseline_scored, score_col="group_score").top3_hit

    impacts: dict[str, float] = {}
    for feat in TEAM_CONTEXT_COLUMNS:
        tr_ab = tr.copy()
        te_ab = te.copy()
        tr_ab[feat] = 0.0
        te_ab[feat] = 0.0
        ablated = _train_score_group(tr_ab, te_ab, "player_team")
        hits = fixture_ranking_hits(ablated, score_col="group_score")
        impacts[feat] = round(baseline - hits.top3_hit, 4)

    verdicts: dict[str, FeatureVerdict] = {}
    for feat, drop in impacts.items():
        if drop >= 0.005:
            verdicts[feat] = "positive"
        elif drop <= -0.005:
            verdicts[feat] = "harmful"
        else:
            verdicts[feat] = "neutral"

    ranked = sorted(impacts.items(), key=lambda x: x[1], reverse=True)
    return {
        "baseline_top3": baseline,
        "feature_impacts": impacts,
        "verdicts": verdicts,
        "positive": [f for f, v in verdicts.items() if v == "positive"],
        "neutral": [f for f, v in verdicts.items() if v == "neutral"],
        "harmful": [f for f, v in verdicts.items() if v == "harmful"],
        "ranked": ranked,
    }


def uefa_league_impact(df: pd.DataFrame, group_results: dict[str, Any]) -> dict[str, Any]:
    """Per-league UEFA improvement vs 54Q baseline on test split."""
    _, _, test = split_data(df)
    uefa_ids = set(UEFA_LEAGUE_IDS.keys())
    uefa_test = test[test["league_id"].isin(uefa_ids)].copy()

    train, _, _ = split_data(df)
    tr_lineup = _prepare_group_frame(train, "player_lineup")
    te_lineup = _prepare_group_frame(uefa_test, "player_lineup")
    tr_team = _prepare_group_frame(train, "player_team")
    te_team = _prepare_group_frame(uefa_test, "player_team")

    baseline_scored = _train_score_group(tr_lineup, te_lineup, "player_lineup")
    team_scored = _train_score_group(tr_team, te_team, "player_team")

    out: dict[str, Any] = {"overall": {}, "by_league": {}}
    for label, seg_base, seg_team in [
        ("overall", baseline_scored, team_scored),
    ]:
        b = fixture_ranking_hits(seg_base, score_col="group_score")
        t = fixture_ranking_hits(seg_team, score_col="group_score")
        out["overall"] = {
            "baseline_54q_proxy_top3": BASELINE_54Q_UEFA_TOP3,
            "player_lineup_top3": b.top3_hit,
            "player_team_top3": t.top3_hit,
            "improvement_pp": round(t.top3_hit - b.top3_hit, 4),
            "fixtures_evaluated": t.fixtures_evaluated,
        }

    for lid, league in UEFA_LEAGUE_IDS.items():
        sub_b = baseline_scored[baseline_scored["league_id"] == lid]
        sub_t = team_scored[team_scored["league_id"] == lid]
        if sub_b.empty:
            continue
        b = fixture_ranking_hits(sub_b, score_col="group_score")
        t = fixture_ranking_hits(sub_t, score_col="group_score")
        out["by_league"][league] = {
            "league_id": lid,
            "fixtures_evaluated": t.fixtures_evaluated,
            "player_lineup_top3": b.top3_hit,
            "player_team_top3": t.top3_hit,
            "improvement_pp": round(t.top3_hit - b.top3_hit, 4),
        }
    return out


def elite_recheck(uefa_impact: dict[str, Any], group_results: dict[str, Any]) -> dict[str, Any]:
    """Check if UEFA reaches elite threshold with team context."""
    uefa_top3 = float((uefa_impact.get("overall") or {}).get("player_team_top3") or 0)
    best_group = max(group_results.items(), key=lambda x: x[1].get("top3_hit", 0))
    best_top3 = float(best_group[1].get("top3_hit", 0))

    reaches_elite = uefa_top3 >= ELITE_THRESHOLD
    if reaches_elite:
        recommendation = "GOALSCORER_ELITE_PATH"
    elif uefa_top3 <= BASELINE_54Q_UEFA_TOP3 + 0.01:
        recommendation = "GOALSCORER_MAXED_OUT"
    else:
        recommendation = "GOALSCORER_HIGH_VALUE"

    return {
        "uefa_player_team_top3": uefa_top3,
        "elite_threshold": ELITE_THRESHOLD,
        "reaches_elite": reaches_elite,
        "best_test_group": best_group[0],
        "best_test_top3": best_top3,
        "recommendation": recommendation,
    }


def decide_recommendation(
    group_results: dict[str, Any],
    feature_importance: dict[str, Any],
    uefa_impact: dict[str, Any],
    elite: dict[str, Any],
) -> dict[str, Any]:
    player_only = float((group_results.get("player_only") or {}).get("top3_hit") or 0)
    player_team = float((group_results.get("player_team") or {}).get("top3_hit") or 0)
    team_lift = round(player_team - player_only, 4)
    uefa_lift = float((uefa_impact.get("overall") or {}).get("improvement_pp") or 0)
    positive_feats = len(feature_importance.get("positive") or [])

    team_helps = team_lift >= 0.01 or uefa_lift >= 0.01 or positive_feats >= 3
    return {
        "team_context_helps": team_helps,
        "team_lift_test_top3_pp": team_lift,
        "uefa_improvement_pp": uefa_lift,
        "positive_team_features": positive_feats,
        "recommendation": elite.get("recommendation", "GOALSCORER_HIGH_VALUE"),
    }
