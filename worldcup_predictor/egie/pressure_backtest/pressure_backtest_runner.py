"""A/B/C/D pressure shadow backtest for EGIE-related markets."""

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

from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import ARTIFACT_DIR, PressureDatasetBuilder
from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import (
    PRESSURE_FEATURE_NAMES,
    PRESSURE_LITE_FEATURES,
)
from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS

MIN_TRAIN = 8
MIN_TEST = 5


def _temporal_split(df: pd.DataFrame, train_frac: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "kickoff_utc" not in df.columns:
        ordered = df.reset_index(drop=True)
    else:
        ordered = df.sort_values("kickoff_utc").reset_index(drop=True)
    pressure_rows = ordered[ordered["pressure_available"] == True]  # noqa: E712
    if len(pressure_rows) >= MIN_TRAIN + MIN_TEST:
        split_at = max(MIN_TRAIN, len(pressure_rows) - max(MIN_TEST, len(pressure_rows) // 3))
        p_train = pressure_rows.iloc[:split_at]
        p_test = pressure_rows.iloc[split_at:]
        non_p = ordered[ordered["pressure_available"] == False]  # noqa: E712
        cut = max(1, int(len(non_p) * train_frac)) if len(non_p) else 0
        train = pd.concat([non_p.iloc[:cut], p_train]).drop_duplicates(
            subset=[c for c in ("sportmonks_fixture_id", "goal_index") if c in df.columns]
        )
        test = pd.concat([non_p.iloc[cut:], p_test]).drop_duplicates(
            subset=[c for c in ("sportmonks_fixture_id", "goal_index") if c in df.columns]
        )
        if "sportmonks_fixture_id" in df.columns:
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


def _train_and_eval(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    *,
    multiclass: bool = False,
    require_pressure: bool = True,
) -> dict[str, Any]:
    avail_cols = [c for c in feature_cols if c in train.columns]
    sub_train = train[train[label_col].notna()].copy()
    sub_test = test[test[label_col].notna()].copy()
    if require_pressure:
        sub_train = sub_train[sub_train["pressure_available"] == True]  # noqa: E712
        sub_test = sub_test[sub_test["pressure_available"] == True]  # noqa: E712
    if len(sub_train) < MIN_TRAIN or len(sub_test) < MIN_TEST:
        return {
            "status": "insufficient_data",
            "train_n": len(sub_train),
            "test_n": len(sub_test),
            "min_train": MIN_TRAIN,
            "min_test": MIN_TEST,
        }

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

    return {
        "status": "ok",
        "train_n": len(sub_train),
        "test_n": len(sub_test),
        "accuracy": round(float(acc), 4),
        "log_loss": round(float(ll), 4) if ll is not None else None,
        "brier_score": brier,
        "precision": round(float(prec), 4),
        "recall": round(float(rec), 4),
        "calibration_ece": cal,
        "feature_importance": importance,
    }


def _delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    if a.get("status") != "ok" or b.get("status") != "ok":
        return {}
    return {
        "accuracy": round(float(b["accuracy"]) - float(a["accuracy"]), 4),
        "log_loss": round(float(b["log_loss"]) - float(a["log_loss"]), 4) if b.get("log_loss") is not None else None,
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


def _classify_pressure_features(pooled: dict[str, float]) -> list[dict[str, Any]]:
    if not pooled:
        return []
    max_imp = max(pooled.values()) if pooled else 1.0
    ranked = sorted(pooled.items(), key=lambda x: x[1], reverse=True)
    out: list[dict[str, Any]] = []
    for feat, imp in ranked:
        if imp >= max_imp * 0.6:
            bucket = "strongest_positive"
        elif imp >= max_imp * 0.25:
            bucket = "weak_positive"
        elif imp >= max_imp * 0.08:
            bucket = "neutral"
        else:
            bucket = "harmful"
        out.append({"feature": feat, "importance_sum": round(imp, 6), "bucket": bucket})
    return out


def _pool_pressure_importance(markets: dict[str, Any]) -> dict[str, float]:
    pooled: dict[str, float] = {}
    for market in markets.values():
        arm_b = market.get("arm_b_baseline_plus_pressure") or {}
        for feat, imp in (arm_b.get("feature_importance") or {}).items():
            if feat in PRESSURE_FEATURE_NAMES:
                pooled[feat] = pooled.get(feat, 0.0) + float(imp)
    return pooled


class PressureBacktestRunner:
    """Run A/B/C/D arms on pressure shadow datasets."""

    def __init__(self) -> None:
        self.dataset_builder = PressureDatasetBuilder()

    def _run_market_block(
        self,
        train: pd.DataFrame,
        test: pd.DataFrame,
        label_col: str,
        *,
        multiclass: bool,
        binary_col: str | None = None,
    ) -> dict[str, Any]:
        baseline_cols = [c for c in BASELINE_COLS if c in train.columns]
        pressure_cols = list(PRESSURE_FEATURE_NAMES)
        lite_cols = [c for c in PRESSURE_LITE_FEATURES if c in train.columns]
        arm_b_cols = baseline_cols + pressure_cols
        use_col = binary_col or label_col

        block = {
            "arm_a_baseline": _train_and_eval(
                train, test, baseline_cols, use_col, multiclass=multiclass, require_pressure=True
            ),
            "arm_b_baseline_plus_pressure": _train_and_eval(
                train, test, arm_b_cols, use_col, multiclass=multiclass, require_pressure=True
            ),
            "arm_c_pressure_only": _train_and_eval(
                train, test, pressure_cols, use_col, multiclass=multiclass, require_pressure=True
            ),
            "arm_d_pressure_lite": _train_and_eval(
                train, test, lite_cols, use_col, multiclass=multiclass, require_pressure=True
            ),
        }
        block["delta_b_vs_a"] = _delta(block["arm_a_baseline"], block["arm_b_baseline_plus_pressure"])
        block["delta_c_vs_a"] = _delta(block["arm_a_baseline"], block["arm_c_pressure_only"])
        block["delta_d_vs_a"] = _delta(block["arm_a_baseline"], block["arm_d_pressure_lite"])
        return block

    def run(
        self,
        prematch_df: pd.DataFrame | None = None,
        inplay_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        if prematch_df is None or inplay_df is None:
            prematch_df, inplay_df, coverage, _ = self.dataset_builder.build_datasets()
        else:
            coverage = {
                "prematch_rows": len(prematch_df),
                "inplay_rows": len(inplay_df),
            }

        pm_train, pm_test = _temporal_split(prematch_df)
        ip_train, ip_test = _temporal_split(inplay_df)

        fg_train = pm_train[pm_train["label_first_goal_team"].isin(["home", "away"])].copy()
        fg_test = pm_test[pm_test["label_first_goal_team"].isin(["home", "away"])].copy()
        fg_train["label_fg_binary"] = (fg_train["label_first_goal_team"] == "home").astype(int)
        fg_test["label_fg_binary"] = (fg_test["label_first_goal_team"] == "home").astype(int)

        ng_train = ip_train[ip_train["label_next_goal_team"].isin(["home", "away"])].copy()
        ng_test = ip_test[ip_test["label_next_goal_team"].isin(["home", "away"])].copy()
        ng_train["label_ng_binary"] = (ng_train["label_next_goal_team"] == "home").astype(int)
        ng_test["label_ng_binary"] = (ng_test["label_next_goal_team"] == "home").astype(int)

        prematch_markets = {
            "first_goal_team": self._run_market_block(
                fg_train, fg_test, "label_first_goal_team", multiclass=False, binary_col="label_fg_binary"
            ),
            "goal_range": self._run_market_block(pm_train, pm_test, "label_goal_range", multiclass=True),
        }
        inplay_markets = {
            "next_goal_team": self._run_market_block(
                ng_train, ng_test, "label_next_goal_team", multiclass=False, binary_col="label_ng_binary"
            ),
            "goal_minute_bucket": self._run_market_block(
                ip_train, ip_test, "label_goal_minute_bucket", multiclass=True
            ),
        }

        all_markets = {**{f"prematch_{k}": v for k, v in prematch_markets.items()}, **{f"inplay_{k}": v for k, v in inplay_markets.items()}}
        pooled = _pool_pressure_importance(all_markets)
        feature_importance = {
            "ranked": _classify_pressure_features(pooled),
            "special_attention": {
                feat: pooled.get(feat)
                for feat in (
                    "pressure_first_15_home",
                    "pressure_first_15_away",
                    "pressure_first_30_home",
                    "pressure_first_30_away",
                    "pressure_spike_count_home",
                    "pressure_spike_count_away",
                    "pressure_dominance",
                    "pressure_swing",
                    "pressure_before_first_goal_home",
                    "pressure_before_first_goal_away",
                )
            },
        }

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "54H-1",
            "backtest_only": True,
            "production_changes": False,
            "wde_changes": False,
            "saas_changes": False,
            "coverage": coverage,
            "prematch_train_size": len(pm_train),
            "prematch_test_size": len(pm_test),
            "inplay_train_size": len(ip_train),
            "inplay_test_size": len(ip_test),
            "markets": {
                "prematch": prematch_markets,
                "inplay": inplay_markets,
            },
            "feature_importance": feature_importance,
            "recommendation": self.recommend_value(all_markets),
        }

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / "backtest_results.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        (ARTIFACT_DIR / "feature_importance.json").write_text(
            json.dumps(feature_importance, indent=2, default=str), encoding="utf-8"
        )
        return result

    @staticmethod
    def recommend_value(markets: dict[str, Any]) -> str:
        ok_markets = 0
        deltas: list[float] = []
        for market in markets.values():
            b = market.get("arm_b_baseline_plus_pressure") or {}
            if b.get("status") != "ok":
                continue
            ok_markets += 1
            d = (market.get("delta_b_vs_a") or {}).get("accuracy")
            if d is not None:
                deltas.append(float(d))
        if ok_markets == 0:
            return "PRESSURE_INSUFFICIENT_DATA"
        avg = sum(deltas) / len(deltas) if deltas else 0.0
        if avg >= 0.05:
            return "PRESSURE_HIGH_VALUE"
        if avg >= 0.02:
            return "PRESSURE_MEDIUM_VALUE"
        if avg > 0:
            return "PRESSURE_LOW_VALUE"
        return "PRESSURE_NO_VALUE"
