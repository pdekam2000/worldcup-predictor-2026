"""Backtest, calibration, and confidence tiers for FG Team V2."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import StandardScaler

from worldcup_predictor.egie.first_goal_team_v2.models import (
    BASELINE_54F7_ACCURACY,
    FEATURE_GROUPS,
    GOALSCORER_INTEL_BASELINE_ACCURACY,
    TARGET_COL,
)
from worldcup_predictor.egie.goalscorer_ml_shadow.calibration import expected_calibration_error


def _prepare_xy(df: pd.DataFrame, features: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    cols = [c for c in features if c in df.columns]
    X = df[cols].fillna(0.0).values
    y = df[TARGET_COL].astype(int).values
    return X, y, cols


def _score_group(train: pd.DataFrame, test: pd.DataFrame, group: str) -> dict[str, Any]:
    feats = FEATURE_GROUPS[group]
    X_train, y_train, cols = _prepare_xy(train, feats)
    X_test, y_test, _ = _prepare_xy(test, feats)
    if not cols:
        return {"group": group, "status": "no_features"}

    scaler = StandardScaler()
    Xtr = scaler.fit_transform(X_train)
    Xte = scaler.transform(X_test)
    model = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)
    model.fit(Xtr, y_train)
    proba = model.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)

    acc = round(float(accuracy_score(y_test, pred)), 4)
    brier = round(float(brier_score_loss(y_test, proba)), 4)
    ece = expected_calibration_error(y_test, proba)
    try:
        ll = round(float(log_loss(y_test, np.clip(proba, 1e-6, 1 - 1e-6))), 4)
    except ValueError:
        ll = None

    scored = test.copy()
    scored["fg_prob_home"] = proba
    scored["fg_pred_home"] = pred
    tiers = assign_confidence_tiers(scored)

    return {
        "group": group,
        "status": "ok",
        "features_used": cols,
        "n_train": len(train),
        "n_test": len(test),
        "accuracy": acc,
        "brier": brier,
        "ece": ece,
        "log_loss": ll,
        "tier_metrics": tier_accuracy(tiers),
        "feature_importance": dict(zip(cols, np.abs(model.coef_[0]).round(4).tolist())),
    }


def assign_confidence_tiers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    p = out["fg_prob_home"].astype(float)
    dq = out.get("data_quality_score", pd.Series([0.5] * len(out))).fillna(0.5)

    def _tier(row: pd.Series) -> str:
        prob = float(row["fg_prob_home"])
        dist = abs(prob - 0.5)
        quality = float(row.get("data_quality_score") or 0.5)
        if dist >= 0.20 and quality >= 0.5:
            return "A"
        if dist >= 0.12:
            return "B"
        if dist >= 0.06:
            return "C"
        return "D"

    out["confidence_tier"] = out.apply(_tier, axis=1)
    out["confidence_score"] = (2 * (p - 0.5).abs()).round(4)
    return out


def tier_accuracy(df: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for tier, grp in df.groupby("confidence_tier"):
        if grp.empty:
            continue
        y = grp[TARGET_COL].astype(int)
        pred = grp["fg_pred_home"].astype(int)
        out[str(tier)] = {
            "n": len(grp),
            "accuracy": round(float((pred == y).mean()), 4),
            "mean_confidence": round(float(grp["confidence_score"].mean()), 4),
        }
    return out


def goalscorer_heuristic_baseline(test: pd.DataFrame) -> dict[str, Any]:
    """Pick home if home_top_goals_per_90 > away."""
    sub = test.copy()
    if "home_top_goals_per_90" not in sub.columns:
        return {"status": "missing", "accuracy": None}
    sub["gs_pick_home"] = (sub["home_top_goals_per_90"] > sub["away_top_goals_per_90"]).astype(int)
    acc = float((sub["gs_pick_home"] == sub[TARGET_COL]).mean())
    return {"status": "ok", "accuracy": round(acc, 4), "n": len(sub)}


def run_backtest(df: pd.DataFrame) -> dict[str, Any]:
    train = df[df["split"] == "train"]
    val = df[df["split"] == "val"]
    test = df[df["split"] == "test"]
    if test.empty:
        test = val if not val.empty else train

    results: dict[str, Any] = {"groups": {}, "baselines": {}}
    for group in FEATURE_GROUPS:
        results["groups"][group] = _score_group(train, test, group)

    results["baselines"]["phase54f7_xg"] = BASELINE_54F7_ACCURACY
    results["baselines"]["phase51h_production"] = GOALSCORER_INTEL_BASELINE_ACCURACY
    results["baselines"]["goalscorer_heuristic"] = goalscorer_heuristic_baseline(test)

    best = max(
        (v for v in results["groups"].values() if v.get("status") == "ok"),
        key=lambda x: x.get("accuracy", 0),
        default={},
    )
    results["best_group"] = best.get("group")
    results["best_accuracy"] = best.get("accuracy")
    return results


def feature_family_importance(backtest: dict[str, Any]) -> dict[str, Any]:
    """Rank which feature family contributes most via group deltas."""
    groups = backtest.get("groups") or {}
    base_acc = float((groups.get("baseline") or {}).get("accuracy") or 0)
    deltas = {
        "lineups": float((groups.get("baseline_lineups") or {}).get("accuracy") or 0) - base_acc,
        "goalscorer": float((groups.get("baseline_goalscorer") or {}).get("accuracy") or 0) - base_acc,
        "fts_odds": float((groups.get("baseline_fts_odds") or {}).get("accuracy") or 0) - base_acc,
        "full_blend": float((groups.get("full_blend") or {}).get("accuracy") or 0) - base_acc,
    }
    ranked = sorted(deltas.items(), key=lambda x: x[1], reverse=True)
    return {"baseline_accuracy": base_acc, "family_deltas": deltas, "ranked": ranked}


def decide_recommendation(backtest: dict[str, Any], families: dict[str, Any]) -> dict[str, Any]:
    best_acc = float(backtest.get("best_accuracy") or 0)
    base_acc = float(families.get("baseline_accuracy") or 0)
    lift = round(best_acc - base_acc, 4)
    beats_54f7 = best_acc > BASELINE_54F7_ACCURACY
    beats_gs = best_acc > float((backtest.get("baselines") or {}).get("goalscorer_heuristic", {}).get("accuracy") or 0)

    if best_acc >= 0.65 and lift >= 0.05:
        rec = "FIRST_GOAL_TEAM_ELITE_PATH"
    elif lift >= 0.02 or beats_54f7:
        rec = "FIRST_GOAL_TEAM_HIGH_VALUE"
    else:
        rec = "FIRST_GOAL_TEAM_NO_VALUE"

    return {
        "recommendation": rec,
        "best_group": backtest.get("best_group"),
        "best_accuracy": best_acc,
        "baseline_accuracy": base_acc,
        "lift_vs_baseline_pp": lift,
        "beats_54f7": beats_54f7,
        "beats_goalscorer_heuristic": beats_gs,
    }
