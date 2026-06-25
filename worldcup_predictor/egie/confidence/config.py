"""Phase 52D — Hybrid confidence engine configuration (shadow mode only)."""

from __future__ import annotations

from pathlib import Path

HYBRID_CONFIDENCE_MODEL_VERSION = "egie_hybrid_confidence_v0.1_phase52d_shadow"

TEAM_ABSTAIN_GAP = 0.04
RELIABILITY_SHRINKAGE_KAPPA = 12.0

# Tier labels (public UI — no raw percentages)
TIER_LABELS: tuple[str, ...] = ("A", "B", "C", "D")
TIER_DISPLAY_NAMES: dict[str, str] = {
    "A": "Tier A",
    "B": "Tier B",
    "C": "Tier C",
    "D": "Tier D",
}

# Hold-out validation
HOLDOUT_TRAIN_RATIO = 0.80
MIN_TIER_SAMPLES = 8
MONOTONICITY_STRICT = True

# Success gates (shadow promotion)
SUCCESS_CRITERIA = {
    "monotonic_tiers_required": True,
    "ece_team_max": 0.25,
    "ece_range_max": 0.30,
    "min_tier_separation_pp": 0.03,
}

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data" / "egie" / "confidence"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

HYBRID_SHADOW_PREDICTIONS_PATH = DATA_DIR / "hybrid_shadow_predictions.jsonl"
TIER_CALIBRATION_PATH = DATA_DIR / "tier_calibration.json"
VALIDATION_ARTIFACT_PATH = ARTIFACTS_DIR / "phase52d_confidence_validation.json"
