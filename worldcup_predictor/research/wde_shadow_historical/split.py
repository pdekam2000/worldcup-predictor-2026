"""Part A — Time-based train/val/test split for WDE shadow dataset."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from worldcup_predictor.research.wde_shadow_historical.constants import (
    DATASET_PATH,
    PHASE,
    SPLIT_ARTIFACT,
    TEST_PARQUET,
    TRAIN_PARQUET,
    VAL_PARQUET,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def load_dataset() -> pd.DataFrame:
    if DATASET_PATH.exists():
        return pd.read_parquet(DATASET_PATH)
    csv_path = DATASET_PATH.with_suffix(".csv")
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return pd.DataFrame()


def load_split_dataframes() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if TRAIN_PARQUET.exists() and VAL_PARQUET.exists() and TEST_PARQUET.exists():
        return (
            pd.read_parquet(TRAIN_PARQUET),
            pd.read_parquet(VAL_PARQUET),
            pd.read_parquet(TEST_PARQUET),
        )
    split = json.loads(SPLIT_ARTIFACT.read_text(encoding="utf-8")) if SPLIT_ARTIFACT.exists() else {}
    df = load_dataset()
    if df.empty:
        return df, df, df
    return (
        df.loc[split.get("train_indices", [])].copy(),
        df.loc[split.get("val_indices", [])].copy(),
        df.loc[split.get("test_indices", [])].copy(),
    )


def _split_meta(sub: pd.DataFrame) -> dict[str, Any]:
    if sub.empty:
        return {"count": 0}
    by_league = sub.groupby("league").size().sort_values(ascending=False).head(15).to_dict()
    by_country = sub.groupby("country").size().sort_values(ascending=False).head(15).to_dict()
    season_col = "season_year" if "season_year" in sub.columns else None
    by_season = sub.groupby(season_col).size().to_dict() if season_col else {}
    return {
        "count": len(sub),
        "date_min": str(sub["date"].min()),
        "date_max": str(sub["date"].max()),
        "xg_rate": round(float(sub["expectedGoalsHome"].notna().mean()), 4) if "expectedGoalsHome" in sub.columns else 0.0,
        "by_league": {str(k): int(v) for k, v in by_league.items()},
        "by_country": {str(k): int(v) for k, v in by_country.items()},
        "by_season": {str(k): int(v) for k, v in by_season.items()},
        "label_1x2_dist": sub["label_1x2"].value_counts().to_dict() if "label_1x2" in sub.columns else {},
    }


def _verify_split(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date().isoformat()
    all_hashes = pd.concat([train_df, val_df, test_df])["row_hash"].tolist() if not train_df.empty else []
    train_dates = set(train_df["date"].astype(str)) if not train_df.empty else set()
    val_dates = set(val_df["date"].astype(str)) if not val_df.empty else set()
    test_dates = set(test_df["date"].astype(str)) if not test_df.empty else set()
    valid_labels = {"home_win", "draw", "away_win"}
    label_ok = True
    if not train_df.empty:
        label_ok = set(train_df["label_1x2"].dropna().unique()) <= valid_labels

    return {
        "no_date_overlap_between_splits": len(train_dates & test_dates) == 0 and len(val_dates & test_dates) == 0,
        "strict_time_order": bool(
            not train_df.empty
            and not val_df.empty
            and not test_df.empty
            and train_df["date"].max() <= val_df["date"].min()
            and val_df["date"].max() <= test_df["date"].min()
        ),
        "no_duplicate_row_hash": len(all_hashes) == len(set(all_hashes)),
        "duplicate_row_hash_count": len(all_hashes) - len(set(all_hashes)),
        "no_future_rows": int((pd.concat([train_df, val_df, test_df])["date"].astype(str) > today).sum()) == 0
        if not train_df.empty
        else True,
        "labels_valid": label_ok,
    }


def split_time_based(
    df: pd.DataFrame,
    *,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> dict[str, Any]:
    if df.empty:
        split = {
            "phase": PHASE,
            "error": "empty_dataset",
            "total_rows": 0,
            "train": {"count": 0},
            "validation": {"count": 0},
            "test": {"count": 0},
            "verification": {},
            "leakage_check": {"strict_time_order": True},
        }
        SPLIT_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
        SPLIT_ARTIFACT.write_text(json.dumps(split, indent=2, ensure_ascii=False), encoding="utf-8")
        return split

    ordered = df.sort_values("date").reset_index(drop=True)
    n = len(ordered)
    train_end = int(n * train_frac)
    val_end = train_end + int(n * val_frac)
    train_idx = ordered.index[:train_end].tolist()
    val_idx = ordered.index[train_end:val_end].tolist()
    test_idx = ordered.index[val_end:].tolist()

    train_df = ordered.loc[train_idx].copy()
    val_df = ordered.loc[val_idx].copy()
    test_df = ordered.loc[test_idx].copy()

    TRAIN_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    train_df.to_parquet(TRAIN_PARQUET, index=False)
    val_df.to_parquet(VAL_PARQUET, index=False)
    test_df.to_parquet(TEST_PARQUET, index=False)

    verification = _verify_split(train_df, val_df, test_df)
    split = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "total_rows": n,
        "train_frac": train_frac,
        "val_frac": val_frac,
        "test_frac": round(1.0 - train_frac - val_frac, 4),
        "train_indices": train_idx,
        "val_indices": val_idx,
        "test_indices": test_idx,
        "train_parquet": str(TRAIN_PARQUET),
        "val_parquet": str(VAL_PARQUET),
        "test_parquet": str(TEST_PARQUET),
        "train": _split_meta(train_df),
        "validation": _split_meta(val_df),
        "test": _split_meta(test_df),
        "verification": verification,
        "leakage_check": {
            "train_max_date": str(train_df["date"].max()) if len(train_df) else None,
            "val_min_date": str(val_df["date"].min()) if len(val_df) else None,
            "val_max_date": str(val_df["date"].max()) if len(val_df) else None,
            "test_min_date": str(test_df["date"].min()) if len(test_df) else None,
            "strict_time_order": verification.get("strict_time_order"),
        },
    }
    SPLIT_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_ARTIFACT.write_text(json.dumps(split, indent=2, ensure_ascii=False), encoding="utf-8")
    return split
