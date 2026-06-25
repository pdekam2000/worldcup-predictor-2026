"""A/B backtest: EGIE baseline features vs baseline + Sportmonks xG features."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import LabelEncoder

from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS, EgieXgDatasetBuilder
from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XG_FEATURE_NAMES
from worldcup_predictor.goal_timing.backtest.aggregator import aggregate_backtest_results, build_calibration_stats

ARTIFACT_DIR = Path("artifacts/phase54f_egie_xg_backtest")


def _temporal_split(df: pd.DataFrame, train_frac: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values("kickoff_utc").reset_index(drop=True)
    xg_rows = ordered[ordered["xg_available"] == True]  # noqa: E712
    if len(xg_rows) >= 4:
        split_at = max(1, len(xg_rows) - max(2, len(xg_rows) // 3))
        xg_train = xg_rows.iloc[:split_at]
        xg_test = xg_rows.iloc[split_at:]
        non_xg = ordered[ordered["xg_available"] == False]  # noqa: E712
        cut = max(1, int(len(non_xg) * train_frac)) if len(non_xg) else 0
        train = pd.concat([non_xg.iloc[:cut], xg_train]).drop_duplicates("sportmonks_fixture_id")
        test = pd.concat([non_xg.iloc[cut:], xg_test]).drop_duplicates("sportmonks_fixture_id")
        test = test[~test["sportmonks_fixture_id"].isin(train["sportmonks_fixture_id"])]
        return train, test
    cut = max(1, int(len(ordered) * train_frac))
    if cut >= len(ordered):
        cut = max(1, len(ordered) - 1)
    return ordered.iloc[:cut], ordered.iloc[cut:]


def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 5) -> float | None:
    if len(y_true) == 0:
        return None
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
        if not mask.any():
            continue
        ece += mask.mean() * abs(float(y_true[mask].mean()) - float(y_prob[mask].mean()))
    return round(float(ece), 4)


def _roi_proxy(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    if len(y_true) == 0:
        return None
    wins = int((y_pred == y_true).sum())
    return round((wins - len(y_true)) / len(y_true), 4)


def _train_and_eval(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    *,
    multiclass: bool = False,
) -> dict[str, Any]:
    avail_cols = [c for c in feature_cols if c in train.columns]
    sub_train = train[train[label_col].notna() & train["xg_available"]].copy()
    sub_test = test[test[label_col].notna() & test["xg_available"]].copy()
    if len(sub_train) < 3 or len(sub_test) < 2:
        return {"status": "insufficient_data", "train_n": len(sub_train), "test_n": len(sub_test)}

    X_train = sub_train[avail_cols].fillna(-1.0)
    X_test = sub_test[avail_cols].fillna(-1.0)

    if multiclass:
        le = LabelEncoder()
        y_train = le.fit_transform(sub_train[label_col].astype(str))
        y_test = le.transform(sub_test[label_col].astype(str))
        model = GradientBoostingClassifier(random_state=42)
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        proba = model.predict_proba(X_test)
        acc = accuracy_score(y_test, pred)
        ll = log_loss(y_test, proba, labels=list(range(len(le.classes_))))
        brier = None
        prec = precision_score(y_test, pred, average="weighted", zero_division=0)
        rec = recall_score(y_test, pred, average="weighted", zero_division=0)
        cal = None
        importance = dict(zip(avail_cols, model.feature_importances_.tolist()))
        classes = le.classes_.tolist()
    else:
        y_train = sub_train[label_col].astype(int).values
        y_test = sub_test[label_col].astype(int).values
        model = GradientBoostingClassifier(random_state=42)
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        acc = accuracy_score(y_test, pred)
        try:
            ll = log_loss(y_test, np.clip(proba, 1e-6, 1 - 1e-6), labels=[0, 1])
        except ValueError:
            ll = None
        brier = round(float(brier_score_loss(y_test, proba)), 4)
        prec = precision_score(y_test, pred, zero_division=0)
        rec = recall_score(y_test, pred, zero_division=0)
        cal = _ece(y_test, proba)
        importance = dict(zip(avail_cols, model.feature_importances_.tolist()))
        classes = [0, 1]

    return {
        "status": "ok",
        "train_n": len(sub_train),
        "test_n": len(sub_test),
        "accuracy": round(float(acc), 4),
        "log_loss": round(float(ll), 4),
        "brier_score": brier,
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
        "calibration_ece": cal,
        "roi_proxy": _roi_proxy(y_test, pred),
        "feature_importance": importance,
        "classes": classes,
    }


def _baseline_engine_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Evaluate current EGIE baseline predictions (rule-based, not ML)."""
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        if not r.get("xg_available"):
            continue
        actual_fg = r.get("label_first_goal_team")
        pred_fg = r.get("baseline_first_goal_team")
        fg_status = "pending"
        if actual_fg and pred_fg:
            fg_status = "correct" if pred_fg == actual_fg else "wrong"
        actual_range = r.get("label_goal_range")
        pred_range = r.get("baseline_goal_range")
        range_status = "pending"
        if actual_range and pred_range:
            range_status = "correct" if pred_range == actual_range else "wrong"
        rows.append(
            {
                "fixture_id": r.get("sportmonks_fixture_id"),
                "evaluable": actual_fg is not None,
                "no_prediction_flag": pred_fg is None,
                "first_goal_team_status": fg_status,
                "time_range_status": range_status,
                "confidence_score": 0.5,
                "data_quality_score": r.get("data_quality_score"),
            }
        )
    return rows


def _feature_importance_ranked(results: dict[str, Any]) -> list[dict[str, Any]]:
    pooled: dict[str, float] = {}
    for market in ("first_goal_team", "goal_range", "team_goals"):
        arm_b = (results.get("markets") or {}).get(market, {}).get("arm_b_xg", {})
        for feat, imp in (arm_b.get("feature_importance") or {}).items():
            pooled[feat] = pooled.get(feat, 0.0) + float(imp)
    ranked = sorted(pooled.items(), key=lambda x: x[1], reverse=True)
    return [{"feature": k, "importance_sum": round(v, 6)} for k, v in ranked[:20]]


class XgBacktestRunner:
    """Run A/B comparison on xG-available fixtures only."""

    def __init__(self) -> None:
        self.dataset_builder = EgieXgDatasetBuilder()

    def run(self, df: pd.DataFrame | None = None) -> dict[str, Any]:
        if df is None:
            _, xg_df, coverage = self.dataset_builder.build_datasets()
            df = xg_df
        else:
            coverage = {
                "fixtures_total": len(df),
                "fixtures_with_xg": int(df["xg_available"].sum()),
            }

        train, test = _temporal_split(df)
        baseline_cols = [c for c in BASELINE_COLS if c in df.columns]
        xg_cols = list(XG_FEATURE_NAMES)
        arm_b_cols = baseline_cols + xg_cols

        # Labels for ML arms
        fg_train = train.copy()
        fg_test = test.copy()
        fg_train["label_fg_binary"] = (fg_train["label_first_goal_team"] == "home").astype(int)
        fg_test["label_fg_binary"] = (fg_test["label_first_goal_team"] == "home").astype(int)
        fg_train = fg_train[fg_train["label_first_goal_team"].isin(["home", "away"])]
        fg_test = fg_test[fg_test["label_first_goal_team"].isin(["home", "away"])]

        markets: dict[str, Any] = {
            "first_goal_team": {
                "arm_a_baseline": _train_and_eval(
                    fg_train, fg_test, baseline_cols, "label_fg_binary", multiclass=False
                ),
                "arm_b_xg": _train_and_eval(
                    fg_train, fg_test, arm_b_cols, "label_fg_binary", multiclass=False
                ),
            },
            "goal_range": {
                "arm_a_baseline": _train_and_eval(
                    train, test, baseline_cols, "label_goal_range", multiclass=True
                ),
                "arm_b_xg": _train_and_eval(train, test, arm_b_cols, "label_goal_range", multiclass=True),
            },
            "team_goals": {
                "arm_a_baseline": _train_and_eval(
                    train, test, baseline_cols, "label_over_25", multiclass=False
                ),
                "arm_b_xg": _train_and_eval(train, test, arm_b_cols, "label_over_25", multiclass=False),
            },
        }

        baseline_engine = aggregate_backtest_results(_baseline_engine_rows(test))
        for key, block in markets.items():
            a = block.get("arm_a_baseline") or {}
            b = block.get("arm_b_xg") or {}
            block["delta"] = {}
            if a.get("status") == "ok" and b.get("status") == "ok":
                block["delta"] = {
                    "accuracy": round(float(b["accuracy"]) - float(a["accuracy"]), 4),
                    "log_loss": round(float(b["log_loss"]) - float(a["log_loss"]), 4),
                    "brier_score": (
                        round(float(b["brier_score"]) - float(a["brier_score"]), 4)
                        if b.get("brier_score") is not None and a.get("brier_score") is not None
                        else None
                    ),
                    "calibration_ece": (
                        round(float(b["calibration_ece"]) - float(a["calibration_ece"]), 4)
                        if b.get("calibration_ece") is not None and a.get("calibration_ece") is not None
                        else None
                    ),
                }

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "54F",
            "backtest_only": True,
            "production_changes": False,
            "coverage": coverage,
            "train_size": len(train),
            "test_size": len(test),
            "markets": markets,
            "egie_rule_baseline_engine": baseline_engine,
            "feature_importance_top20": _feature_importance_ranked({"markets": markets}),
        }

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / "ab_test_results.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        return result

    @staticmethod
    def recommend_value(result: dict[str, Any]) -> str:
        deltas = []
        for market in (result.get("markets") or {}).values():
            d = market.get("delta") or {}
            if d.get("accuracy") is not None:
                deltas.append(float(d["accuracy"]))
        if not deltas:
            return "NO_VALUE"
        avg = sum(deltas) / len(deltas)
        if avg >= 0.08:
            return "VERY_HIGH_VALUE"
        if avg >= 0.05:
            return "HIGH_VALUE"
        if avg >= 0.02:
            return "MEDIUM_VALUE"
        if avg > 0:
            return "LOW_VALUE"
        return "NO_VALUE"
