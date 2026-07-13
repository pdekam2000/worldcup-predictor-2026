"""Tail-risk models — rule-based and sklearn research models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from worldcup_predictor.research.ecse_prematch_tail_risk.constants import (
    TIER_HIGH,
    TIER_LOW,
    TIER_MEDIUM,
    TIER_VERY_HIGH,
)


@dataclass
class TailRiskPrediction:
    tail_risk_probability: float
    tail_risk_tier: str
    reason_codes: list[str] = field(default_factory=list)
    model_name: str = ""


def rule_based_tail_risk(row: dict[str, Any]) -> TailRiskPrediction:
    """Auditable prematch heuristic baseline."""
    score = 0.0
    reasons: list[str] = []
    tl = float(row.get("total_lambda") or 0)
    tail_mass = float(row.get("canonical_high_score_tail_mass") or 0)
    btts_m = float(row.get("canonical_btts_mass") or 0)
    over25 = float(row.get("implied_over_25") or 0)
    l8_h = row.get("last8_home_scored_in_rate")
    l8_a = row.get("last8_away_scored_in_rate")

    if tl >= 3.0:
        score += 0.25
        reasons.append("HIGH_TOTAL_LAMBDA")
    if tail_mass >= 0.30:
        score += 0.20
        reasons.append("HIGH_ECSE_TAIL_MASS")
    if btts_m >= 0.50:
        score += 0.15
        reasons.append("BTTS_MARKET_SUPPORT")
    if over25 >= 0.55:
        score += 0.15
        reasons.append("OVER_2_5_MARKET_SUPPORT")
    if l8_h is not None and l8_a is not None and l8_h >= 0.6 and l8_a >= 0.6:
        score += 0.15
        reasons.append("BOTH_TEAMS_RECENTLY_SCORE")
    league_tail = row.get("league_high_tail_rate")
    if league_tail is not None and league_tail >= 0.25:
        score += 0.10
        reasons.append("LEAGUE_HIGH_VARIANCE")
    prob_fav_con1 = float(row.get("prob_favourite_concedes_one") or 0)
    if prob_fav_con1 >= 0.25:
        score += 0.10
        reasons.append("UNDERDOG_GOAL_RISK")

    prob = min(max(score, 0.02), 0.98)
    if prob >= 0.65:
        tier = TIER_VERY_HIGH
    elif prob >= 0.45:
        tier = TIER_HIGH
    elif prob >= 0.25:
        tier = TIER_MEDIUM
    else:
        tier = TIER_LOW
    return TailRiskPrediction(prob, tier, reasons, "rule_based")


def tier_from_probability(p: float) -> str:
    if p >= 0.65:
        return TIER_VERY_HIGH
    if p >= 0.45:
        return TIER_HIGH
    if p >= 0.25:
        return TIER_MEDIUM
    return TIER_LOW


def reason_codes_from_row(row: dict[str, Any], prob: float) -> list[str]:
    rb = rule_based_tail_risk(row)
    return rb.reason_codes if prob >= 0.25 else []


class SklearnTailRiskModel:
    """Wrapper for sklearn classifiers with median imputation."""

    def __init__(self, name: str, estimator: Any, feature_columns: tuple[str, ...]) -> None:
        self.name = name
        self.estimator = estimator
        self.feature_columns = feature_columns
        self._medians: dict[str, float] = {}

    def _matrix(self, rows: list[dict[str, Any]], *, fit: bool = False) -> np.ndarray:
        cols = self.feature_columns
        if fit:
            for c in cols:
                vals = [float(r[c]) for r in rows if r.get(c) is not None]
                self._medians[c] = float(np.median(vals)) if vals else 0.0
        X = []
        for r in rows:
            row_vals = []
            for c in cols:
                v = r.get(c)
                row_vals.append(float(v) if v is not None else self._medians.get(c, 0.0))
            X.append(row_vals)
        return np.array(X, dtype=float)

    def fit(self, rows: list[dict[str, Any]], labels: list[int]) -> None:
        X = self._matrix(rows, fit=True)
        y = np.array(labels, dtype=int)
        self.estimator.fit(X, y)

    def predict_proba(self, rows: list[dict[str, Any]]) -> np.ndarray:
        X = self._matrix(rows, fit=False)
        if hasattr(self.estimator, "predict_proba"):
            return self.estimator.predict_proba(X)[:, 1]
        preds = self.estimator.predict(X)
        return preds.astype(float)


def build_sklearn_models(feature_columns: tuple[str, ...]) -> dict[str, SklearnTailRiskModel]:
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    models: dict[str, SklearnTailRiskModel] = {
        "logistic_regression": SklearnTailRiskModel(
            "logistic_regression",
            Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=500, class_weight="balanced"))]),
            feature_columns,
        ),
        "calibrated_tree": SklearnTailRiskModel(
            "calibrated_tree",
            CalibratedClassifierCV(RandomForestClassifier(n_estimators=100, max_depth=8, class_weight="balanced", random_state=42), cv=3),
            feature_columns,
        ),
        "gradient_boosting": SklearnTailRiskModel(
            "gradient_boosting",
            GradientBoostingClassifier(n_estimators=100, max_depth=4, random_state=42),
            feature_columns,
        ),
    }
    return models


def league_aware_predict(
    row: dict[str, Any],
    *,
    global_model: SklearnTailRiskModel,
    league_rates: dict[str, float],
) -> TailRiskPrediction:
    """Blend global model with league prior."""
    prob_g = float(global_model.predict_proba([row])[0])
    lr = league_rates.get(row.get("league") or "unknown", 0.23)
    prob = 0.7 * prob_g + 0.3 * lr
    return TailRiskPrediction(prob, tier_from_probability(prob), reason_codes_from_row(row, prob), "league_aware")
