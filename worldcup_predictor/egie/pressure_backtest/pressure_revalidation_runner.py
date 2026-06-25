"""Phase 54H-2 revalidation with proxy-control arms E/F and bootstrap CI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import LabelEncoder

from worldcup_predictor.egie.pressure_backtest.minute_proxy_audit import _bootstrap_accuracy_ci, _eval_with_bootstrap
from worldcup_predictor.egie.pressure_backtest.pressure_backtest_runner import (
    MIN_TEST,
    MIN_TRAIN,
    _delta,
    _temporal_split,
    _train_and_eval,
)
from worldcup_predictor.egie.pressure_backtest.pressure_dataset_builder import ARTIFACT_DIR_H2, PressureDatasetBuilder
from worldcup_predictor.egie.pressure_backtest.pressure_feature_builder import (
    MINUTE_ONLY_FEATURES,
    PRESSURE_FEATURE_NAMES,
    PRESSURE_LITE_FEATURES,
    PRESSURE_WITHOUT_MINUTE_PROXY,
)
from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS

ARTIFACT_DIR = ARTIFACT_DIR_H2

SPECIAL_FEATURES = (
    "pressure_spike_count_away",
    "pressure_before_first_goal_away",
    "pressure_momentum",
    "pressure_first_15_home",
    "pressure_dominance",
    "pressure_swing",
)


def _classify_proxy_aware(pooled: dict[str, float], proxy_audit: dict[str, Any]) -> list[dict[str, Any]]:
    if not pooled:
        return []
    max_imp = max(pooled.values())
    minute_risk_high = proxy_audit.get("proxy_risk_verdict") == "MINUTE_PROXY_RISK_HIGH"
    ranked = sorted(pooled.items(), key=lambda x: x[1], reverse=True)
    out: list[dict[str, Any]] = []
    proxy_feats = set(
        (
            "pressure_first_15_home",
            "pressure_first_15_away",
            "pressure_first_30_home",
            "pressure_first_30_away",
            "pressure_last_5_home",
            "pressure_last_5_away",
            "pressure_last_10_home",
            "pressure_last_10_away",
            "pressure_before_first_goal_home",
            "pressure_before_first_goal_away",
        )
    )
    for feat, imp in ranked:
        if imp >= max_imp * 0.55:
            bucket = "minute_proxy" if feat in proxy_feats and minute_risk_high else "robust_signal"
        elif imp >= max_imp * 0.2:
            bucket = "minute_proxy" if feat in proxy_feats else "robust_signal"
        elif imp >= max_imp * 0.06:
            bucket = "unstable"
        else:
            bucket = "harmful"
        out.append({"feature": feat, "importance_sum": round(imp, 6), "bucket": bucket})
    return out


class PressureRevalidationRunner:
    """Re-run 54H-1 arms plus minute-control arms on expanded datasets."""

    def __init__(self) -> None:
        self.dataset_builder = PressureDatasetBuilder()

    def _market_block(
        self,
        train: pd.DataFrame,
        test: pd.DataFrame,
        label_col: str,
        *,
        multiclass: bool,
        binary_col: str | None = None,
        include_minute_arms: bool = False,
        require_pressure: bool = True,
    ) -> dict[str, Any]:
        baseline_cols = [c for c in BASELINE_COLS if c in train.columns]
        pressure_cols = [c for c in PRESSURE_FEATURE_NAMES if c in train.columns]
        lite_cols = [c for c in PRESSURE_LITE_FEATURES if c in train.columns]
        no_minute_cols = [c for c in PRESSURE_WITHOUT_MINUTE_PROXY if c in train.columns]
        minute_cols = [c for c in MINUTE_ONLY_FEATURES if c in train.columns]
        use_col = binary_col or label_col

        eval_fn = _eval_with_bootstrap
        block = {
            "arm_a_baseline": eval_fn(
                train, test, baseline_cols, use_col, multiclass=multiclass, require_pressure=require_pressure
            ),
            "arm_b_pressure_full": eval_fn(
                train,
                test,
                baseline_cols + pressure_cols,
                use_col,
                multiclass=multiclass,
                require_pressure=require_pressure,
            ),
            "arm_c_pressure_only": eval_fn(
                train, test, pressure_cols, use_col, multiclass=multiclass, require_pressure=require_pressure
            ),
            "arm_d_pressure_lite": eval_fn(
                train, test, lite_cols, use_col, multiclass=multiclass, require_pressure=require_pressure
            ),
        }
        if include_minute_arms:
            block["arm_e_minute_only"] = eval_fn(
                train, test, minute_cols, use_col, multiclass=multiclass, require_pressure=require_pressure
            )
            block["arm_f_pressure_without_minute"] = eval_fn(
                train, test, no_minute_cols, use_col, multiclass=multiclass, require_pressure=require_pressure
            )
            block["delta_f_vs_e"] = _delta(block["arm_e_minute_only"], block["arm_f_pressure_without_minute"])

        block["delta_b_vs_a"] = _delta(block["arm_a_baseline"], block["arm_b_pressure_full"])
        block["delta_c_vs_a"] = _delta(block["arm_a_baseline"], block["arm_c_pressure_only"])
        block["delta_d_vs_a"] = _delta(block["arm_a_baseline"], block["arm_d_pressure_lite"])
        return block

    def run(
        self,
        prematch_df: pd.DataFrame | None = None,
        inplay_df: pd.DataFrame | None = None,
        proxy_audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if prematch_df is None or inplay_df is None:
            prematch_df, inplay_df, coverage, _ = self.dataset_builder.build_datasets(phase="54H-2")
        else:
            coverage = {"prematch_rows": len(prematch_df), "inplay_rows": len(inplay_df)}

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

        prematch = {
            "first_goal_team": self._market_block(
                fg_train, fg_test, "label_first_goal_team", multiclass=False, binary_col="label_fg_binary"
            ),
            "goal_range": self._market_block(pm_train, pm_test, "label_goal_range", multiclass=True),
        }
        inplay = {
            "next_goal_team": self._market_block(
                ng_train,
                ng_test,
                "label_next_goal_team",
                multiclass=False,
                binary_col="label_ng_binary",
                include_minute_arms=True,
            ),
            "goal_minute_bucket": self._market_block(
                ip_train,
                ip_test,
                "label_goal_minute_bucket",
                multiclass=True,
                include_minute_arms=True,
            ),
        }

        pooled: dict[str, float] = {}
        for section in (prematch, inplay):
            for market in section.values():
                arm_b = market.get("arm_b_pressure_full") or {}
                for feat, imp in (arm_b.get("feature_importance") or {}).items():
                    if feat in PRESSURE_FEATURE_NAMES:
                        pooled[feat] = pooled.get(feat, 0.0) + float(imp)

        proxy_audit = proxy_audit or {}
        feature_importance = {
            "ranked": _classify_proxy_aware(pooled, proxy_audit),
            "special_attention": {feat: pooled.get(feat) for feat in SPECIAL_FEATURES},
        }

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "54H-2",
            "backtest_only": True,
            "production_changes": False,
            "coverage": coverage,
            "prematch_train_size": len(pm_train),
            "prematch_test_size": len(pm_test),
            "inplay_train_size": len(ip_train),
            "inplay_test_size": len(ip_test),
            "markets": {"prematch": prematch, "inplay": inplay},
            "feature_importance": feature_importance,
            "minute_proxy_audit_summary": proxy_audit.get("comparison") or {},
            "proxy_risk_verdict": proxy_audit.get("proxy_risk_verdict"),
            "recommendation": self.recommend(proxy_audit, inplay, prematch, coverage),
        }

        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        (ARTIFACT_DIR / "revalidation_results.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        (ARTIFACT_DIR / "feature_importance.json").write_text(
            json.dumps(feature_importance, indent=2, default=str), encoding="utf-8"
        )
        return result

    @staticmethod
    def recommend(
        proxy_audit: dict[str, Any],
        inplay: dict[str, Any],
        prematch: dict[str, Any],
        coverage: dict[str, Any],
    ) -> str:
        fixtures = int(coverage.get("fixtures_with_pressure") or 0)
        if fixtures < 100:
            if proxy_audit.get("proxy_risk_verdict") == "MINUTE_PROXY_RISK_HIGH":
                return "PRESSURE_PROXY_RISK_HIGH"
            return "PRESSURE_INSUFFICIENT_DATA"

        if proxy_audit.get("proxy_risk_verdict") == "MINUTE_PROXY_RISK_HIGH":
            return "PRESSURE_PROXY_RISK_HIGH"

        comp = (proxy_audit.get("comparison") or {})
        true_lift = float(comp.get("true_pressure_lift_after_controlling_minute") or 0.0)
        ng_delta = ((inplay.get("next_goal_team") or {}).get("delta_b_vs_a") or {}).get("accuracy")
        ng_delta = float(ng_delta) if ng_delta is not None else 0.0

        if true_lift >= 0.05 and ng_delta >= 0.02:
            return "PRESSURE_HIGH_VALUE"
        if true_lift >= 0.02 or ng_delta >= 0.015:
            return "PRESSURE_MEDIUM_VALUE"
        if true_lift > 0 or ng_delta > 0:
            return "PRESSURE_LOW_VALUE"
        return "PRESSURE_INSUFFICIENT_DATA"
