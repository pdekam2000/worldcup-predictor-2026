"""PHASE WDE-RETRAIN-SHADOW-2 — WDE shadow historical CSV training constants."""

from __future__ import annotations

from pathlib import Path

PHASE = "WDE-RETRAIN-SHADOW-2"
MIN_SHADOW_TRAINING_ROWS = 5_000
MIN_TEST_ROWS = 500
CHUNK_SIZE = 5_000

READINESS_ARTIFACT = Path("artifacts/historical_csv_training_readiness.json")
READINESS_REPORT = Path("HISTORICAL_CSV_TRAINING_READINESS_REPORT.md")
DATASET_PATH = Path("data/research/wde_shadow_training_dataset.parquet")
DATASET_SUMMARY = Path("artifacts/wde_shadow_training_dataset_summary.json")
TRAIN_PARQUET = Path("data/research/wde_shadow_train.parquet")
VAL_PARQUET = Path("data/research/wde_shadow_val.parquet")
TEST_PARQUET = Path("data/research/wde_shadow_test.parquet")
SPLIT_ARTIFACT = Path("artifacts/wde_shadow_train_val_test_split.json")
METRICS_ARTIFACT = Path("artifacts/wde_shadow_training_metrics.json")
BACKTEST_ARTIFACT = Path("artifacts/wde_shadow_vs_current_backtest.json")
VALIDATION_ARTIFACT = Path("artifacts/wde_shadow_training_validation.json")
FINAL_REPORT = Path("WDE_SHADOW_RETRAIN_HISTORICAL_CSV_REPORT.md")
PREP_REPORT = Path("WDE_SHADOW_RETRAIN_PREP_REPORT.md")
TRAINING_BACKTEST_REPORT = Path("WDE_SHADOW_TRAINING_BACKTEST_REPORT.md")

CROSSWALK_PATH = Path("artifacts/external_historical_fixture_crosswalk.json")
SHADOW_MODELS_DIR = Path("models/shadow")

PLAYED_STATUS_TOKENS = frozenset(
    {
        "finished",
        "ft",
        "aet",
        "pen",
        "complete",
        "completed",
        "ended",
        "full time",
        "fulltime",
    }
)

UNPLAYED_STATUS_TOKENS = frozenset(
    {
        "",
        "ns",
        "not started",
        "scheduled",
        "timed",
        "postponed",
        "cancelled",
        "canceled",
        "abandoned",
        "suspended",
        "tbd",
        "unknown",
    }
)

FT_ODDS_COLUMNS = (
    "oddsFT_1",
    "oddsFT_X",
    "oddsFT_2",
    "oddsFT_Over_2_5",
    "oddsFT_Under_2_5",
    "oddsFT_BTTS_Yes",
    "oddsFT_BTTS_No",
)

TARGETS = {
    "1x2": "label_1x2",
    "ou25": "label_over_2_5",
    "btts": "label_btts",
}
