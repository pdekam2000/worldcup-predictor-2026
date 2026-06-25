"""Phase 54F-6B — full xG revalidation on expanded dataset (statistical + confidence)."""

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

from worldcup_predictor.egie.xg_backtest.egie_xg_dataset_builder import BASELINE_COLS
from worldcup_predictor.egie.xg_backtest.xg_backtest_runner import _ece, _temporal_split
from worldcup_predictor.egie.xg_backtest.xg_feature_builder import XG_FEATURE_NAMES

ARTIFACT_DIR = Path("artifacts/phase54f6b_full_xg_revalidation")
DATASET_PATH = Path("artifacts/phase54f6_expanded_dataset/expanded_egie_dataset.parquet")

LEAGUE_LABELS = {
    "world_cup": "World Cup",
    "champions_league": "Champions League",
    "europa_league": "Europa League",
    "conference_league": "Conference League",
}


def _temporal_train_val_test(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values("kickoff_utc").reset_index(drop=True)
    n = len(ordered)
    t1 = int(n * 0.6)
    t2 = int(n * 0.8)
    if t1 < 1:
        t1 = 1
    if t2 <= t1:
        t2 = min(n - 1, t1 + 1)
    return ordered.iloc[:t1], ordered.iloc[t1:t2], ordered.iloc[t2:]


def verify_dataset(df: pd.DataFrame) -> dict[str, Any]:
    train, val, test = _temporal_train_val_test(df)
    by_league: dict[str, dict[str, int]] = {}
    for key, label in LEAGUE_LABELS.items():
        sub = df[df["competition_key"] == key]
        by_league[label] = {
            "total": int(len(sub)),
            "train": int(len(train[train["competition_key"] == key])),
            "validation": int(len(val[val["competition_key"] == key])),
            "test": int(len(test[test["competition_key"] == key])),
            "first_goal_labeled": int(sub["label_first_goal_team"].notna().sum()),
            "goal_range_labeled": int(sub["label_goal_range"].notna().sum()),
            "team_goals_labeled": int(sub["label_over_25"].notna().sum()),
            "rolling_xg_available": int(sub["rolling_xg_available"].sum()) if "rolling_xg_available" in sub else 0,
        }
    by_season = (
        df.groupby("season_id")
        .agg(
            total=("sportmonks_fixture_id", "count"),
            rolling_xg=("rolling_xg_available", "sum"),
        )
        .reset_index()
        .to_dict(orient="records")
    )
    return {
        "total_fixtures": len(df),
        "usable_fixtures": int(df["xg_available"].sum()) if "xg_available" in df.columns else len(df),
        "train_fixtures": len(train),
        "validation_fixtures": len(val),
        "test_fixtures": len(test),
        "rolling_xg_3": int((df["rolling_xg_3_home"].notna() & df["rolling_xg_3_away"].notna()).sum()),
        "rolling_xg_5": int((df["rolling_xg_5_home"].notna() & df["rolling_xg_5_away"].notna()).sum()),
        "rolling_xg_10": int((df["rolling_xg_10_home"].notna() & df["rolling_xg_10_away"].notna()).sum()),
        "first_goal_labeled": int(df["label_first_goal_team"].notna().sum()),
        "goal_range_labeled": int(df["label_goal_range"].notna().sum()),
        "team_goals_labeled": int(df["label_over_25"].notna().sum()),
        "by_league": by_league,
        "by_season": by_season,
    }


def _sharpness(proba: np.ndarray) -> float:
    if len(proba) == 0:
        return 0.0
    return round(float(np.std(proba)), 4)


def _fit_eval(
    train: pd.DataFrame,
    test: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    *,
    multiclass: bool = False,
) -> dict[str, Any]:
    avail = [c for c in feature_cols if c in train.columns]
    tr = train[train[label_col].notna() & train["xg_available"]].copy()
    te = test[test[label_col].notna() & test["xg_available"]].copy()
    if len(tr) < 5 or len(te) < 5:
        return {"status": "insufficient_data", "train_n": len(tr), "test_n": len(te)}

    X_tr, X_te = tr[avail].fillna(-1.0), te[avail].fillna(-1.0)
    if multiclass:
        le = LabelEncoder()
        y_tr = le.fit_transform(tr[label_col].astype(str))
        y_te = le.transform(te[label_col].astype(str))
        model = GradientBoostingClassifier(random_state=42)
        model.fit(X_tr, y_tr)
        pred = model.predict(X_te)
        proba = model.predict_proba(X_te)
        conf = np.max(proba, axis=1)
        ll = log_loss(y_te, proba, labels=list(range(len(le.classes_))))
        brier = None
        cal = None
    else:
        y_tr = tr[label_col].astype(int).values
        y_te = te[label_col].astype(int).values
        model = GradientBoostingClassifier(random_state=42)
        model.fit(X_tr, y_tr)
        proba_pos = model.predict_proba(X_te)[:, 1]
        pred = (proba_pos >= 0.5).astype(int)
        proba = proba_pos
        conf = np.maximum(proba_pos, 1 - proba_pos)
        try:
            ll = log_loss(y_te, np.clip(proba_pos, 1e-6, 1 - 1e-6), labels=[0, 1])
        except ValueError:
            ll = None
        brier = float(brier_score_loss(y_te, proba_pos))
        cal = _ece(y_te, proba_pos)

    acc = float(accuracy_score(y_te, pred))
    return {
        "status": "ok",
        "train_n": len(tr),
        "test_n": len(te),
        "accuracy": round(acc, 4),
        "log_loss": round(float(ll), 4) if ll is not None else None,
        "brier_score": round(brier, 4) if brier is not None else None,
        "precision": round(float(precision_score(y_te, pred, average="weighted" if multiclass else "binary", zero_division=0)), 4),
        "recall": round(float(recall_score(y_te, pred, average="weighted" if multiclass else "binary", zero_division=0)), 4),
        "calibration_ece": cal,
        "confidence_mean": round(float(np.mean(conf)), 4),
        "probability_sharpness": _sharpness(proba if not multiclass else conf),
        "feature_importance": dict(zip(avail, model.feature_importances_.tolist())),
        "y_true": y_te.tolist() if hasattr(y_te, "tolist") else list(y_te),
        "y_pred": pred.tolist(),
        "y_proba": proba.tolist() if not multiclass else conf.tolist(),
    }


def _bootstrap_accuracy_delta(
    y_true: list,
    pred_a: list,
    pred_b: list,
    *,
    n_boot: int = 1000,
    seed: int = 42,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    ya, yb = np.array(y_true), np.array(y_true)
    pa, pb = np.array(pred_a), np.array(pred_b)
    n = len(ya)
    if n < 10:
        return {"status": "insufficient_data", "n": n}
    deltas = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        acc_a = (pa[idx] == ya[idx]).mean()
        acc_b = (pb[idx] == yb[idx]).mean()
        deltas.append(acc_b - acc_a)
    deltas_arr = np.array(deltas)
    lo, hi = float(np.percentile(deltas_arr, 2.5)), float(np.percentile(deltas_arr, 97.5))
    mean_d = float(np.mean(deltas_arr))
    p_improve = float((deltas_arr > 0).mean())
    significant = (lo > 0) or (hi < 0)
    return {
        "n": n,
        "n_bootstrap": n_boot,
        "accuracy_delta_mean": round(mean_d, 4),
        "ci_95_low": round(lo, 4),
        "ci_95_high": round(hi, 4),
        "p_improve": round(p_improve, 4),
        "statistically_significant": significant,
        "interpretation": "meaningful" if significant else "likely_noise",
    }


def _market_stats(arm_a: dict, arm_b: dict, boot: dict) -> dict[str, Any]:
    d_acc = round(arm_b["accuracy"] - arm_a["accuracy"], 4)
    d_ll = None
    if arm_a.get("log_loss") is not None and arm_b.get("log_loss") is not None:
        d_ll = round(arm_b["log_loss"] - arm_a["log_loss"], 4)
    d_brier = None
    if arm_a.get("brier_score") is not None and arm_b.get("brier_score") is not None:
        d_brier = round(arm_b["brier_score"] - arm_a["brier_score"], 4)
    lift = round(d_acc / arm_a["accuracy"], 4) if arm_a["accuracy"] else None
    rel_pct = round(100 * d_acc / arm_a["accuracy"], 2) if arm_a["accuracy"] else None
    return {
        "baseline": {k: arm_a.get(k) for k in ("accuracy", "log_loss", "brier_score", "precision", "recall", "calibration_ece", "confidence_mean", "probability_sharpness", "test_n")},
        "xg": {k: arm_b.get(k) for k in ("accuracy", "log_loss", "brier_score", "precision", "recall", "calibration_ece", "confidence_mean", "probability_sharpness", "test_n")},
        "delta": {
            "accuracy": d_acc,
            "log_loss": d_ll,
            "brier_score": d_brier,
            "calibration_ece": (
                round(arm_b["calibration_ece"] - arm_a["calibration_ece"], 4)
                if arm_a.get("calibration_ece") is not None and arm_b.get("calibration_ece") is not None
                else None
            ),
            "confidence_mean": round(arm_b["confidence_mean"] - arm_a["confidence_mean"], 4),
            "probability_sharpness": round(arm_b["probability_sharpness"] - arm_a["probability_sharpness"], 4),
        },
        "lift": lift,
        "relative_improvement_pct": rel_pct,
        "bootstrap": boot,
        "confidence_analysis": {
            "calibration_gain": (
                round(arm_a["calibration_ece"] - arm_b["calibration_ece"], 4)
                if arm_a.get("calibration_ece") is not None and arm_b.get("calibration_ece") is not None
                else None
            ),
            "confidence_gain": round(arm_b["confidence_mean"] - arm_a["confidence_mean"], 4),
            "sharpness_delta": round(arm_b["probability_sharpness"] - arm_a["probability_sharpness"], 4),
            "reliability_gain": (
                "improved" if arm_b.get("calibration_ece") is not None and arm_a.get("calibration_ece") is not None and arm_b["calibration_ece"] < arm_a["calibration_ece"]
                else "worse_or_unchanged"
            ),
        },
    }


def classify_features(
    markets: dict[str, Any],
    xg_features: tuple[str, ...] = XG_FEATURE_NAMES,
) -> list[dict[str, Any]]:
    """Classify xG features by importance and market delta direction."""
    pooled: dict[str, float] = {}
    per_market_imp: dict[str, dict[str, float]] = {}
    market_delta: dict[str, float] = {}
    for market, block in markets.items():
        arm_b = block.get("arm_b_xg") or {}
        imp = {k: float(v) for k, v in (arm_b.get("feature_importance") or {}).items() if k in xg_features}
        per_market_imp[market] = imp
        for f, v in imp.items():
            pooled[f] = pooled.get(f, 0.0) + v
        d = (block.get("delta") or {}).get("accuracy")
        if d is not None:
            market_delta[market] = float(d)

    ranked = sorted(pooled.items(), key=lambda x: x[1], reverse=True)
    total = sum(pooled.values()) or 1.0
    out: list[dict[str, Any]] = []
    for rank, (feat, val) in enumerate(ranked[:20], start=1):
        helps = sum(1 for m, d in market_delta.items() if d > 0 and per_market_imp.get(m, {}).get(feat, 0) > 0.01)
        hurts = sum(1 for m, d in market_delta.items() if d < 0 and per_market_imp.get(m, {}).get(feat, 0) > 0.01)
        share = val / total
        if hurts > helps and hurts >= 2:
            cls = "Harmful"
        elif helps >= 2 and share >= 0.05:
            cls = "Strong Positive"
        elif helps >= 1 and share >= 0.02:
            cls = "Weak Positive"
        elif share < 0.02:
            cls = "Neutral"
        else:
            cls = "Neutral"
        out.append(
            {
                "rank": rank,
                "feature": feat,
                "importance_sum": round(val, 6),
                "share_pct": round(100 * share, 2),
                "classification": cls,
            }
        )
    return out


def _market_recommendation(delta_acc: float, boot: dict) -> str:
    sig = boot.get("statistically_significant") and boot.get("interpretation") == "meaningful"
    if delta_acc >= 0.05 and sig:
        return "HIGH_VALUE"
    if delta_acc >= 0.02 and (sig or delta_acc >= 0.03):
        return "MEDIUM_VALUE"
    if delta_acc > 0:
        return "LOW_VALUE"
    if delta_acc <= -0.03 and sig:
        return "HARMFUL"
    return "NO_VALUE"


def final_decision(markets: dict[str, Any]) -> tuple[str, str]:
    deltas = []
    recs = []
    for market, block in markets.items():
        d = (block.get("delta") or {}).get("accuracy")
        boot = (block.get("statistics") or {}).get("bootstrap") or {}
        if d is not None:
            deltas.append(float(d))
            recs.append(_market_recommendation(float(d), boot))
    if not deltas:
        return "NO_VALUE", "XG_NO_VALUE"
    avg = sum(deltas) / len(deltas)
    sig_wins = sum(1 for m in markets.values() if (m.get("statistics") or {}).get("bootstrap", {}).get("statistically_significant"))
    if avg >= 0.08 and sig_wins >= 2:
        tier = "VERY_HIGH_VALUE"
    elif avg >= 0.05:
        tier = "HIGH_VALUE"
    elif avg >= 0.02:
        tier = "MEDIUM_VALUE"
    elif avg > 0:
        tier = "LOW_VALUE"
    else:
        tier = "NO_VALUE"

    if tier in ("VERY_HIGH_VALUE", "HIGH_VALUE", "MEDIUM_VALUE"):
        rec = "CONTINUE_XG_RESEARCH"
    elif tier == "LOW_VALUE":
        rec = "XG_LOW_VALUE"
    else:
        rec = "XG_NO_VALUE"
    return tier, rec


class FullXgRevalidationRunner:
    def __init__(self, dataset_path: Path | None = None) -> None:
        self.dataset_path = dataset_path or DATASET_PATH

    def run(self) -> dict[str, Any]:
        df = pd.read_parquet(self.dataset_path)
        verification = verify_dataset(df)
        train, val, test = _temporal_train_val_test(df)
        # Fit on train+val, evaluate on test (standard holdout)
        fit_pool = pd.concat([train, val]).drop_duplicates("sportmonks_fixture_id")

        baseline_cols = [c for c in BASELINE_COLS if c in df.columns]
        xg_cols = list(XG_FEATURE_NAMES)
        arm_b_cols = baseline_cols + xg_cols

        fg_fit = fit_pool[fit_pool["label_first_goal_team"].isin(["home", "away"])].copy()
        fg_test = test[test["label_first_goal_team"].isin(["home", "away"])].copy()
        fg_fit["label_fg_binary"] = (fg_fit["label_first_goal_team"] == "home").astype(int)
        fg_test["label_fg_binary"] = (fg_test["label_first_goal_team"] == "home").astype(int)

        market_specs = [
            ("first_goal_team", fg_fit, fg_test, "label_fg_binary", False),
            ("goal_range", fit_pool, test, "label_goal_range", True),
            ("team_goals", fit_pool, test, "label_over_25", False),
        ]

        markets: dict[str, Any] = {}
        for name, tr, te, label, multi in market_specs:
            arm_a = _fit_eval(tr, te, baseline_cols, label, multiclass=multi)
            arm_b = _fit_eval(tr, te, arm_b_cols, label, multiclass=multi)
            delta = {}
            if arm_a.get("status") == "ok" and arm_b.get("status") == "ok":
                delta = {
                    "accuracy": round(arm_b["accuracy"] - arm_a["accuracy"], 4),
                    "log_loss": round(arm_b["log_loss"] - arm_a["log_loss"], 4) if arm_a.get("log_loss") is not None else None,
                    "brier_score": (
                        round(arm_b["brier_score"] - arm_a["brier_score"], 4)
                        if arm_a.get("brier_score") is not None and arm_b.get("brier_score") is not None
                        else None
                    ),
                }
                boot = _bootstrap_accuracy_delta(arm_a["y_true"], arm_a["y_pred"], arm_b["y_pred"])
            else:
                boot = {"status": "insufficient_data"}
            stats = _market_stats(arm_a, arm_b, boot)
            markets[name] = {
                "arm_a_baseline": {k: v for k, v in arm_a.items() if k not in ("y_true", "y_pred", "y_proba")},
                "arm_b_xg": {k: v for k, v in arm_b.items() if k not in ("y_true", "y_pred", "y_proba")},
                "delta": delta,
                "statistics": stats,
                "recommendation": _market_recommendation(delta.get("accuracy", 0), boot),
            }

        feature_ranking = classify_features(markets)
        tier, final_rec = final_decision(markets)

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "phase": "54F-6B",
            "dataset_path": str(self.dataset_path),
            "dataset_verification": verification,
            "sample_size_sufficient": verification["usable_fixtures"] >= 300,
            "markets": markets,
            "feature_importance_top20": feature_ranking,
            "final_value_tier": tier,
            "final_recommendation": final_rec,
            "ready_for_54g": False,
        }
        return result

    def save(self, output_dir: Path | None = None) -> dict[str, Any]:
        out = output_dir or ARTIFACT_DIR
        out.mkdir(parents=True, exist_ok=True)
        result = self.run()
        (out / "full_revalidation.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        return result
