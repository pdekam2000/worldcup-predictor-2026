"""GBGM-1 — Gradient Boosted Goal Model (shadow challenger).

Compares available boosting backends on identical data:
- LightGBM (if installed)
- sklearn HistGradientBoosting (always available via scikit-learn)
- XGBoost / CatBoost optional if installed

Does not copy WDE/ECSE outputs. Score distribution labeled GBGM_SCORE_DISTRIBUTION.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from worldcup_predictor.challenger.constants import GBGM_MODEL_ID_PREFIX
from worldcup_predictor.challenger.feature_contract import DEFAULT_GBGM_CONTRACT
from worldcup_predictor.challenger.models.base import ChallengerModel

FEATURE_ORDER = list(DEFAULT_GBGM_CONTRACT.required) + [
    "is_home",
    "home_l5_sample",
    "away_l5_sample",
    "league_sample_before_cutoff",
    "implied_home",
    "implied_draw",
    "implied_away",
    "bookmaker_count",
    "market_odds_usable",
]


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def goals_to_markets(lam_h: float, lam_a: float, *, max_goals: int = 7) -> dict[str, Any]:
    lam_h = max(0.05, float(lam_h))
    lam_a = max(0.05, float(lam_a))
    ph = [_poisson_pmf(i, lam_h) for i in range(max_goals + 1)]
    pa = [_poisson_pmf(j, lam_a) for j in range(max_goals + 1)]
    grid = []
    p_home = p_draw = p_away = 0.0
    p_btts_yes = 0.0
    p_over = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j]
            grid.append({"score": f"{i}-{j}", "probability": p, "home_goals": i, "away_goals": j})
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if i >= 1 and j >= 1:
                p_btts_yes += p
            if i + j >= 3:
                p_over += p
    grid.sort(key=lambda r: -r["probability"])
    top10 = [{"rank": i + 1, "score": g["score"], "probability": round(g["probability"], 6)} for i, g in enumerate(grid[:10])]
    top5 = top10[:5]
    mass3 = sum(x["probability"] for x in top10[:3])
    mass5 = sum(x["probability"] for x in top10[:5])
    # entropy of top10 renormalized
    s = sum(x["probability"] for x in top10) or 1.0
    ent = -sum((x["probability"] / s) * math.log(x["probability"] / s) for x in top10 if x["probability"] > 0)
    s_hda = p_home + p_draw + p_away
    if s_hda > 0:
        p_home, p_draw, p_away = p_home / s_hda, p_draw / s_hda, p_away / s_hda
    return {
        "expected_home_goals": round(lam_h, 4),
        "expected_away_goals": round(lam_a, 4),
        "hda": {"home": round(p_home, 4), "draw": round(p_draw, 4), "away": round(p_away, 4)},
        "decision_1x2": max([("home", p_home), ("draw", p_draw), ("away", p_away)], key=lambda t: t[1])[0],
        "btts_yes": round(p_btts_yes, 4),
        "btts_no": round(max(0.0, 1.0 - p_btts_yes), 4),
        "btts_selection": "yes" if p_btts_yes >= 0.5 else "no",
        "ou25_over": round(p_over, 4),
        "ou25_under": round(max(0.0, 1.0 - p_over), 4),
        "ou25_selection": "over_2_5" if p_over >= 0.5 else "under_2_5",
        "top1_score": top10[0]["score"] if top10 else None,
        "top10": top10,
        "top5": top5,
        "top3_mass": round(mass3, 6),
        "top5_mass": round(mass5, 6),
        "entropy": round(ent, 6),
        "distribution_family": "GBGM_SCORE_DISTRIBUTION",
        "max_goals": max_goals,
    }


def _matrix(rows: list[dict[str, Any]], feature_cols: list[str]) -> np.ndarray:
    mat = []
    for r in rows:
        mat.append([float(r[c]) if r.get(c) is not None else np.nan for c in feature_cols])
    return np.asarray(mat, dtype=float)


class GBGMChallenger(ChallengerModel):
    def __init__(self, *, variant: str = "NM", backend: str = "lightgbm", model_version: str = "GBGM-1.0.0"):
        assert variant in {"NM", "MC"}
        self.variant = variant
        self.backend = backend
        self.model_id = f"{GBGM_MODEL_ID_PREFIX}-{variant}-{backend}"
        self.model_version = model_version
        self.feature_cols = list(FEATURE_ORDER)
        if variant == "NM":
            self.feature_cols = [c for c in self.feature_cols if not c.startswith("implied_") and c not in {"bookmaker_count", "market_odds_usable"}]
        self.model_home = None
        self.model_away = None
        self.train_meta: dict[str, Any] = {}

    def required_features(self) -> tuple[str, ...]:
        return tuple(self.feature_cols)

    def _make_regressor(self):
        if self.backend == "lightgbm":
            import lightgbm as lgb

            return lgb.LGBMRegressor(
                n_estimators=120,
                learning_rate=0.05,
                num_leaves=31,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
                verbosity=-1,
            )
        if self.backend == "xgboost":
            import xgboost as xgb

            return xgb.XGBRegressor(
                n_estimators=120,
                learning_rate=0.05,
                max_depth=5,
                subsample=0.9,
                colsample_bytree=0.9,
                random_state=42,
                objective="reg:squarederror",
            )
        if self.backend == "catboost":
            from catboost import CatBoostRegressor

            return CatBoostRegressor(
                iterations=120,
                learning_rate=0.05,
                depth=6,
                random_seed=42,
                verbose=False,
            )
        # sklearn fallback / explicit
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(max_depth=6, learning_rate=0.05, max_iter=120, random_state=42)

    def fit(self, X, y_home, y_away, *, sample_meta: dict[str, Any] | None = None) -> dict[str, Any]:
        if isinstance(X, list):
            X = _matrix(X, self.feature_cols)
        # Impute nan with column medians (training only — recorded)
        col_med = np.nanmedian(X, axis=0)
        inds = np.where(np.isnan(X))
        X = X.copy()
        X[inds] = np.take(col_med, inds[1])
        self._col_med = col_med
        self.model_home = self._make_regressor()
        self.model_away = self._make_regressor()
        self.model_home.fit(X, np.asarray(y_home, dtype=float))
        self.model_away.fit(X, np.asarray(y_away, dtype=float))
        self.train_meta = {
            "n": int(X.shape[0]),
            "backend": self.backend,
            "variant": self.variant,
            "feature_cols": self.feature_cols,
            "col_medians": [None if (isinstance(v, float) and math.isnan(v)) else float(v) for v in col_med.tolist()],
            "sample_meta": sample_meta or {},
            "random_seed": 42,
        }
        return self.train_meta

    def _transform(self, X):
        if isinstance(X, dict):
            X = _matrix([X], self.feature_cols)
        elif isinstance(X, list):
            X = _matrix(X, self.feature_cols)
        X = np.asarray(X, dtype=float).copy()
        med = getattr(self, "_col_med", np.nanmedian(X, axis=0))
        inds = np.where(np.isnan(X))
        X[inds] = np.take(med, inds[1])
        return X

    def predict(self, X) -> dict[str, Any]:
        if self.model_home is None or self.model_away is None:
            raise RuntimeError("model_not_fitted")
        Xm = self._transform(X)
        yh = np.clip(self.model_home.predict(Xm), 0.05, 6.0)
        ya = np.clip(self.model_away.predict(Xm), 0.05, 6.0)
        if len(yh) == 1:
            return goals_to_markets(float(yh[0]), float(ya[0]))
        return {"batch": [goals_to_markets(float(h), float(a)) for h, a in zip(yh, ya)]}

    def serialize_metadata(self) -> dict[str, Any]:
        base = super().serialize_metadata()
        base.update({"variant": self.variant, "backend": self.backend, "train_meta": self.train_meta})
        return base


def available_backends() -> list[str]:
    # Prefer LightGBM; sklearn HistGBM is optional secondary (can fail on low-cardinality features).
    out: list[str] = []
    try:
        import lightgbm  # noqa: F401

        out.append("lightgbm")
    except Exception:
        pass
    try:
        import xgboost  # noqa: F401

        out.append("xgboost")
    except Exception:
        pass
    try:
        import catboost  # noqa: F401

        out.append("catboost")
    except Exception:
        pass
    # Always keep a simple sklearn fallback last
    out.append("sklearn_hist")
    return out
