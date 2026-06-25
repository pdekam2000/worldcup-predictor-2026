"""Phase 58D — Root Cause Analyzer configuration."""

from __future__ import annotations

from pathlib import Path

PHASE = "58D"
MODEL_VERSION = "root_cause_analyzer_v1.0.58d"

ROOT = Path(__file__).resolve().parents[2]
STORE_DIR = ROOT / "data" / "shadow" / "root_cause_store"
ARTIFACT_DIR = ROOT / "artifacts" / "phase58d_root_cause_analyzer"
REPORT_PATH = ROOT / "PHASE_58D_ROOT_CAUSE_ANALYZER_REPORT.md"

EVALUATIONS_PATH = ROOT / "data" / "shadow" / "elite_orchestrator_evaluations.jsonl"
EXPANDED_PATH = ROOT / "artifacts" / "phase54f6_expanded_dataset" / "expanded_egie_dataset.parquet"
GOALSCORER_PATH = ROOT / "artifacts" / "phase54q_goalscorer_generalization" / "goalscorer_dataset_v3.parquet"

FAILURE_CATEGORIES: tuple[str, ...] = (
    "lineup_mismatch",
    "late_injury",
    "odds_disagreement",
    "low_data_quality",
    "historical_prior_conflict",
    "goalscorer_disagreement",
    "confidence_overestimation",
    "missing_information",
    "unknown",
)

BLAME_LABELS: tuple[str, ...] = ("helped", "hurt", "neutral", "uncertain")

PATTERN_IDS: tuple[str, ...] = (
    "tier_a_failures",
    "tier_b_failures",
    "away_underdogs",
    "low_lineup_confidence",
    "odds_disagreement_gt_15pct",
    "missing_xg",
    "missing_lineup",
    "component_conflict",
    "high_confidence_miss",
)
