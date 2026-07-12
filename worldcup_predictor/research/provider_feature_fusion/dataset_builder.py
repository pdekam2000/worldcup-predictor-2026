"""Build shadow fusion dataset from stored data only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from worldcup_predictor.research.provider_feature_fusion.constants import (
    DATA_DICTIONARY_PATH,
    DATASET_PATH,
    FEATURE_VERSION,
    HOLDOUT_RATIO,
    PHASE,
    TRAIN_RATIO,
    VAL_RATIO,
)
from worldcup_predictor.research.wde_shadow_historical.constants import (
    DATASET_PATH as WDE_SHADOW_DATASET,
    TEST_PARQUET,
    TRAIN_PARQUET,
    VAL_PARQUET,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entropy(probs: np.ndarray) -> float:
    p = np.clip(probs, 1e-9, 1.0)
    return float(-np.sum(p * np.log(p)))


def _build_feature_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # Odds family (SAFE pre-match FT odds from stored CSV)
    for col in (
        "implied_prob_home",
        "implied_prob_draw",
        "implied_prob_away",
        "implied_prob_over_2_5",
        "implied_prob_under_2_5",
        "implied_prob_btts_yes",
        "implied_prob_btts_no",
    ):
        if col not in out.columns:
            out[col] = np.nan

    out["odds_home"] = out.get("oddsFT_1", np.nan)
    out["odds_draw"] = out.get("oddsFT_X", np.nan)
    out["odds_away"] = out.get("oddsFT_2", np.nan)
    out["bookmaker_count"] = 1.0  # single-source CSV odds; disagreement proxy via entropy

    implied_1x2 = out[["implied_prob_home", "implied_prob_draw", "implied_prob_away"]].to_numpy(dtype=float)
    out["market_entropy"] = [
        _entropy(row) if np.all(np.isfinite(row)) else np.nan for row in implied_1x2
    ]
    out["odds_favorite_strength"] = out[["implied_prob_home", "implied_prob_away"]].max(axis=1)

    # Form proxy from goal difference momentum (SAFE — uses only pre-match odds shape, not results)
    out["form_proxy_home"] = out["implied_prob_home"] - out["implied_prob_away"]
    out["form_proxy_away"] = out["implied_prob_away"] - out["implied_prob_home"]

    # xG diagnostic (POST_MATCH — flagged, not for primary fusion)
    out["home_xg_diagnostic"] = out.get("expectedGoalsHome", np.nan)
    out["away_xg_diagnostic"] = out.get("expectedGoalsAway", np.nan)
    out["has_xg_diagnostic"] = out["home_xg_diagnostic"].notna().astype(int)

    # Lineup/injury/pressure proxies unavailable in CSV — explicit missing
    out["lineup_strength_proxy"] = np.nan
    out["injury_impact_proxy"] = np.nan
    out["pressure_proxy"] = np.nan

    # Missingness mask
    out["mask_odds"] = out["implied_prob_home"].notna().astype(int)
    out["mask_xg_diagnostic"] = out["has_xg_diagnostic"]
    out["mask_form"] = out["mask_odds"]  # form proxy derived from odds
    out["mask_lineup"] = 0
    out["mask_pressure"] = 0

    out["feature_version"] = FEATURE_VERSION
    out["prediction_cutoff_utc"] = out.get("kickoff", out.get("date"))
    out["data_quality"] = out.get("data_quality_flags", "").fillna("")
    return out


def _chronological_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    work = df.sort_values("date").reset_index(drop=True)
    n = len(work)
    t_end = int(n * TRAIN_RATIO)
    v_end = int(n * (TRAIN_RATIO + VAL_RATIO))
    return work.iloc[:t_end], work.iloc[t_end:v_end], work.iloc[v_end:]


def build_shadow_dataset(*, force: bool = False) -> dict[str, Any]:
    if DATASET_PATH.exists() and not force:
        meta = json.loads((DATASET_PATH.parent / "dataset_meta.json").read_text(encoding="utf-8"))
        return meta

    source = WDE_SHADOW_DATASET
    if not source.exists():
        return {"phase": PHASE, "skipped_reason": "wde_shadow_dataset_missing", "row_count": 0}

    df = pd.read_parquet(source)
    df = _build_feature_columns(df)
    df = df[df["label_1x2"].notna()].copy()

    train_df, val_df, holdout_df = _chronological_split(df)
    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(DATASET_PATH, index=False)

    # Also refresh split parquets for experiment reuse
    train_df.to_parquet(TRAIN_PARQUET, index=False)
    val_df.to_parquet(VAL_PARQUET, index=False)
    holdout_df.to_parquet(TEST_PARQUET, index=False)

    dictionary = {
        "fixture_id": "source_match_id (hash) — canonical staging identity",
        "prediction_cutoff_utc": "kickoff date from stored CSV (pre-match odds row)",
        "kickoff_utc": "same as date/kickoff in staging",
        "feature_version": FEATURE_VERSION,
        "odds_home/draw/away": "Pre-match FT odds from stored historical CSV",
        "implied_prob_*": "Normalized implied probabilities from stored odds",
        "home_xg_diagnostic": "POST_MATCH realized xG — diagnostic only, leakage flagged",
        "label_1x2": "FT result label: home_win/draw/away_win",
        "label_over_2_5": "O/U 2.5 label",
        "label_btts": "BTTS label",
        "mask_*": "Explicit missingness indicators (1=present)",
    }
    DATA_DICTIONARY_PATH.write_text(json.dumps(dictionary, indent=2), encoding="utf-8")

    meta = {
        "phase": PHASE,
        "built_at_utc": _utc_now(),
        "source": str(source),
        "row_count": len(df),
        "train_rows": len(train_df),
        "val_rows": len(val_df),
        "holdout_rows": len(holdout_df),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
        "feature_version": FEATURE_VERSION,
        "provider_calls_made": 0,
        "leakage_note": "CSV xG columns classified POST_MATCH_ONLY — excluded from H_full_safe_fusion",
    }
    (DATASET_PATH.parent / "dataset_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta
