"""Phase 54F-7 — market-specific xG optimization (isolated tracks per market)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS
from worldcup_predictor.egie.xg_backtest.full_revalidation import (
    _bootstrap_accuracy_delta,
    _fit_eval,
    _temporal_train_val_test,
)
from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XG_FEATURE_NAMES

ARTIFACT_DIR = Path("artifacts/phase54f7_market_specific_xg")
DATASET_PATH = Path("artifacts/phase54f6_expanded_dataset/expanded_egie_dataset.parquet")

# Strongest features from 54F-6B pooled importance
XG_TOP10: tuple[str, ...] = (
    "away_recent_xga",
    "home_recent_xga",
    "rolling_xg_10_away",
    "rolling_xg_3_away",
    "xg_momentum_difference",
    "rolling_xg_10_home",
    "rolling_xg_3_home",
    "defensive_weakness_difference",
    "attack_strength_difference",
    "xg_difference",
)

XG_TOP5: tuple[str, ...] = XG_TOP10[:5]

XG_LITE: tuple[str, ...] = (
    "away_recent_xga",
    "home_recent_xga",
    "rolling_xg_10_away",
    "rolling_xg_3_away",
    "xg_momentum_difference",
    "defensive_weakness_difference",
)

# Candidates to remove per 54F-6B
XG_REMOVE_CANDIDATES: tuple[str, ...] = (
    "home_recent_xg",
    "away_recent_xg",
    "rolling_xg_5_home",
    "rolling_xg_5_away",
    "rolling_xga_3_home",
    "rolling_xga_3_away",
    "rolling_xga_5_home",
    "rolling_xga_5_away",
    "rolling_xga_10_home",
    "rolling_xga_10_away",
)


def _market_frames(df: pd.DataFrame, market: str) -> tuple[pd.DataFrame, pd.DataFrame, str, bool]:
    train, val, test = _temporal_train_val_test(df)
    fit_pool = pd.concat([train, val]).drop_duplicates("sportmonks_fixture_id")
    if market == "first_goal_team":
        fit = fit_pool[fit_pool["label_first_goal_team"].isin(["home", "away"])].copy()
        te = test[test["label_first_goal_team"].isin(["home", "away"])].copy()
        fit["label"] = (fit["label_first_goal_team"] == "home").astype(int)
        te["label"] = (te["label_first_goal_team"] == "home").astype(int)
        return fit, te, "label", False
    if market == "goal_range":
        return fit_pool, test, "label_goal_range", True
    if market == "team_goals":
        return fit_pool, test, "label_over_25", False
    raise ValueError(f"unknown_market:{market}")


def _eval_arm(
    fit: pd.DataFrame,
    test: pd.DataFrame,
    label_col: str,
    feature_cols: list[str],
    *,
    multiclass: bool,
    arm_name: str,
) -> dict[str, Any]:
    result = _fit_eval(fit, test, feature_cols, label_col, multiclass=multiclass)
    out = {k: v for k, v in result.items() if k not in ("y_true", "y_pred", "y_proba")}
    out["arm"] = arm_name
    if result.get("status") == "ok":
        boot = _bootstrap_accuracy_delta(result["y_true"], result["y_pred"], result["y_pred"])
        # For non-baseline comparison, caller replaces bootstrap with paired preds
        out["_y_true"] = result["y_true"]
        out["_y_pred"] = result["y_pred"]
    return out


def _compare_to_baseline(baseline: dict, arm: dict) -> dict[str, Any]:
    if baseline.get("status") != "ok" or arm.get("status") != "ok":
        return {"status": "insufficient_data"}
    boot = _bootstrap_accuracy_delta(baseline["_y_true"], baseline["_y_pred"], arm["_y_pred"])
    return {
        "accuracy_delta": round(arm["accuracy"] - baseline["accuracy"], 4),
        "log_loss_delta": (
            round(arm["log_loss"] - baseline["log_loss"], 4)
            if baseline.get("log_loss") is not None and arm.get("log_loss") is not None
            else None
        ),
        "brier_delta": (
            round(arm["brier_score"] - baseline["brier_score"], 4)
            if baseline.get("brier_score") is not None and arm.get("brier_score") is not None
            else None
        ),
        "calibration_delta": (
            round(arm["calibration_ece"] - baseline["calibration_ece"], 4)
            if baseline.get("calibration_ece") is not None and arm.get("calibration_ece") is not None
            else None
        ),
        "confidence_delta": round(arm["confidence_mean"] - baseline["confidence_mean"], 4),
        "bootstrap": boot,
        "test_n": arm.get("test_n"),
    }


def _strip_internal(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def _run_arms(
    fit: pd.DataFrame,
    test: pd.DataFrame,
    label_col: str,
    *,
    multiclass: bool,
    include_xg_only: bool = True,
) -> dict[str, Any]:
    baseline_cols = [c for c in BASELINE_COLS if c in fit.columns]
    full_xg = baseline_cols + list(XG_FEATURE_NAMES)
    top10 = baseline_cols + list(XG_TOP10)
    top5 = baseline_cols + list(XG_TOP5)
    lite = baseline_cols + list(XG_LITE)
    xg_only = list(XG_FEATURE_NAMES)

    arms_spec = [
        ("baseline", baseline_cols),
        ("full_xg", full_xg),
        ("top10_xg", top10),
        ("top5_xg", top5),
        ("xg_lite", lite),
    ]
    if include_xg_only:
        arms_spec.append(("xg_only", xg_only))

    raw: dict[str, dict] = {}
    for name, cols in arms_spec:
        raw[name] = _eval_arm(fit, test, label_col, cols, multiclass=multiclass, arm_name=name)

    baseline = raw["baseline"]
    compared: dict[str, Any] = {}
    for name, arm in raw.items():
        entry = _strip_internal(arm)
        if name != "baseline":
            entry["vs_baseline"] = _compare_to_baseline(baseline, arm)
        compared[name] = entry

    compared["full_vs_lite"] = {}
    if raw.get("full_xg", {}).get("status") == "ok" and raw.get("xg_lite", {}).get("status") == "ok":
        compared["full_vs_lite"] = _compare_to_baseline(raw["full_xg"], raw["xg_lite"])
        compared["full_vs_lite"]["interpretation"] = (
            "lite_better" if compared["full_vs_lite"].get("accuracy_delta", 0) > 0 else "full_better_or_equal"
        )

    return compared


def _first_goal_feature_audit(fit: pd.DataFrame, test: pd.DataFrame, label_col: str) -> dict[str, Any]:
    baseline_cols = [c for c in BASELINE_COLS if c in fit.columns]
    baseline = _eval_arm(fit, test, label_col, baseline_cols, multiclass=False, arm_name="baseline")
    full = _eval_arm(
        fit, test, label_col, baseline_cols + list(XG_FEATURE_NAMES), multiclass=False, arm_name="full_xg"
    )
    delta = _compare_to_baseline(baseline, full)

    harmful: list[str] = []
    neutral: list[str] = []
    unstable: list[str] = []

    imp = (full.get("feature_importance") or {}) if full.get("status") == "ok" else {}
    xg_imp = {k: float(v) for k, v in imp.items() if k in XG_FEATURE_NAMES}
    total_xg = sum(xg_imp.values()) or 1.0

    for feat in XG_FEATURE_NAMES:
        share = xg_imp.get(feat, 0) / total_xg
        if share >= 0.08:
            harmful.append(feat)
        elif share >= 0.03:
            unstable.append(feat)
        else:
            neutral.append(feat)

    consistently_hurts = delta.get("accuracy_delta", 0) < -0.02 and delta.get("bootstrap", {}).get("p_improve", 1) < 0.25

    return {
        "baseline": _strip_internal(baseline),
        "full_xg": _strip_internal(full),
        "vs_baseline": delta,
        "feature_contribution": {
            "harmful": harmful,
            "neutral": neutral,
            "unstable": unstable,
            "xg_feature_importance": {k: round(v, 6) for k, v in sorted(xg_imp.items(), key=lambda x: -x[1])},
        },
        "recommendation": "NO_XG_FOR_FIRST_GOAL_TEAM" if consistently_hurts else "RESEARCH_ONLY",
    }


def _classify_all_features(market_results: dict[str, Any]) -> list[dict[str, Any]]:
    """Classify each xG feature using per-market arm deltas and importance."""
    pooled_imp: dict[str, float] = {f: 0.0 for f in XG_FEATURE_NAMES}
    market_delta: dict[str, float] = {}

    for market in ("goal_range", "team_goals"):
        block = market_results.get(market) or {}
        full = block.get("arms", {}).get("full_xg") or {}
        vs = full.get("vs_baseline") or {}
        market_delta[market] = float(vs.get("accuracy_delta") or 0)
        for feat, val in (full.get("feature_importance") or {}).items():
            if feat in XG_FEATURE_NAMES:
                pooled_imp[feat] += float(val)

    fg = market_results.get("first_goal_team") or {}
    fg_delta = float((fg.get("vs_baseline") or {}).get("accuracy_delta") or 0)

    ranked = sorted(pooled_imp.items(), key=lambda x: -x[1])
    total = sum(pooled_imp.values()) or 1.0
    out: list[dict[str, Any]] = []

    fg_harmful = set((fg.get("feature_contribution") or {}).get("harmful", []))
    benefits_other = any(market_delta.get(m, 0) > 0 for m in market_delta)

    for feat, imp in ranked:
        share = imp / total
        in_remove = feat in XG_REMOVE_CANDIDATES
        if share >= 0.08 and benefits_other:
            cls = "STRONG_POSITIVE"
        elif share >= 0.03 and benefits_other:
            cls = "WEAK_POSITIVE"
        elif fg_delta < -0.02 and feat in fg_harmful:
            cls = "HARMFUL"
        elif in_remove and share < 0.03:
            cls = "REMOVE"
        elif in_remove:
            cls = "REMOVE"
        else:
            cls = "NEUTRAL"
        out.append({"feature": feat, "importance_sum": round(imp, 6), "share_pct": round(100 * share, 2), "classification": cls})

    return out


def _production_readiness(market: str, arms: dict[str, Any], fg_rec: str | None = None) -> str:
    if market == "first_goal_team":
        return "NO_VALUE" if fg_rec == "NO_XG_FOR_FIRST_GOAL_TEAM" else "RESEARCH_ONLY"

    best_name = _best_arm(arms)
    if best_name == "baseline":
        return "NO_VALUE"

    best = arms.get(best_name) or {}
    vs = best.get("vs_baseline") or {}
    acc_d = float(vs.get("accuracy_delta") or 0)
    boot = vs.get("bootstrap") or {}
    sig = boot.get("statistically_significant") and boot.get("interpretation") == "meaningful"
    ll = vs.get("log_loss_delta")
    brier = vs.get("brier_delta")
    cal = vs.get("calibration_delta")

    secondary_ok = (ll is not None and ll < 0) or (brier is not None and brier < 0) or (cal is not None and cal < 0)

    if acc_d >= 0.03 and (sig or secondary_ok):
        return "PRODUCTION_READY"
    if acc_d > 0 or secondary_ok:
        return "RESEARCH_ONLY"
    return "NO_VALUE"


def _best_arm(arms: dict[str, Any]) -> str:
    best_name = "baseline"
    best_delta = 0.0
    for name, arm in arms.items():
        if name in ("full_vs_lite",):
            continue
        vs = arm.get("vs_baseline") or {}
        d = float(vs.get("accuracy_delta") or 0)
        if d > best_delta:
            best_delta = d
            best_name = name
    return best_name


class MarketSpecificXgOptimizer:
    def __init__(self, dataset_path: Path | None = None) -> None:
        self.dataset_path = dataset_path or DATASET_PATH

    def run(self) -> dict[str, Any]:
        df = pd.read_parquet(self.dataset_path)
        results: dict[str, Any] = {}

        # Track A — First Goal Team
        fit, test, label, multi = _market_frames(df, "first_goal_team")
        fg_audit = _first_goal_feature_audit(fit, test, label)
        results["first_goal_team"] = {
            "track": "A",
            "test_n": fg_audit.get("full_xg", {}).get("test_n"),
            **fg_audit,
        }

        # Track B — Goal Range
        fit, test, label, multi = _market_frames(df, "goal_range")
        gr_arms = _run_arms(fit, test, label, multiclass=multi)
        results["goal_range"] = {
            "track": "B",
            "test_n": (gr_arms.get("baseline") or {}).get("test_n"),
            "arms": gr_arms,
            "best_arm": _best_arm(gr_arms),
            "production_readiness": _production_readiness("goal_range", gr_arms),
        }

        # Track C — Team Goals
        fit, test, label, multi = _market_frames(df, "team_goals")
        tg_arms = _run_arms(fit, test, label, multiclass=multi)
        results["team_goals"] = {
            "track": "C",
            "test_n": (tg_arms.get("baseline") or {}).get("test_n"),
            "arms": tg_arms,
            "best_arm": _best_arm(tg_arms),
            "production_readiness": _production_readiness("team_goals", tg_arms),
        }

        feature_pruning = _classify_all_features(results)
        remain = [f["feature"] for f in feature_pruning if f["classification"] in ("STRONG_POSITIVE", "WEAK_POSITIVE")]
        remove = [f["feature"] for f in feature_pruning if f["classification"] in ("HARMFUL", "REMOVE")]

        lite_vs_full_gr = (gr_arms.get("full_vs_lite") or {})
        lite_vs_full_tg = (tg_arms.get("full_vs_lite") or {})
        lite_wins = sum(
            1
            for d in (lite_vs_full_gr.get("accuracy_delta"), lite_vs_full_tg.get("accuracy_delta"))
            if d is not None and float(d) > 0
        )

        final_rec = self._final_recommendation(results, lite_wins)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "54F-7",
            "dataset_path": str(self.dataset_path),
            "usable_fixtures": len(df),
            "markets": results,
            "feature_pruning": feature_pruning,
            "features_to_remain": remain,
            "features_to_remove": remove,
            "xg_lite_features": list(XG_LITE),
            "xg_lite_vs_full": {
                "goal_range": lite_vs_full_gr,
                "team_goals": lite_vs_full_tg,
                "lite_outperforms_full_markets": lite_wins,
            },
            "production_readiness": {
                "first_goal_team": _production_readiness(
                    "first_goal_team", {}, fg_rec=results["first_goal_team"]["recommendation"]
                ),
                "goal_range": results["goal_range"]["production_readiness"],
                "team_goals": results["team_goals"]["production_readiness"],
            },
            "first_goal_team_xg_policy": results["first_goal_team"]["recommendation"],
            "final_recommendation": final_rec,
        }

    @staticmethod
    def _final_recommendation(results: dict[str, Any], lite_wins: int) -> str:
        fg = results.get("first_goal_team", {}).get("recommendation") == "NO_XG_FOR_FIRST_GOAL_TEAM"
        gr = results.get("goal_range", {}).get("production_readiness")
        tg = results.get("team_goals", {}).get("production_readiness")
        if gr == "PRODUCTION_READY" or tg == "PRODUCTION_READY":
            return "XG_PRODUCTION_FOR_SPECIFIC_MARKETS"
        if gr == "RESEARCH_ONLY" or tg == "RESEARCH_ONLY" or lite_wins >= 1:
            return "CONTINUE_XG_RESEARCH"
        if fg and gr == "NO_VALUE" and tg == "NO_VALUE":
            return "XG_NO_VALUE"
        return "XG_RESEARCH_ONLY"

    def save(self, output_dir: Path | None = None) -> dict[str, Any]:
        out = output_dir or ARTIFACT_DIR
        out.mkdir(parents=True, exist_ok=True)
        result = self.run()
        (out / "market_specific_optimization.json").write_text(
            json.dumps(result, indent=2, default=str), encoding="utf-8"
        )
        return result
