"""Shadow-only fusion experiment runner — no production changes."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from worldcup_predictor.research.provider_feature_fusion.constants import (
    EXPERIMENT_VARIANTS,
    EXPERIMENTS_PATH,
    FEATURE_VERSION,
    MODEL_VERSION,
    PHASE,
)
from worldcup_predictor.research.provider_feature_fusion.metrics import (
    evaluate_binary,
    evaluate_classification,
    poisson_score_topk,
)
from worldcup_predictor.research.wde_shadow_historical.constants import (
    TEST_PARQUET,
    TRAIN_PARQUET,
    VAL_PARQUET,
)

FEATURE_SETS: dict[str, list[str]] = {
    "A_baseline_production_odds": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
    ],
    "B_baseline_plus_odds_features": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
        "market_entropy",
        "odds_favorite_strength",
        "implied_prob_over_2_5",
        "implied_prob_btts_yes",
    ],
    "C_baseline_plus_xg_diagnostic": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
        "home_xg_diagnostic",
        "away_xg_diagnostic",
    ],
    "D_baseline_plus_form_proxy": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
        "form_proxy_home",
        "form_proxy_away",
    ],
    "E_baseline_plus_lineup_injury_proxy": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
    ],
    "F_baseline_plus_pressure_proxy": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
    ],
    "G_baseline_plus_odds_and_xg_diagnostic": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
        "market_entropy",
        "home_xg_diagnostic",
        "away_xg_diagnostic",
    ],
    "H_full_safe_fusion": [
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
        "market_entropy",
        "odds_favorite_strength",
        "implied_prob_over_2_5",
        "implied_prob_under_2_5",
        "implied_prob_btts_yes",
        "implied_prob_btts_no",
        "form_proxy_home",
        "form_proxy_away",
    ],
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _prep_xy(df: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, pd.DataFrame]:
    sub = df[features].copy()
    for col in features:
        if sub[col].notna().sum() == 0:
            sub[col] = 0.0
    medians = sub.median(numeric_only=True)
    sub = sub.fillna(medians).fillna(0.0)
    return sub.to_numpy(dtype=float), sub


def _fit_multiclass(train_df: pd.DataFrame, features: list[str], label_col: str) -> Pipeline | None:
    work = train_df[train_df[label_col].notna()].copy()
    if len(work) < 200:
        return None
    x, _ = _prep_xy(work, features)
    y = work[label_col].astype(str).tolist()
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, C=1.0, solver="lbfgs")),
        ]
    )
    pipe.fit(x, y)
    return pipe


def _fit_binary(train_df: pd.DataFrame, features: list[str], label_col: str, *, positive: str) -> Pipeline | None:
    work = train_df[train_df[label_col].notna()].copy()
    if len(work) < 200:
        return None
    x, _ = _prep_xy(work, features)
    y = (work[label_col].astype(str) == positive).astype(int).to_numpy()
    if len(np.unique(y)) < 2:
        return None
    pipe = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=500, C=1.0)),
        ]
    )
    pipe.fit(x, y)
    return pipe


def _predict_multiclass(model: Pipeline, df: pd.DataFrame, features: list[str], label_col: str) -> dict[str, Any]:
    work = df[df[label_col].notna()].copy()
    if work.empty:
        return {"n": 0}
    x, _ = _prep_xy(work, features)
    clf = model.named_steps["clf"]
    classes = list(clf.classes_)
    proba = model.predict_proba(x)
    preds = model.predict(x).tolist()
    y_true = work[label_col].astype(str).tolist()
    return evaluate_classification(y_true, preds, proba, classes)


def _predict_binary(
    model: Pipeline, df: pd.DataFrame, features: list[str], label_col: str, *, positive: str
) -> dict[str, Any]:
    work = df[df[label_col].notna()].copy()
    if work.empty:
        return {"n": 0}
    x, _ = _prep_xy(work, features)
    proba = model.predict_proba(x)[:, 1]
    preds = (proba >= 0.5).astype(int).tolist()
    y_true = (work[label_col].astype(str) == positive).astype(int).tolist()
    return evaluate_binary(y_true, preds, proba)


def _ecse_eval(df: pd.DataFrame, *, use_xg: bool) -> dict[str, Any]:
    hits = {1: 0, 3: 0, 5: 0}
    ranks: list[int] = []
    n = 0
    for _, row in df.iterrows():
        h = int(row["final_home_goals"])
        a = int(row["final_away_goals"])
        if use_xg and pd.notna(row.get("home_xg_diagnostic")):
            hxg = float(row["home_xg_diagnostic"])
            axg = float(row["away_xg_diagnostic"])
        else:
            # odds-implied goal rates proxy (safe)
            hxg = float(row.get("implied_prob_home") or 0.33) * 2.5
            axg = float(row.get("implied_prob_away") or 0.33) * 2.5
        ev = poisson_score_topk(hxg, axg, h, a, k=5)
        n += 1
        for k in (1, 3, 5):
            if ev.get(f"top{k}_hit"):
                hits[k] += 1
        if ev.get("actual_rank"):
            ranks.append(int(ev["actual_rank"]))
    return {
        "n": n,
        "top1_hit_rate": round(hits[1] / n, 4) if n else None,
        "top3_hit_rate": round(hits[3] / n, 4) if n else None,
        "top5_hit_rate": round(hits[5] / n, 4) if n else None,
        "median_actual_rank": round(float(np.median(ranks)), 2) if ranks else None,
        "use_xg": use_xg,
    }


def _breakdown(df: pd.DataFrame, metric_fn, *, col: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, sub in df.groupby(col):
        if len(sub) < 50:
            continue
        out[str(key)] = metric_fn(sub)
    return out


def run_fusion_experiments() -> dict[str, Any]:
    if not TRAIN_PARQUET.exists() or not TEST_PARQUET.exists():
        return {"phase": PHASE, "skipped_reason": "split_parquets_missing"}

    train_df = pd.read_parquet(TRAIN_PARQUET)
    val_df = pd.read_parquet(VAL_PARQUET)
    holdout_df = pd.read_parquet(TEST_PARQUET)

    results: dict[str, Any] = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "feature_version": FEATURE_VERSION,
        "model_version": MODEL_VERSION,
        "provider_calls_made": 0,
        "splits": {
            "train": len(train_df),
            "validation": len(val_df),
            "holdout": len(holdout_df),
        },
        "variants": {},
    }

    baseline_metrics: dict[str, Any] | None = None

    for variant in EXPERIMENT_VARIANTS:
        features = FEATURE_SETS[variant]
        coverage = float(train_df[features].notna().all(axis=1).mean())
        vrec: dict[str, Any] = {
            "features": features,
            "feature_coverage_train": round(coverage, 4),
            "leakage_flags": [],
        }
        if "xg_diagnostic" in variant:
            vrec["leakage_flags"].append("POST_MATCH_xG_diagnostic_non_promotable")
        if variant in {"E_baseline_plus_lineup_injury_proxy", "F_baseline_plus_pressure_proxy"}:
            vrec["leakage_flags"].append("insufficient_stored_coverage_proxy_only")

        m1x2 = _fit_multiclass(train_df, features, "label_1x2")
        mou = _fit_binary(train_df, features, "label_over_2_5", positive="over_2_5")
        mbtts = _fit_binary(train_df, features, "label_btts", positive="yes")

        holdout_eval: dict[str, Any] = {}
        if m1x2:
            holdout_eval["wde_1x2"] = _predict_multiclass(m1x2, holdout_df, features, "label_1x2")
        if mou:
            holdout_eval["ou25"] = _predict_binary(mou, holdout_df, features, "label_over_2_5", positive="over_2_5")
        if mbtts:
            holdout_eval["btts"] = _predict_binary(mbtts, holdout_df, features, "label_btts", positive="yes")

        holdout_eval["ecse_odds_proxy"] = _ecse_eval(holdout_df, use_xg=False)
        if "xg" in variant:
            holdout_eval["ecse_xg_diagnostic"] = _ecse_eval(holdout_df, use_xg=True)

        vrec["holdout"] = holdout_eval
        if m1x2 and "wde_1x2" in holdout_eval:
            vrec["by_league"] = _breakdown(
                holdout_df,
                lambda sub: _predict_multiclass(m1x2, sub, features, "label_1x2"),
                col="league",
            )
            vrec["by_season"] = _breakdown(
                holdout_df,
                lambda sub: _predict_multiclass(m1x2, sub, features, "label_1x2"),
                col="season_year",
            )

        if variant == "A_baseline_production_odds" and "wde_1x2" in holdout_eval:
            baseline_metrics = holdout_eval["wde_1x2"]
        if baseline_metrics and "wde_1x2" in holdout_eval:
            b = baseline_metrics.get("accuracy") or 0
            h = holdout_eval["wde_1x2"].get("accuracy") or 0
            vrec["delta_vs_baseline_1x2_accuracy"] = round(h - b, 4)

        results["variants"][variant] = vrec

    EXPERIMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXPERIMENTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results
