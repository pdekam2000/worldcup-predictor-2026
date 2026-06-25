"""Goalscorer ML shadow backtest orchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from worldcup_predictor.egie.goalscorer_ml_shadow.calibration import evaluate_calibration_methods
from worldcup_predictor.egie.goalscorer_ml_shadow.features import load_dataset, prepare_features, split_data
from worldcup_predictor.egie.goalscorer_ml_shadow.models import MLShadowReport, TARGETS
from worldcup_predictor.egie.goalscorer_ml_shadow.odds_overlay import run_odds_overlay
from worldcup_predictor.egie.goalscorer_ml_shadow.ranking_metrics import compute_ranking_metrics
from worldcup_predictor.egie.goalscorer_ml_shadow.trainer import analyze_feature_groups, train_market_models
from worldcup_predictor.egie.goalscorer_shadow.scoring import apply_baseline_scores

ARTIFACT_DIR = Path("artifacts/phase54l_goalscorer_ml_shadow")

ML_MODELS = ("logistic_regression", "lightgbm", "catboost", "ensemble")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _recommend(ranking: list, baseline_comparison: dict[str, float]) -> str:
    lifts = []
    for market in TARGETS:
        b = baseline_comparison.get(f"{market}_top3", 0.0)
        ml_scores = [
            r.top3_hit or 0.0
            for r in ranking
            if r.market == market and r.model not in ("combined_baseline",)
        ]
        best = max(ml_scores) if ml_scores else 0.0
        lifts.append(best - b)
    avg_lift = sum(lifts) / len(lifts) if lifts else 0.0
    if avg_lift >= 0.05:
        return "GOALSCORER_HIGH_VALUE"
    if avg_lift >= 0.02:
        return "GOALSCORER_MEDIUM_VALUE"
    if avg_lift >= -0.02:
        return "GOALSCORER_LOW_VALUE"
    return "GOALSCORER_NO_VALUE"


def run_ml_shadow(
    dataset_path: Path | str | None = None,
    artifact_dir: Path | str | None = None,
) -> MLShadowReport:
    out_dir = Path(artifact_dir or ARTIFACT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = prepare_features(load_dataset(dataset_path))
    train, val, test = split_data(df)

    limitations: list[str] = []
    n_test_fixtures = int(test["sportmonks_fixture_id"].nunique())
    if n_test_fixtures < 100:
        limitations.append(f"test split has {n_test_fixtures} fixtures (<100 preferred)")

    test_base = apply_baseline_scores(test)
    test_base["score_combined_baseline"] = test_base["combined_score"]

    market_test: dict[str, pd.DataFrame] = {}
    all_importance: dict = {}
    all_calibration = []
    calibration_curves: dict = {}
    catboost_ok = False

    for market, target_col in TARGETS.items():
        bundle = train_market_models(train, val, test, market=market, target_col=target_col)
        catboost_ok = catboost_ok or bool(bundle.get("catboost_available"))
        part = bundle["test"].copy()
        rename = {f"score_{m}": f"score_{m}" for m in ML_MODELS if f"score_{m}" in part.columns}
        market_test[market] = part
        all_importance[market] = bundle["importance"]

        val_b, test_b = bundle["val"], bundle["test"]
        if "score_ensemble" in val_b.columns:
            cal_metrics, curves = evaluate_calibration_methods(
                val_b[target_col].astype(int).values,
                val_b["score_ensemble"].values,
                test_b[target_col].astype(int).values,
                test_b["score_ensemble"].values,
                market=market,
                model="ensemble",
            )
            all_calibration.extend(cal_metrics)
            calibration_curves[market] = curves

    ranking = []
    baseline_comparison: dict[str, float] = {}
    ml_best: dict[str, float] = {}

    for market, target_col in TARGETS.items():
        multi = market == "anytime"
        eval_df = market_test[market].merge(
            test_base[["sportmonks_fixture_id", "player_id", "score_combined_baseline"]],
            on=["sportmonks_fixture_id", "player_id"],
            how="left",
        )
        models_to_run = list(ML_MODELS) + ["combined_baseline"]
        for model in models_to_run:
            col = "score_combined_baseline" if model == "combined_baseline" else f"score_{model}"
            if col not in eval_df.columns:
                continue
            m = compute_ranking_metrics(
                eval_df,
                score_col=col,
                target_col=target_col,
                market=market,
                model=model,
                multi_positive=multi,
            )
            ranking.append(m)
            if model == "combined_baseline":
                baseline_comparison[f"{market}_top3"] = m.top3_hit or 0.0
            if model == "ensemble":
                ml_best[f"{market}_top3"] = m.top3_hit or 0.0

    imp_rows = all_importance.get("anytime", {}).get("combined_rank", [])
    imp_dict = {row["feature"]: row["importance"] for row in imp_rows}
    group_analysis = analyze_feature_groups(imp_dict)
    max_imp = max(imp_dict.values()) if imp_dict else 1.0
    redundant = [f for f, v in imp_dict.items() if v < 0.01 * max_imp]

    odds = {}
    anytime_test = market_test.get("anytime")
    if anytime_test is not None and "score_ensemble" in anytime_test.columns:
        odds = run_odds_overlay(anytime_test, score_col="score_ensemble")

    recommendation = _recommend(ranking, baseline_comparison)

    report = MLShadowReport(
        generated_at=_utc_now(),
        dataset={
            "total_rows": len(df),
            "train_rows": len(train),
            "val_rows": len(val),
            "test_rows": len(test),
            "fixtures_test": n_test_fixtures,
            "catboost_available": catboost_ok,
        },
        ranking=ranking,
        calibration=all_calibration,
        feature_importance={
            "by_market": all_importance,
            "aggregate_anytime": imp_dict,
            "group_analysis": group_analysis,
            "redundant_features": redundant,
        },
        odds_overlay=odds,
        baseline_comparison={
            **baseline_comparison,
            "ml_ensemble": ml_best,
            "lifts_top3": {
                m: round(ml_best.get(f"{m}_top3", 0) - baseline_comparison.get(f"{m}_top3", 0), 4)
                for m in TARGETS
            },
        },
        recommendation=recommendation,
        limitations=limitations,
    )

    (out_dir / "ml_shadow_report.json").write_text(
        json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    (out_dir / "calibration_curves.json").write_text(
        json.dumps(calibration_curves, indent=2, default=str), encoding="utf-8"
    )
    if anytime_test is not None:
        anytime_test.to_parquet(out_dir / "test_predictions_anytime.parquet", index=False)

    return report
