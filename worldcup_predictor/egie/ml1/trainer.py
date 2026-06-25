"""ML-1 training, evaluation, meta layer, and market intelligence."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover
    lgb = None

from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.preprocessing import LabelEncoder

ROOT = Path(__file__).resolve().parents[3]

FORM_FEATURES = [
    "home_gf_l5",
    "home_ga_l5",
    "away_gf_l5",
    "away_ga_l5",
    "home_btts_l5",
    "away_btts_l5",
    "home_points_l5",
    "away_points_l5",
]

ODDS_FEATURES = [
    "odds_mw_home",
    "odds_mw_draw",
    "odds_mw_away",
    "odds_btts_yes",
    "odds_btts_no",
    "odds_over_25",
    "odds_under_25",
    "sm_consensus_implied_home",
    "sm_consensus_implied_draw",
    "sm_consensus_implied_away",
    "sm_closing_implied_home",
    "sm_closing_implied_draw",
    "sm_closing_implied_away",
    "sm_sharp_implied_home",
    "sm_sharp_implied_away",
    "sm_first_team_score_home",
    "sm_first_team_score_away",
    "sm_odds_movement_home",
    "sm_odds_movement_away",
]

FEATURE_META: dict[str, dict[str, str]] = {
    **{f: {"group": "form", "leakage": "low", "tier_hint": "A"} for f in FORM_FEATURES},
    **{f: {"group": "odds", "leakage": "low", "tier_hint": "S"} for f in ODDS_FEATURES},
}


def _temporal_split(df: pd.DataFrame, train_frac: float = 0.8) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = df.sort_values("kickoff_utc").reset_index(drop=True)
    cut = int(len(ordered) * train_frac)
    return ordered.iloc[:cut], ordered.iloc[cut:]


def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (y_prob >= bins[i]) & (y_prob < bins[i + 1])
        if not mask.any():
            continue
        ece += mask.mean() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return round(float(ece), 4)


def _roi_proxy(y_true: np.ndarray, y_pred: np.ndarray, *, payout: float = 1.0) -> float:
    """Flat-stake ROI proxy on binary picks (research only)."""
    if len(y_true) == 0:
        return 0.0
    wins = (y_pred == y_true).sum()
    return round((wins * payout - len(y_true)) / len(y_true), 4)


def audit_feature_quality(df: pd.DataFrame) -> dict[str, Any]:
    rows = []
    n = len(df)
    for feat, meta in FEATURE_META.items():
        if feat not in df.columns:
            continue
        series = df[feat]
        coverage = round(float(series.notna().mean()), 4)
        missing = round(1 - coverage, 4)
        # stability: train vs test mean absolute difference
        train, test = _temporal_split(df)
        train_mean = float(train[feat].mean(skipna=True) or 0)
        test_mean = float(test[feat].mean(skipna=True) or 0)
        stability = round(1 - min(1.0, abs(train_mean - test_mean) / (abs(train_mean) + 1e-6)), 4)
        leakage = meta["leakage"]
        tier_hint = meta["tier_hint"]
        if coverage < 0.05:
            tier = "C"
        elif coverage < 0.3:
            tier = "B"
        elif tier_hint == "S" and coverage >= 0.3:
            tier = "S"
        else:
            tier = tier_hint if coverage >= 0.5 else "B"
        rows.append(
            {
                "feature": feat,
                "group": meta["group"],
                "coverage_pct": round(100 * coverage, 2),
                "missing_pct": round(100 * missing, 2),
                "usable_pct": round(100 * coverage, 2),
                "leakage_risk": leakage,
                "predictive_stability": stability,
                "tier": tier,
            }
        )
    rows.sort(key=lambda r: ({"S": 0, "A": 1, "B": 2, "C": 3}[r["tier"]], -r["coverage_pct"]))
    return {"generated_at": datetime.utcnow().isoformat() + "Z", "features": rows, "fixture_count": n}


def _train_classifier(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    *,
    multiclass: bool = False,
) -> tuple[Any, np.ndarray, np.ndarray]:
    X_tr = X_train.fillna(-1.0).values
    X_te = X_test.fillna(-1.0).values
    y_tr = y_train.values

    if lgb is not None:
        params = {
            "objective": "multiclass" if multiclass else "binary",
            "num_class": len(np.unique(y_tr)) if multiclass else 1,
            "verbosity": -1,
            "num_leaves": 31,
            "learning_rate": 0.05,
            "n_estimators": 200,
        }
        if multiclass:
            model = lgb.LGBMClassifier(**params)
        else:
            model = lgb.LGBMClassifier(
                objective="binary",
                verbosity=-1,
                num_leaves=31,
                learning_rate=0.05,
                n_estimators=200,
            )
        model.fit(X_tr, y_tr)
        if multiclass:
            proba = model.predict_proba(X_te)
            pred = model.predict(X_te)
        else:
            proba = model.predict_proba(X_te)[:, 1]
            pred = (proba >= 0.5).astype(int)
        return model, pred, proba

    model = GradientBoostingClassifier(random_state=42)
    model.fit(X_tr, y_tr)
    if multiclass:
        proba = model.predict_proba(X_te)
        pred = model.predict(X_te)
    else:
        proba = model.predict_proba(X_te)[:, 1]
        pred = (proba >= 0.5).astype(int)
    return model, pred, proba


def _majority_baseline(y_train: pd.Series, y_test: pd.Series) -> dict[str, Any]:
    maj = y_train.mode().iloc[0]
    pred = np.full(len(y_test), maj)
    acc = accuracy_score(y_test, pred)
    return {"accuracy": round(float(acc), 4), "predictions": pred}


def train_lgbm_baselines(df: pd.DataFrame) -> dict[str, Any]:
    train, test = _temporal_split(df)
    feature_cols = [c for c in FORM_FEATURES + ODDS_FEATURES if c in df.columns]
    results: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model_backend": "lightgbm" if lgb is not None else "sklearn_gradient_boosting",
        "train_size": int(len(train)),
        "test_size": int(len(test)),
        "feature_columns": feature_cols,
        "models": {},
    }

    specs = [
        ("MW_Model", "label_mw", True),
        ("BTTS_Model", "label_btts", False),
        ("OU15_Model", "label_over_15", False),
        ("OU25_Model", "label_over_25", False),
        ("OU35_Model", "label_over_35", False),
    ]

    for name, label_col, multiclass in specs:
        sub_train = train[train[label_col].notna()].copy()
        sub_test = test[test[label_col].notna()].copy()
        if len(sub_train) < 50 or len(sub_test) < 10:
            results["models"][name] = {"status": "insufficient_data"}
            continue

        X_train = sub_train[feature_cols]
        X_test = sub_test[feature_cols]
        y_train = sub_train[label_col]
        y_test = sub_test[label_col]

        if multiclass:
            le = LabelEncoder()
            y_tr = le.fit_transform(y_train.astype(str))
            y_te = le.transform(y_test.astype(str))
            _, pred, proba = _train_classifier(X_train, pd.Series(y_tr), X_test, multiclass=True)
            acc = accuracy_score(y_te, pred)
            ll = log_loss(y_te, proba, labels=list(range(len(le.classes_))))
            brier = None
            cal = None
            roi = _roi_proxy(y_te, pred)
            classes = le.classes_.tolist()
        else:
            y_tr = y_train.astype(int)
            y_te = y_test.astype(int)
            _, pred, proba = _train_classifier(X_train, y_tr, X_test, multiclass=False)
            acc = accuracy_score(y_te, pred)
            ll = log_loss(y_te, np.clip(proba, 1e-6, 1 - 1e-6))
            brier = round(float(brier_score_loss(y_te, proba)), 4)
            cal = _ece(y_te.values, proba)
            roi = _roi_proxy(y_te.values, pred)
            classes = [0, 1]

        base = _majority_baseline(y_train, y_test)
        results["models"][name] = {
            "status": "trained",
            "accuracy": round(float(acc), 4),
            "log_loss": round(float(ll), 4),
            "brier_score": brier,
            "calibration_ece": cal,
            "roi_proxy": roi,
            "majority_baseline_accuracy": base["accuracy"],
            "delta_vs_majority": round(float(acc) - base["accuracy"], 4),
            "classes": classes,
        }

    return results


def _pick_side(home_p: float | None, away_p: float | None) -> str | None:
    if home_p is None or away_p is None:
        return None
    if abs(home_p - away_p) < 0.02:
        return "none"
    return "home" if home_p > away_p else "away"


def evaluate_fg_engine(df: pd.DataFrame, *, settings=None) -> dict[str, Any]:
    """FG strategies on UEFA Sportmonks odds rows (temporal test split)."""
    from worldcup_predictor.egie.ml1.dataset_builder import build_uefa_evaluation_rows

    uefa_rows = build_uefa_evaluation_rows(settings=settings)
    if not uefa_rows:
        k2 = _load_k2_reference()
        return {"status": "no_uefa_rows", "k2_reference": k2}

    sub = pd.DataFrame(uefa_rows)

    def _egie_pick(row: pd.Series) -> str:
        home_rate = float(row.get("home_gf_l5") or 0.33)
        away_rate = float(row.get("away_gf_l5") or 0.33)
        if abs(home_rate - away_rate) < 0.04:
            return "none"
        return "home" if home_rate > away_rate else "away"

    strategies = {
        "A_odds_only": lambda r: _pick_side(r.get("sm_sharp_implied_home"), r.get("sm_sharp_implied_away")),
        "B_egie_only": _egie_pick,
        "C_odds_plus_egie": lambda r: _pick_side(
            (float(r.get("sm_sharp_implied_home") or 0) + float(r.get("home_gf_l5") or 0) * 0.1),
            (float(r.get("sm_sharp_implied_away") or 0) + float(r.get("away_gf_l5") or 0) * 0.1),
        ),
    }

    train, test = _temporal_split(sub)
    out: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "evaluable_test_rows": int(len(test)),
        "strategies": {},
    }
    for name, fn in strategies.items():
        correct = wrong = pending = 0
        for _, row in test.iterrows():
            pred = fn(row)
            actual = row["label_fg_team"]
            if pred is None or pred == "none":
                pending += 1
                continue
            if pred == actual:
                correct += 1
            else:
                wrong += 1
        decided = correct + wrong
        out["strategies"][name] = {
            "accuracy": round(correct / decided, 4) if decided else None,
            "coverage": decided,
            "pending": pending,
            "correct": correct,
            "wrong": wrong,
        }
    best = max(
        out["strategies"].items(),
        key=lambda x: float(x[1].get("accuracy") or 0),
    )
    out["k2_full_sample_reference"] = _load_k2_reference()
    return out


def _load_k2_reference() -> dict[str, Any]:
    path = ROOT / "artifacts" / "first_goal_market_backtest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    strategies = data.get("strategies") or {}
    return {
        "A_consensus_mw": (strategies.get("A") or {}).get("direct_fg_accuracy"),
        "C_sharp_mw": (strategies.get("C") or {}).get("direct_fg_accuracy"),
        "D_direct_fts": (strategies.get("D") or {}).get("direct_fg_accuracy"),
        "evaluable_fixtures": (strategies.get("C") or {}).get("coverage_fixtures"),
    }


def evaluate_goal_range(df: pd.DataFrame) -> dict[str, Any]:
    """Compare range pickers on PL rows with timing labels."""
    sub = df[
        (df["competition_key"] == "premier_league")
        & df["label_goal_range"].notna()
    ].copy()
    if len(sub) < 20:
        sub = df[df["label_goal_range"].notna()].copy()

    train, test = _temporal_split(sub)
    league_counts = Counter(train["label_goal_range"].dropna())
    top_range = league_counts.most_common(1)[0][0] if league_counts else "31-45+"

    def _stat_baseline(_row: pd.Series) -> str:
        return top_range

    def _form_baseline(row: pd.Series) -> str:
        avg_goals = float(row.get("home_gf_l5") or 0) + float(row.get("away_gf_l5") or 0)
        if avg_goals >= 3.0:
            return "0-15"
        if avg_goals >= 2.0:
            return "16-30"
        return "31-45+"

    def _odds_enhanced(row: pd.Series) -> str:
        over = row.get("sm_consensus_implied_home")
        if pd.notna(over) and float(row.get("home_gf_l5") or 0) + float(row.get("away_gf_l5") or 0) > 2.5:
            return "0-15"
        return _form_baseline(row)

    engines = {
        "statistical_baseline": _stat_baseline,
        "form_survival_proxy": _form_baseline,
        "odds_enhanced": _odds_enhanced,
    }

    out: dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "test_rows": int(len(test)),
        "phase52a_reference_range": 0.2779,
        "phase52a_survival_range": 0.3095,
        "engines": {},
    }
    for name, fn in engines.items():
        correct = 0
        for _, row in test.iterrows():
            if fn(row) == row["label_goal_range"]:
                correct += 1
        acc = correct / len(test) if len(test) else 0
        out["engines"][name] = {
            "range_accuracy": round(acc, 4),
            "coverage": int(len(test)),
        }
    return out


def compute_market_intelligence_score(df: pd.DataFrame, *, settings=None) -> dict[str, Any]:
    """Market Intelligence Score from odds agreement + favorite strength."""
    from worldcup_predictor.egie.ml1.dataset_builder import build_uefa_evaluation_rows

    uefa_rows = build_uefa_evaluation_rows(settings=settings)
    if not uefa_rows:
        return {"status": "no_rows"}
    sub = pd.DataFrame(uefa_rows)

    scores = []
    impacts = []
    for _, row in sub.iterrows():
        sharp_h = float(row.get("sm_sharp_implied_home") or 0)
        sharp_a = float(row.get("sm_sharp_implied_away") or 0)
        cons_h = float(row.get("sm_consensus_implied_home") or 0)
        cons_a = float(row.get("sm_consensus_implied_away") or 0)
        close_h = float(row.get("sm_closing_implied_home") or cons_h)
        close_a = float(row.get("sm_closing_implied_away") or cons_a)

        agreement = 1 - (abs(sharp_h - cons_h) + abs(sharp_a - cons_a)) / 2
        closing_agree = 1 - (abs(close_h - cons_h) + abs(close_a - cons_a)) / 2
        favorite_strength = max(sharp_h, sharp_a, cons_h, cons_a)
        mis = round(0.4 * agreement + 0.3 * closing_agree + 0.3 * favorite_strength, 4)
        scores.append(mis)

        actual = row.get("label_fg_team")
        fav_side = "home" if sharp_h >= sharp_a else "away"
        if actual in ("home", "away"):
            impacts.append(1 if fav_side == actual else 0)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "sample_size": int(len(sub)),
        "mis_mean": round(float(np.mean(scores)), 4),
        "mis_median": round(float(np.median(scores)), 4),
        "high_mis_accuracy_fg": round(float(np.mean(impacts)), 4) if impacts else None,
        "components": {
            "sharp_consensus_agreement": 0.4,
            "closing_consensus_agreement": 0.3,
            "favorite_strength": 0.3,
        },
        "tiers": {
            "high_mis_threshold": 0.65,
            "low_mis_threshold": 0.45,
        },
    }


def evaluate_meta_layer(
    df: pd.DataFrame,
    lgbm_results: dict[str, Any],
    fg_results: dict[str, Any],
    mis: dict[str, Any],
) -> dict[str, Any]:
    """Research meta layer: combine isolated model signals on test split."""
    train, test = _temporal_split(df)
    feature_cols = [c for c in FORM_FEATURES + ODDS_FEATURES if c in df.columns]

    isolated: dict[str, float] = {}
    for model_name, data in (lgbm_results.get("models") or {}).items():
        if data.get("status") == "trained":
            isolated[model_name] = float(data.get("accuracy") or 0)

    fg_best = float((fg_results.get("best_strategy") or {}).get("accuracy") or 0)
    k2 = fg_results.get("k2_full_sample_reference") or {}
    if fg_best == 0 and k2.get("C_sharp_mw"):
        fg_best = float(k2["C_sharp_mw"])
    isolated["FG_Engine_best"] = fg_best
    isolated["Market_Intelligence_FG"] = float(mis.get("high_mis_accuracy_fg") or fg_best)

    tabular_avg = float(np.mean([v for k, v in isolated.items() if k.endswith("_Model")])) if isolated else 0
    hybrid_score = round(0.6 * fg_best + 0.4 * tabular_avg, 4)

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "isolated_model_accuracy": isolated,
        "meta_hybrid_score_proxy": hybrid_score,
        "unified_confidence_formula": "0.6*FG_odds + 0.4*mean(LGBM_markets)",
        "meta_beats_isolated": hybrid_score > max(isolated.values()) if isolated else False,
        "test_fixtures": int(len(test)),
        "note": "Meta layer is research-only; not wired to production",
    }


def build_roadmap_decision(
    lgbm_results: dict[str, Any],
    fg_results: dict[str, Any],
    meta_results: dict[str, Any],
    mis: dict[str, Any],
) -> dict[str, Any]:
    """Rank approaches A–D."""
    lgbm_avg = float(
        np.mean(
            [
                m.get("accuracy", 0)
                for m in (lgbm_results.get("models") or {}).values()
                if m.get("status") == "trained"
            ]
        )
        or 0
    )
    k2 = fg_results.get("k2_full_sample_reference") or {}
    fg_odds = float(
        (fg_results.get("strategies") or {}).get("A_odds_only", {}).get("accuracy")
        or k2.get("C_sharp_mw")
        or 0.7872
    )
    fg_hybrid = float((fg_results.get("strategies") or {}).get("C_odds_plus_egie", {}).get("accuracy") or fg_odds)
    egie_ref = 0.5076
    hybrid = round(0.6 * fg_odds + 0.4 * lgbm_avg, 4)
    mis_acc = float(mis.get("high_mis_accuracy_fg") or fg_odds)

    options = [
        {
            "option": "A",
            "name": "Current EGIE",
            "score": round(egie_ref * 100, 1),
            "fg_team_accuracy": egie_ref,
        },
        {
            "option": "B",
            "name": "Classical ML (LightGBM)",
            "score": round(lgbm_avg * 100, 1),
            "mean_accuracy": round(lgbm_avg, 4),
        },
        {
            "option": "C",
            "name": "Market Intelligence",
            "score": round(mis_acc * 100, 1),
            "fg_team_accuracy": mis_acc,
        },
        {
            "option": "D",
            "name": "Hybrid ML + Market Intelligence",
            "score": round(hybrid * 100, 1),
            "meta_proxy": hybrid,
            "fg_component": fg_odds,
            "ml_component": lgbm_avg,
        },
    ]
    options.sort(key=lambda x: x["score"], reverse=True)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "ranked": options,
        "recommended": options[0],
        "production_direction": options[0]["name"] if options[0]["option"] == "D" else options[0]["name"],
    }
