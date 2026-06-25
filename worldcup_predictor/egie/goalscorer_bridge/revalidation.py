"""Revalidation — ML vs Odds on bridged fixtures."""

from __future__ import annotations

from typing import Any

import pandas as pd

from worldcup_predictor.egie.goalscorer_ml_shadow.features import prepare_features, split_data
from worldcup_predictor.egie.goalscorer_ml_shadow.trainer import predict_logistic, train_logistic
from worldcup_predictor.egie.goalscorer_odds_mapping.calibration_study import run_calibration_study
from worldcup_predictor.egie.goalscorer_odds_mapping.comparison import build_comparison_frame, fixture_ranking_metrics, run_comparison


def _comparison_for_market(
    mapped_df: pd.DataFrame,
    outcomes_df: pd.DataFrame,
    ml_scores: pd.DataFrame,
    *,
    market_label: str,
    target_col: str,
) -> pd.DataFrame:
    odds = mapped_df.copy()
    if "label" not in odds.columns:
        odds["label"] = "Anytime"
    odds = odds[odds["label"].str.contains(market_label, case=False, na=False)]
    if odds.empty:
        return pd.DataFrame()

    comp = build_comparison_frame(odds, outcomes_df, ml_scores, market_label=market_label)
    if comp.empty:
        return comp
    if target_col != "target_anytime" and target_col in outcomes_df.columns:
        comp = comp.drop(columns=["target_anytime"], errors="ignore")
        comp = comp.merge(
            outcomes_df[["sportmonks_fixture_id", "player_id", target_col]],
            on=["sportmonks_fixture_id", "player_id"],
            how="left",
        )
    return comp


def run_revalidation(
    dataset_v2: pd.DataFrame,
    mapped_df: pd.DataFrame,
    *,
    full_dataset: pd.DataFrame,
) -> dict[str, Any]:
    if dataset_v2.empty or mapped_df.empty:
        return {"status": "insufficient_data"}

    train, val, test = split_data(full_dataset)
    train_f = prepare_features(train)
    test_ids = set(dataset_v2["sportmonks_fixture_id"].astype(int).unique())
    test_f = prepare_features(full_dataset[full_dataset["sportmonks_fixture_id"].isin(test_ids)])

    if test_f.empty:
        test_f = prepare_features(dataset_v2)

    model, scaler = train_logistic(train_f, "target_anytime")
    ml_probs = predict_logistic(model, scaler, test_f)
    ml_scores = test_f[["sportmonks_fixture_id", "player_id"]].copy()
    ml_scores["ml_probability"] = ml_probs

    outcomes = dataset_v2.drop_duplicates(["sportmonks_fixture_id", "player_id"])
    mapped = mapped_df.copy()
    if "label" not in mapped.columns:
        mapped["label"] = mapped["market"].apply(
            lambda m: "First" if "first" in str(m).lower() else ("Last" if "last" in str(m).lower() else "Anytime")
        )

    markets = {
        "anytime": ("Anytime", "target_anytime"),
        "first_goal": ("First", "target_first_goal"),
        "most_likely": ("Anytime", "target_most_likely"),
    }

    results: dict[str, Any] = {"status": "ok", "markets": {}}
    for key, (label, target) in markets.items():
        comp = _comparison_for_market(mapped, outcomes, ml_scores, market_label=label, target_col=target)
        if comp.empty:
            results["markets"][key] = {"status": "no_rows"}
            continue
        target_use = target if target in comp.columns else "target_anytime"
        if target_use not in comp.columns and "target_anytime" in outcomes.columns:
            comp = comp.merge(
                outcomes[["sportmonks_fixture_id", "player_id", "target_anytime", target]],
                on=["sportmonks_fixture_id", "player_id"],
                how="left",
            )
            target_use = target if target in comp.columns else "target_anytime"
        ranking = {
            "ml_only": fixture_ranking_metrics(comp, "ml_probability", target_col=target_use),
            "odds_only": fixture_ranking_metrics(comp, "implied_probability", target_col=target_use),
            "ml_odds_blend": fixture_ranking_metrics(comp, "ml_odds_blend", target_col=target_use),
        }
        cal_input = comp.copy()
        if target_use != "target_anytime" and target_use in cal_input.columns:
            cal_input["target_anytime"] = cal_input[target_use]
        elif "target_anytime" not in cal_input.columns and target_use in cal_input.columns:
            cal_input["target_anytime"] = cal_input[target_use]
        cal = run_calibration_study(cal_input)
        results["markets"][key] = {
            "ranking": ranking,
            "calibration": cal,
            "comparison": run_comparison(cal_input),
            "rows": len(comp),
            "fixtures": int(comp["sportmonks_fixture_id"].nunique()),
        }

    return results
