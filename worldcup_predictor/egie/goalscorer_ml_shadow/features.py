"""Feature preparation for goalscorer ML shadow."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from worldcup_predictor.egie.goalscorer_ml_shadow.models import ML_FEATURE_COLUMNS

DEFAULT_DATASET = Path("artifacts/phase54k_goalscorer_shadow/goalscorer_dataset.parquet")


def load_dataset(path: Path | str | None = None) -> pd.DataFrame:
    p = Path(path or DEFAULT_DATASET)
    if not p.is_file():
        raise FileNotFoundError(f"Goalscorer dataset not found: {p}")
    return pd.read_parquet(p)


def prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    status = out.get("lineup_status", pd.Series(["unknown"] * len(out)))
    out["lineup_status_starter"] = (status == "starter").astype(int)
    out["lineup_status_bench"] = (status == "bench").astype(int)
    out["captain"] = out["captain"].fillna(False).astype(int)
    out["expected_minutes"] = out.get("expected_minutes", out["starter_probability"] * 90).fillna(0.0)
    for col in ML_FEATURE_COLUMNS:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def split_data(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if "split" not in df.columns:
        raise ValueError("Dataset missing temporal split column")
    train = df[df["split"] == "train"].copy()
    val = df[df["split"] == "val"].copy()
    test = df[df["split"] == "test"].copy()
    return train, val, test
