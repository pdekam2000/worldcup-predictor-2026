"""Train goalscorer ML shadow models."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from worldcup_predictor.egie.goalscorer_ml_shadow.models import ML_FEATURE_COLUMNS, TARGETS

try:
    import lightgbm as lgb
except ImportError:
    lgb = None

try:
    from catboost import CatBoostClassifier
except ImportError:
    CatBoostClassifier = None


def _xy(df: pd.DataFrame, target_col: str) -> tuple[np.ndarray, np.ndarray]:
    X = df[list(ML_FEATURE_COLUMNS)].fillna(0.0).values
    y = df[target_col].astype(int).values
    return X, y


def train_logistic(train: pd.DataFrame, target_col: str) -> tuple[Any, StandardScaler]:
    scaler = StandardScaler()
    X, y = _xy(train, target_col)
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    model.fit(Xs, y)
    return model, scaler


def predict_logistic(model: Any, scaler: StandardScaler, df: pd.DataFrame) -> np.ndarray:
    X = scaler.transform(df[list(ML_FEATURE_COLUMNS)].fillna(0.0).values)
    return model.predict_proba(X)[:, 1]


def train_lightgbm(train: pd.DataFrame, target_col: str) -> Any:
    X, y = _xy(train, target_col)
    if lgb is None:
        from sklearn.ensemble import GradientBoostingClassifier

        model = GradientBoostingClassifier(random_state=42, max_depth=4, n_estimators=150)
        model.fit(X, y)
        return model
    model = lgb.LGBMClassifier(
        objective="binary",
        verbosity=-1,
        num_leaves=31,
        learning_rate=0.05,
        n_estimators=200,
        class_weight="balanced",
        random_state=42,
    )
    model.fit(X, y)
    return model


def predict_lightgbm(model: Any, df: pd.DataFrame) -> np.ndarray:
    X = df[list(ML_FEATURE_COLUMNS)].fillna(0.0).values
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    return model.predict(X).astype(float)


def train_catboost(train: pd.DataFrame, target_col: str) -> Any | None:
    if CatBoostClassifier is None:
        return None
    X, y = _xy(train, target_col)
    model = CatBoostClassifier(
        iterations=200,
        depth=6,
        learning_rate=0.05,
        verbose=False,
        auto_class_weights="Balanced",
        random_seed=42,
    )
    model.fit(X, y)
    return model


def predict_catboost(model: Any | None, df: pd.DataFrame) -> np.ndarray | None:
    if model is None:
        return None
    X = df[list(ML_FEATURE_COLUMNS)].fillna(0.0).values
    return model.predict_proba(X)[:, 1]


def train_market_models(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
    *,
    market: str,
    target_col: str,
) -> dict[str, Any]:
    lr_model, scaler = train_logistic(train, target_col)
    lgb_model = train_lightgbm(train, target_col)
    cat_model = train_catboost(train, target_col)

    out_test = test.copy()
    out_val = val.copy()

    out_test["score_logistic_regression"] = predict_logistic(lr_model, scaler, test)
    out_val["score_logistic_regression"] = predict_logistic(lr_model, scaler, val)

    out_test["score_lightgbm"] = predict_lightgbm(lgb_model, test)
    out_val["score_lightgbm"] = predict_lightgbm(lgb_model, val)

    cat_test = predict_catboost(cat_model, test)
    cat_val = predict_catboost(cat_model, val)
    if cat_test is not None:
        out_test["score_catboost"] = cat_test
        out_val["score_catboost"] = cat_val

    parts_test = [out_test["score_logistic_regression"], out_test["score_lightgbm"]]
    parts_val = [out_val["score_logistic_regression"], out_val["score_lightgbm"]]
    if cat_test is not None:
        parts_test.append(out_test["score_catboost"])
        parts_val.append(out_val["score_catboost"])
    out_test["score_ensemble"] = np.mean(np.vstack(parts_test), axis=0)
    out_val["score_ensemble"] = np.mean(np.vstack(parts_val), axis=0)

    importance = extract_feature_importance(lr_model, scaler, lgb_model, cat_model)

    return {
        "market": market,
        "test": out_test,
        "val": out_val,
        "models": {
            "logistic_regression": lr_model,
            "lightgbm": lgb_model,
            "catboost": cat_model,
        },
        "scaler": scaler,
        "importance": importance,
        "catboost_available": cat_model is not None,
    }


def extract_feature_importance(
    lr_model: Any,
    scaler: StandardScaler,
    lgb_model: Any,
    cat_model: Any | None,
) -> dict[str, Any]:
    lr_imp = dict(zip(ML_FEATURE_COLUMNS, np.abs(lr_model.coef_[0]).tolist()))
    if lgb is not None and hasattr(lgb_model, "feature_importances_"):
        lgb_imp = dict(zip(ML_FEATURE_COLUMNS, lgb_model.feature_importances_.tolist()))
    elif hasattr(lgb_model, "feature_importances_"):
        lgb_imp = dict(zip(ML_FEATURE_COLUMNS, lgb_model.feature_importances_.tolist()))
    else:
        lgb_imp = {}
    cat_imp = {}
    if cat_model is not None and hasattr(cat_model, "feature_importances_"):
        cat_imp = dict(zip(ML_FEATURE_COLUMNS, cat_model.feature_importances_.tolist()))

    combined: dict[str, float] = {}
    for feat in ML_FEATURE_COLUMNS:
        lr_v = lr_imp.get(feat, 0.0)
        lgb_v = lgb_imp.get(feat, 0.0)
        cat_v = cat_imp.get(feat, 0.0)
        lgb_n = lgb_v / max(lgb_imp.values()) if lgb_imp and max(lgb_imp.values()) > 0 else 0.0
        vals = [v for v in (lr_v, lgb_n, cat_v) if v > 0]
        combined[feat] = round(float(np.mean(vals)), 4) if vals else 0.0

    ranked = sorted(combined.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "logistic_regression": dict(sorted(lr_imp.items(), key=lambda kv: kv[1], reverse=True)),
        "lightgbm": dict(sorted(lgb_imp.items(), key=lambda kv: kv[1], reverse=True)),
        "catboost": dict(sorted(cat_imp.items(), key=lambda kv: kv[1], reverse=True)) if cat_imp else {},
        "combined_rank": [{"feature": f, "importance": v} for f, v in ranked],
    }


def analyze_feature_groups(importance: dict[str, float]) -> dict[str, Any]:
    from worldcup_predictor.egie.goalscorer_ml_shadow.models import (
        FEATURE_GROUP_A,
        FEATURE_GROUP_B,
        FEATURE_GROUP_C,
        FEATURE_GROUP_D,
    )

    def _group_sum(names: tuple[str, ...]) -> float:
        return round(sum(importance.get(n, 0.0) for n in names), 4)

    groups = {
        "form": _group_sum(FEATURE_GROUP_A),
        "shots": _group_sum(FEATURE_GROUP_B),
        "xg": _group_sum(FEATURE_GROUP_C),
        "lineup": _group_sum(FEATURE_GROUP_D),
    }
    ranked_feats = sorted(importance.items(), key=lambda kv: kv[1], reverse=True)
    top = [f for f, v in ranked_feats[:5] if v > 0]
    bottom = [f for f, v in ranked_feats if v <= ranked_feats[-1][1] + 1e-9][:3]
    return {
        "group_importance": groups,
        "most_valuable": top,
        "least_valuable": bottom,
        "xg_helps": groups["xg"] > groups["shots"],
        "lineup_helps": groups["lineup"] > 0.05 * sum(groups.values()) if sum(groups.values()) else False,
    }
