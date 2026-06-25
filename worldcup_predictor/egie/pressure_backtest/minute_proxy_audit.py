"""Minute-proxy risk audit for in-play goal-minute pressure models."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.preprocessing import LabelEncoder

from worldcup_predictor.egie.pressure_backtest.pressure_backtest_runner import (
    MIN_TEST,
    MIN_TRAIN,
    _delta,
    _ece,
    _temporal_split,
    _train_and_eval,
)
from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import ARTIFACT_DIR_H2
from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import (
    MINUTE_ONLY_FEATURES,
    PRESSURE_FEATURE_NAMES,
    PRESSURE_WITHOUT_MINUTE_PROXY,
)
from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS

ARTIFACT_DIR = ARTIFACT_DIR_H2


def _bootstrap_accuracy_ci(y_true: np.ndarray, y_pred: np.ndarray, *, n_boot: int = 200) -> dict[str, float]:
    if len(y_true) < 2:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0}
    rng = np.random.default_rng(42)
    scores: list[float] = []
    n = len(y_true)
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        scores.append(float(accuracy_score(y_true[idx], y_pred[idx])))
    return {
        "mean": round(float(np.mean(scores)), 4),
        "ci_low": round(float(np.percentile(scores, 2.5)), 4),
        "ci_high": round(float(np.percentile(scores, 97.5)), 4),
    }


def _eval_with_bootstrap(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    *,
    multiclass: bool = True,
    require_pressure: bool = True,
) -> dict[str, Any]:
    base = _train_and_eval(
        train,
        test,
        feature_cols,
        label_col,
        multiclass=multiclass,
        require_pressure=require_pressure,
    )
    if base.get("status") != "ok":
        return base

    avail_cols = [c for c in feature_cols if c in train.columns]
    sub_train = train[train[label_col].notna()].copy()
    sub_test = test[test[label_col].notna()].copy()
    if require_pressure:
        sub_train = sub_train[sub_train["pressure_available"] == True]  # noqa: E712
        sub_test = sub_test[sub_test["pressure_available"] == True]  # noqa: E712

    X_train = sub_train[avail_cols].fillna(-1.0)
    X_test = sub_test[avail_cols].fillna(-1.0)
    model = GradientBoostingClassifier(random_state=42)
    if multiclass:
        le = LabelEncoder()
        y_train = le.fit_transform(sub_train[label_col].astype(str))
        y_test = le.transform(sub_test[label_col].astype(str))
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
    else:
        y_train = sub_train[label_col].astype(int).values
        y_test = sub_test[label_col].astype(int).values
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
    base["bootstrap_accuracy"] = _bootstrap_accuracy_ci(y_test, pred)
    return base


def run_minute_proxy_audit(
    inplay_df: pd.DataFrame | None = None,
    *,
    output_dir: Path | None = None,
    phase: str = "54H-2",
) -> dict[str, Any]:
    artifact_dir = output_dir or ARTIFACT_DIR
    if inplay_df is None:
        path = artifact_dir / "pressure_inplay_dataset.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"missing inplay dataset: {path}")
        inplay_df = pd.read_parquet(path)

    train, test = _temporal_split(inplay_df)
    ip_train = train[train["label_goal_minute_bucket"].notna()].copy()
    ip_test = test[test["label_goal_minute_bucket"].notna()].copy()

    minute_cols = [c for c in MINUTE_ONLY_FEATURES if c in ip_train.columns]
    pressure_no_minute = [c for c in PRESSURE_WITHOUT_MINUTE_PROXY if c in ip_train.columns]
    pressure_full = [c for c in PRESSURE_FEATURE_NAMES if c in ip_train.columns]
    pressure_plus_minute = minute_cols + pressure_full
    baseline_cols = [c for c in BASELINE_COLS if c in ip_train.columns]

    models = {
        "minute_only": _eval_with_bootstrap(ip_train, ip_test, minute_cols, "label_goal_minute_bucket"),
        "pressure_only_no_minute": _eval_with_bootstrap(
            ip_train, ip_test, pressure_no_minute, "label_goal_minute_bucket"
        ),
        "pressure_full": _eval_with_bootstrap(ip_train, ip_test, pressure_full, "label_goal_minute_bucket"),
        "pressure_plus_minute": _eval_with_bootstrap(
            ip_train, ip_test, pressure_plus_minute, "label_goal_minute_bucket"
        ),
        "baseline_egie": _eval_with_bootstrap(
            ip_train, ip_test, baseline_cols, "label_goal_minute_bucket", require_pressure=False
        ),
    }

    minute_acc = float((models["minute_only"] or {}).get("accuracy") or 0.0)
    pressure_full_acc = float((models["pressure_full"] or {}).get("accuracy") or 0.0)
    pressure_no_minute_acc = float((models["pressure_only_no_minute"] or {}).get("accuracy") or 0.0)
    pressure_plus_acc = float((models["pressure_plus_minute"] or {}).get("accuracy") or 0.0)

    true_lift_vs_minute = round(pressure_no_minute_acc - minute_acc, 4)
    incremental_over_minute_full = round(pressure_plus_acc - minute_acc, 4)
    minute_explains_lift = pressure_full_acc - minute_acc <= 0.03

    if models["minute_only"].get("status") == "ok" and minute_acc >= pressure_full_acc - 0.02:
        proxy_risk = "MINUTE_PROXY_RISK_HIGH"
    elif true_lift_vs_minute >= 0.03:
        proxy_risk = "MINUTE_PROXY_RISK_LOW"
    else:
        proxy_risk = "MINUTE_PROXY_RISK_MEDIUM"

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "market": "inplay_goal_minute_bucket",
        "models": models,
        "comparison": {
            "minute_only_accuracy": minute_acc,
            "pressure_only_no_minute_accuracy": pressure_no_minute_acc,
            "pressure_full_accuracy": pressure_full_acc,
            "pressure_plus_minute_accuracy": pressure_plus_acc,
            "true_pressure_lift_after_controlling_minute": true_lift_vs_minute,
            "incremental_lift_pressure_plus_over_minute_only": incremental_over_minute_full,
            "minute_explains_most_of_pressure_full_lift": minute_explains_lift,
        },
        "proxy_risk_verdict": proxy_risk,
        "leakage_note": "pressure features use minute < goal_minute only; audit validates no post-goal rows",
    }

    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "minute_proxy_audit.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    return out
