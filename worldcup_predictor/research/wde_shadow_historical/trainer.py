"""Part C — Train shadow WDE tabular models (research only, no production writes)."""



from __future__ import annotations



import json

from datetime import datetime, timezone

from pathlib import Path

from typing import Any



import numpy as np

import pandas as pd

from joblib import dump

from sklearn.base import clone

from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier

from sklearn.linear_model import LogisticRegression

from sklearn.metrics import accuracy_score

from sklearn.preprocessing import LabelEncoder



from worldcup_predictor.research.wde_shadow_historical.constants import METRICS_ARTIFACT, PHASE, TARGETS

from worldcup_predictor.research.wde_shadow_historical.wde_shadow_baselines import (

    accuracy,

    bookmaker_predictions,

    log_loss,

)





def _utc_now() -> str:

    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")





def _select_model_backend() -> tuple[str, Any]:

    try:

        import lightgbm as lgb  # type: ignore



        return "LightGBM", lgb.LGBMClassifier(

            n_estimators=300,

            learning_rate=0.05,

            max_depth=-1,

            num_leaves=31,

            random_state=42,

            verbose=-1,

        )

    except ImportError:

        pass

    return "HistGradientBoostingClassifier", HistGradientBoostingClassifier(max_iter=250, random_state=42)





def _fallback_model(model_type: str) -> Any:

    if model_type == "HistGradientBoostingClassifier":

        return RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)

    return LogisticRegression(max_iter=500, random_state=42)





class FeatureEncoder:

    def __init__(self) -> None:

        self.league_enc = LabelEncoder()

        self.country_enc = LabelEncoder()

        self.medians: dict[str, float] = {}

        self.fitted = False



    def fit(self, df: pd.DataFrame) -> None:

        self.medians = {

            "expectedGoalsHome": float(df["expectedGoalsHome"].median()) if df["expectedGoalsHome"].notna().any() else 1.2,

            "expectedGoalsAway": float(df["expectedGoalsAway"].median()) if df["expectedGoalsAway"].notna().any() else 1.1,

            "cornerKicksHome": float(df["cornerKicksHome"].median()) if "cornerKicksHome" in df and df["cornerKicksHome"].notna().any() else 5.0,

            "cornerKicksAway": float(df["cornerKicksAway"].median()) if "cornerKicksAway" in df and df["cornerKicksAway"].notna().any() else 5.0,

        }

        self.league_enc.fit(df["league"].fillna("unknown").astype(str))

        self.country_enc.fit(df["country"].fillna("unknown").astype(str))

        self.fitted = True



    def transform(self, df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:

        if not self.fitted:

            raise RuntimeError("FeatureEncoder not fitted")

        xg_h = df["expectedGoalsHome"].fillna(self.medians["expectedGoalsHome"])

        xg_a = df["expectedGoalsAway"].fillna(self.medians["expectedGoalsAway"])

        ch = df["cornerKicksHome"].fillna(self.medians["cornerKicksHome"]) if "cornerKicksHome" in df else 5.0

        ca = df["cornerKicksAway"].fillna(self.medians["cornerKicksAway"]) if "cornerKicksAway" in df else 5.0

        year = df["season_year"].fillna(pd.to_datetime(df["date"], errors="coerce").dt.year).fillna(2020)



        leagues = df["league"].fillna("unknown").astype(str)

        countries = df["country"].fillna("unknown").astype(str)

        league_codes = np.array([self.league_enc.transform([v])[0] if v in self.league_enc.classes_ else -1 for v in leagues])

        country_codes = np.array([self.country_enc.transform([v])[0] if v in self.country_enc.classes_ else -1 for v in countries])



        has_xg = df["expectedGoalsHome"].notna().astype(float).to_numpy()

        has_corners = df["cornerKicksHome"].notna().astype(float).to_numpy() if "cornerKicksHome" in df else np.zeros(len(df))

        has_dq = df["data_quality_flags"].notna().astype(float).to_numpy() if "data_quality_flags" in df else np.zeros(len(df))



        cols = [

            "implied_prob_home",

            "implied_prob_draw",

            "implied_prob_away",

            "implied_prob_over_2_5",

            "implied_prob_under_2_5",

            "implied_prob_btts_yes",

            "implied_prob_btts_no",

        ]

        base = df[cols].fillna(0).to_numpy(dtype=float)

        extra = np.column_stack(

            [

                xg_h.to_numpy(),

                xg_a.to_numpy(),

                (xg_h - xg_a).to_numpy(),

                (xg_h + xg_a).to_numpy(),

                ch.to_numpy() if hasattr(ch, "to_numpy") else np.full(len(df), float(ch)),

                ca.to_numpy() if hasattr(ca, "to_numpy") else np.full(len(df), float(ca)),

                year.to_numpy(),

                league_codes,

                country_codes,

                has_xg,

                has_corners,

                has_dq,

            ]

        )

        feature_names = cols + [

            "xg_home",

            "xg_away",

            "xg_diff",

            "xg_total",

            "corners_home",

            "corners_away",

            "season_year",

            "league_code",

            "country_code",

            "has_xg",

            "has_corners",

            "has_dq_flag",

        ]

        return np.hstack([base, extra]), feature_names





def train_shadow_models(

    train_df: pd.DataFrame,

    val_df: pd.DataFrame,

    *,

    model_dir: Path,

    process_date: str | None = None,

) -> dict[str, Any]:

    model_dir.mkdir(parents=True, exist_ok=True)

    if train_df.empty or val_df.empty:

        out = {"phase": PHASE, "status": "skipped", "reason": "insufficient_data", "model_dir": str(model_dir)}

        METRICS_ARTIFACT.write_text(json.dumps(out, indent=2), encoding="utf-8")

        return out



    model_type, model_template = _select_model_backend()

    encoder = FeatureEncoder()

    encoder.fit(train_df)

    x_train, feature_names = encoder.transform(train_df)

    x_val, _ = encoder.transform(val_df)



    dump(encoder, model_dir / "feature_encoder.joblib")



    metrics: dict[str, Any] = {

        "phase": PHASE,

        "generated_at_utc": _utc_now(),

        "model_type": model_type,

        "model_dir": str(model_dir),

        "process_date": process_date,

        "train_rows": len(train_df),

        "val_rows": len(val_df),

        "feature_groups": {

            "implied_market_probs": True,

            "xg_home_away_diff_total": True,

            "corners": True,

            "league_country_encoding": True,

            "season_year": True,

            "data_quality_flags": True,

            "no_final_score_features": True,

        },

        "feature_names": feature_names,

        "markets": {},

    }



    book = bookmaker_predictions(val_df)

    for market, col in TARGETS.items():

        try:

            clf = clone(model_template)

        except Exception:

            clf = _fallback_model(model_type)



        y_train = train_df[col].tolist()

        y_val = val_df[col].tolist()

        try:

            clf.fit(x_train, y_train)

        except Exception:

            clf = _fallback_model(model_type)

            clf.fit(x_train, y_train)

            metrics["markets"].setdefault(market, {})["fallback_used"] = True



        dump(clf, model_dir / f"shadow_{market}.joblib")

        val_pred = clf.predict(x_val)

        val_proba = clf.predict_proba(x_val) if hasattr(clf, "predict_proba") else None

        val_acc = round(float(accuracy_score(y_val, val_pred)), 4)

        book_acc = accuracy(y_val, book[market])

        market_metrics = {

            "val_accuracy": val_acc,

            "val_log_loss": log_loss(y_val, val_proba, list(clf.classes_)) if val_proba is not None else None,

            "bookmaker_baseline_val_accuracy": book_acc,

            "beats_bookmaker_on_val": val_acc > book_acc if book_acc is not None else False,

            "classes": list(clf.classes_),

        }

        metrics["markets"][market] = market_metrics



    meta = {

        "phase": PHASE,

        "feature_names": feature_names,

        "targets": TARGETS,

        "shadow_only": True,

        "no_production_writes": True,

    }

    (model_dir / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    METRICS_ARTIFACT.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    return metrics


