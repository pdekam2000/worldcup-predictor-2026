"""PHASE — Paid provider feature utilization audit and shadow fusion."""

from __future__ import annotations

from pathlib import Path

PHASE = "PROVIDER-FEATURE-FUSION-SHADOW"
ARTIFACTS_DIR = Path("artifacts/provider_feature_fusion")
SHADOW_OUTPUT_DIR = ARTIFACTS_DIR / "shadow_outputs"
DATASET_PATH = ARTIFACTS_DIR / "shadow_dataset.parquet"
DATA_DICTIONARY_PATH = ARTIFACTS_DIR / "data_dictionary.json"
COVERAGE_PATH = ARTIFACTS_DIR / "coverage_audit.json"
EXPERIMENTS_PATH = ARTIFACTS_DIR / "fusion_experiments.json"
ABLATION_PATH = ARTIFACTS_DIR / "ablation_report.json"
IMPORTANCE_PATH = ARTIFACTS_DIR / "feature_importance.json"
VALIDATION_PATH = ARTIFACTS_DIR / "validation_report.json"

FEATURE_VERSION = "provider_fusion_v1"
MODEL_VERSION = "shadow_fusion_lr_v1"

# Chronological split ratios (train / val / holdout)
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
HOLDOUT_RATIO = 0.15

MIN_HOLDOUT_ROWS = 500
MIN_FEATURE_COVERAGE = 0.05

EXPERIMENT_VARIANTS = (
    "A_baseline_production_odds",
    "B_baseline_plus_odds_features",
    "C_baseline_plus_xg_diagnostic",
    "D_baseline_plus_form_proxy",
    "E_baseline_plus_lineup_injury_proxy",
    "F_baseline_plus_pressure_proxy",
    "G_baseline_plus_odds_and_xg_diagnostic",
    "H_full_safe_fusion",
)
