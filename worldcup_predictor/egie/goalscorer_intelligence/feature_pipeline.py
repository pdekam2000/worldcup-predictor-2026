"""Feature pipeline for goalscorer intelligence shadow layer."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from worldcup_predictor.egie.goalscorer_ml_shadow.features import load_dataset, prepare_features, split_data
from worldcup_predictor.egie.goalscorer_ml_shadow.trainer import predict_logistic, train_logistic

BRIDGE_DATASET_V2 = Path("artifacts/phase54o_goalscorer_bridge/goalscorer_dataset_v2.parquet")
BRIDGE_FIXTURES = Path("artifacts/phase54o_goalscorer_bridge/fixture_bridge.json")


def _norm_series(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").fillna(0.0)
    mx = float(s.max()) if len(s) else 0.0
    if mx <= 0:
        return s * 0.0
    return (s / mx).clip(0.0, 1.0)


def load_bridge_dataset(path: Path | None = None) -> pd.DataFrame:
    p = Path(path or BRIDGE_DATASET_V2)
    if not p.is_file():
        raise FileNotFoundError(f"Dataset v2 not found: {p}")
    return pd.read_parquet(p)


def attach_ml_scores(df: pd.DataFrame, *, full_dataset_path: Path | None = None) -> pd.DataFrame:
    """Train logistic on full 54K train split; score bridged rows."""
    full = load_dataset(full_dataset_path)
    train, _, _ = split_data(full)
    train_f = prepare_features(train)
    model, scaler = train_logistic(train_f, "target_anytime")

    scored = prepare_features(df)
    out = df.copy()
    out["ml_score"] = predict_logistic(model, scaler, scored)
    return out


def enrich_intelligence_features(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize signals and compute composite inputs per fixture group."""
    out = df.copy()
    out["odds_implied_anytime"] = pd.to_numeric(out.get("implied_probability_anytime"), errors="coerce")
    out["odds_implied_first"] = pd.to_numeric(out.get("implied_probability_first"), errors="coerce")
    out["starter_probability"] = pd.to_numeric(out.get("starter_probability"), errors="coerce").fillna(0.0)
    out["recent_form_score"] = pd.to_numeric(out.get("recent_form_score"), errors="coerce").fillna(0.0)
    out["xg_per_90"] = pd.to_numeric(out.get("xg_per_90"), errors="coerce").fillna(0.0)
    out["shots_on_target_last_5"] = pd.to_numeric(out.get("shots_on_target_last_5"), errors="coerce").fillna(0).astype(int)
    out["lineup_status"] = out.get("lineup_status", pd.Series(["unknown"] * len(out))).fillna("unknown").astype(str)
    out["ml_score"] = pd.to_numeric(out.get("ml_score"), errors="coerce").fillna(0.0)

    norm_cols: dict[str, pd.Series] = {}
    for fid, grp in out.groupby("sportmonks_fixture_id"):
        idx = grp.index
        norm_cols.setdefault("ml_norm", pd.Series(0.0, index=out.index))
        norm_cols.setdefault("odds_norm", pd.Series(0.0, index=out.index))
        norm_cols.setdefault("form_norm", pd.Series(0.0, index=out.index))
        norm_cols.setdefault("xg_norm", pd.Series(0.0, index=out.index))
        norm_cols.setdefault("sot_norm", pd.Series(0.0, index=out.index))
        norm_cols["ml_norm"].loc[idx] = _norm_series(grp["ml_score"])
        norm_cols["odds_norm"].loc[idx] = _norm_series(grp["odds_implied_anytime"].fillna(0))
        norm_cols["form_norm"].loc[idx] = _norm_series(grp["recent_form_score"])
        norm_cols["xg_norm"].loc[idx] = _norm_series(grp["xg_per_90"])
        norm_cols["sot_norm"].loc[idx] = _norm_series(grp["shots_on_target_last_5"])

    for k, v in norm_cols.items():
        out[k] = v

    w = {
        "ml_score": 0.35,
        "odds_implied": 0.25,
        "starter_probability": 0.15,
        "recent_form": 0.10,
        "xg_per_90": 0.08,
        "shots_on_target": 0.07,
    }
    out["composite_scorer_score"] = (
        w["ml_score"] * out["ml_norm"]
        + w["odds_implied"] * out["odds_norm"]
        + w["starter_probability"] * out["starter_probability"].clip(0, 1)
        + w["recent_form"] * out["form_norm"]
        + w["xg_per_90"] * out["xg_norm"]
        + w["shots_on_target"] * out["sot_norm"]
    ).round(6)

    first_odds_norm = out.groupby("sportmonks_fixture_id")["odds_implied_first"].transform(
        lambda s: _norm_series(s.fillna(0))
    )
    out["composite_first_goal_score"] = (
        0.40 * out["ml_norm"] + 0.35 * first_odds_norm + 0.25 * out["starter_probability"].clip(0, 1)
    ).round(6)

    return out
