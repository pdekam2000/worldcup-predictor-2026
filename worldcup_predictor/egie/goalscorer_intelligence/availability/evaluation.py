"""Feature group evaluation and UEFA analysis for Phase 54S."""

from __future__ import annotations

from typing import Any

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from worldcup_predictor.egie.goalscorer_intelligence.availability.models import (
    AVAILABILITY_COLUMNS,
    BASELINE_54Q_UEFA_TOP3,
    BASELINE_54R_UEFA_TOP3,
    ELITE_PATH_THRESHOLD,
    FEATURE_GROUPS,
    UEFA_LEAGUE_IDS,
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


def _metrics_block(scored: pd.DataFrame) -> dict[str, Any]:
    hits = fixture_ranking_hits(scored, score_col="group_score", target_col="target_anytime")
    rank_m = compute_ranking_metrics(
        scored,
        score_col="group_score",
        target_col="target_anytime",
        market="anytime",
        model="group",
    )
    return {
        "fixtures_evaluated": hits.fixtures_evaluated,
        "top1_hit": hits.top1_hit,
        "top3_hit": hits.top3_hit,
        "top5_hit": hits.top5_hit,
        "mrr": hits.mrr,
        "ranking_metrics": rank_m.to_dict(),
    }


def evaluate_feature_groups(df: pd.DataFrame) -> dict[str, Any]:
    train, _, test = split_data(df)
    results: dict[str, Any] = {}
    for group in FEATURE_GROUPS:
        tr = _prepare_group_frame(train, group)
        te = _prepare_group_frame(test, group)
        scored = _train_score_group(tr, te, group)
        results[group] = _metrics_block(scored)
    return results


def availability_feature_importance(df: pd.DataFrame) -> dict[str, Any]:
    """Ablation on player_lineup_availability model."""
    train, _, test = split_data(df)
    tr = _prepare_group_frame(train, "player_lineup_availability")
    te = _prepare_group_frame(test, "player_lineup_availability")
    baseline_scored = _train_score_group(tr, te, "player_lineup_availability")
    baseline = fixture_ranking_hits(baseline_scored, score_col="group_score").top3_hit

    impacts: dict[str, float] = {}
    for feat in AVAILABILITY_COLUMNS:
        tr_ab = tr.copy()
        te_ab = te.copy()
        tr_ab[feat] = 0.0
        te_ab[feat] = 0.0
        ablated = _train_score_group(tr_ab, te_ab, "player_lineup_availability")
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


def uefa_league_analysis(df: pd.DataFrame) -> dict[str, Any]:
    """UEFA test-split metrics for lineup vs lineup+availability."""
    train, _, test = split_data(df)
    uefa_ids = set(UEFA_LEAGUE_IDS.keys())
    uefa_test = test[test["league_id"].isin(uefa_ids)].copy()

    tr_lineup = _prepare_group_frame(train, "player_lineup")
    te_lineup = _prepare_group_frame(uefa_test, "player_lineup")
    tr_full = _prepare_group_frame(train, "player_lineup_availability")
    te_full = _prepare_group_frame(uefa_test, "player_lineup_availability")

    lineup_scored = _train_score_group(tr_lineup, te_lineup, "player_lineup")
    full_scored = _train_score_group(tr_full, te_full, "player_lineup_availability")

    out: dict[str, Any] = {
        "overall": {},
        "by_league": {},
        "baselines": {
            "54q_uefa_composite": BASELINE_54Q_UEFA_TOP3,
            "54r_uefa_test": BASELINE_54R_UEFA_TOP3,
        },
    }

    b = _metrics_block(lineup_scored)
    t = _metrics_block(full_scored)
    out["overall"] = {
        **t,
        "player_lineup_top3": b["top3_hit"],
        "player_lineup_availability_top3": t["top3_hit"],
        "improvement_pp": round(float(t["top3_hit"] or 0) - float(b["top3_hit"] or 0), 4),
    }

    for lid, league in UEFA_LEAGUE_IDS.items():
        sub_b = lineup_scored[lineup_scored["league_id"] == lid]
        sub_t = full_scored[full_scored["league_id"] == lid]
        if sub_b.empty:
            continue
        lb = _metrics_block(sub_b)
        lt = _metrics_block(sub_t)
        out["by_league"][league] = {
            "league_id": lid,
            "fixtures_evaluated": lt["fixtures_evaluated"],
            "player_lineup_top3": lb["top3_hit"],
            "player_lineup_availability_top3": lt["top3_hit"],
            "improvement_pp": round(float(lt["top3_hit"] or 0) - float(lb["top3_hit"] or 0), 4),
            "top1_hit": lt["top1_hit"],
            "top5_hit": lt["top5_hit"],
            "mrr": lt["mrr"],
        }
    return out


def elite_path_test(uefa: dict[str, Any], group_results: dict[str, Any]) -> dict[str, Any]:
    uefa_top3 = float((uefa.get("overall") or {}).get("player_lineup_availability_top3") or 0)
    best_group = max(group_results.items(), key=lambda x: float(x[1].get("top3_hit") or 0))
    best_top3 = float(best_group[1].get("top3_hit") or 0)
    closes_gap = uefa_top3 > ELITE_PATH_THRESHOLD

    if closes_gap:
        recommendation = "GOALSCORER_ELITE_PATH"
    elif uefa_top3 <= BASELINE_54R_UEFA_TOP3 + 0.005:
        recommendation = "GOALSCORER_MAXED_OUT"
    else:
        recommendation = "GOALSCORER_HIGH_VALUE"

    return {
        "uefa_lineup_availability_top3": uefa_top3,
        "elite_path_threshold": ELITE_PATH_THRESHOLD,
        "closes_uefa_gap": closes_gap,
        "architecture_near_ceiling": not closes_gap,
        "best_test_group": best_group[0],
        "best_test_top3": best_top3,
        "recommendation": recommendation,
    }


def decide_recommendation(
    group_results: dict[str, Any],
    feat_imp: dict[str, Any],
    uefa: dict[str, Any],
    elite: dict[str, Any],
) -> dict[str, Any]:
    lineup = float((group_results.get("player_lineup") or {}).get("top3_hit") or 0)
    full = float((group_results.get("player_lineup_availability") or {}).get("top3_hit") or 0)
    avail_only = float((group_results.get("player_availability") or {}).get("top3_hit") or 0)
    uefa_lift = float((uefa.get("overall") or {}).get("improvement_pp") or 0)

    availability_helps = (full - lineup) >= 0.005 or uefa_lift >= 0.005 or len(feat_imp.get("positive") or []) >= 2
    return {
        "availability_helps": availability_helps,
        "test_lift_lineup_to_full_pp": round(full - lineup, 4),
        "uefa_improvement_pp": uefa_lift,
        "positive_availability_features": len(feat_imp.get("positive") or []),
        "recommendation": elite.get("recommendation", "GOALSCORER_HIGH_VALUE"),
    }
