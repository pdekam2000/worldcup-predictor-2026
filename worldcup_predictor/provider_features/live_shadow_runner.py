"""30-day live shadow runner preparation — design implementation, no timer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIVE_SHADOW_DIR = Path("data/shadow/provider_feature_fusion_live")
FEATURE_VERSION = "prematch_v1"
MODEL_VERSION = "shadow_fusion_lr_v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def prepare_live_shadow_runner() -> dict[str, Any]:
    """Create directory structure and manifest — does not schedule or predict."""
    LIVE_SHADOW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "phase": "PREMATCH-LIVE-SHADOW-PREP",
        "prepared_at_utc": _utc_now(),
        "production_visible": False,
        "timer_enabled": False,
        "feature_version": FEATURE_VERSION,
        "model_version": MODEL_VERSION,
        "workflow": [
            "collect_prematch_snapshots_from_store",
            "freeze_snapshot_before_prediction",
            "record_prediction_cutoff",
            "run_baseline_odds_fusion_shadow_only",
            "run_extended_fusion_if_coverage_allows",
            "write_jsonl_to_data_shadow_provider_feature_fusion_live",
        ],
        "required_fields": [
            "fixture_id",
            "prediction_scope",
            "baseline_probabilities",
            "fusion_probabilities",
            "features_used",
            "missing_features",
            "snapshot_timestamp",
            "cutoff_timestamp",
            "model_version",
            "feature_version",
            "generated_at",
            "evaluation_status",
            "production_visible",
        ],
        "schedule_design_only": {
            "T-24h": "initial_snapshot",
            "T-6h": "update_snapshot",
            "T-1h": "update_snapshot",
            "T-30m": "final_freeze",
            "post_kickoff": "no_prematch_update",
        },
        "note": "Timer not installed — separate approval required",
    }
    path = LIVE_SHADOW_DIR / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
