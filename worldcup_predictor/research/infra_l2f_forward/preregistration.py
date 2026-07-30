"""Immutable preregistration artifacts for L2-F challenger evaluation."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "l2f-preregistration-v1"
DEFAULT_DIR = Path("artifacts/l2f_preregistration")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def build_preregistration_document(*, git_commit: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "git_commit": git_commit or _git_commit(),
        "models": {
            "exact_v2": {
                "model_id": "EXACT_V2_SELECTED",
                "model_version": "EXACT-V2-1",
                "primary_metric": "top5_hit_rate",
                "secondary_metrics": [
                    "top1_hit_rate",
                    "top3_hit_rate",
                    "top10_hit_rate",
                    "log_loss",
                    "actual_score_rank",
                    "entropy",
                    "top5_mass",
                ],
            },
            "lambda_v2": {
                "model_id": "LAMBDA_V2_BLENDED_ADAPTIVE",
                "model_version": "LAMBDA-V2-1",
                "primary_metric": "mae_total_lambda_error",
                "secondary_metrics": [
                    "mae_home",
                    "mae_away",
                    "rmse_home",
                    "rmse_away",
                    "rmse_total",
                    "calibration_by_expected_total_bucket",
                ],
            },
            "detector_et_gte_3_0": {
                "research_only": True,
                "routing_activated": False,
                "threshold_frozen": {"min_expected_total_lambda": 3.0},
                "metrics": ["precision", "recall", "coverage", "challenger_top5_uplift"],
                "no_retuning_on_true_forward_outcomes": True,
            },
        },
        "sample_size_gates": {
            "hard_minimum_true_forward_evaluated": 100,
            "preferred_decision_threshold": 250,
            "min_leagues": 4,
            "max_single_league_share": 0.5,
            "min_calendar_days": 21,
        },
        "statistics": {
            "confidence_interval_method": "wilson_score_interval_95",
            "bootstrap_method": "paired_mean_difference_1000_resamples_percentile_95",
        },
        "exclusion_rules": {
            "postponed": "exclude_from_evaluated_metrics",
            "cancelled": "exclude_from_evaluated_metrics",
            "abandoned": "exclude_from_evaluated_metrics",
            "conflicting_result": "exclude_and_flag_integrity",
            "missing_immutable_freeze": "exclude",
            "postkickoff_prediction": "exclude_from_true_forward",
        },
        "league_inclusion": {
            "owner_scopes": ["production", "owner_shadow", "owner_daily"],
            "require_valid_canonical_completion": True,
        },
        "odds_input_quality": {
            "prefer_freeze_time_odds": True,
            "forbid_current_odds_substitution_for_historical": True,
            "missing_odds_allowed_with_canonical_lambdas": True,
        },
        "promotion_policy": {
            "automatic_promotion": False,
            "requires_explicit_owner_approval": True,
            "allowed_terminal_statuses": [
                "NOT_READY_INSUFFICIENT_TRUE_FORWARD",
                "NOT_READY_INTEGRITY_FAILURE",
                "NOT_READY_OPERATIONAL_FAILURE",
                "NOT_READY_NO_PERFORMANCE_LIFT",
                "READY_FOR_MANUAL_REVIEW",
            ],
            "forbidden_statuses": ["PROMOTED"],
        },
        "amendment_policy": "create_new_version_never_overwrite",
    }


def content_hash(doc: dict[str, Any]) -> str:
    # Hash without volatile fields that are duplicated outside
    material = {k: v for k, v in doc.items() if k not in {"content_hash"}}
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()


def write_preregistration(
    out_dir: Path | None = None,
    *,
    git_commit: str | None = None,
) -> dict[str, Any]:
    out_dir = out_dir or DEFAULT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    # Version by timestamp — never overwrite prior files.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    doc = build_preregistration_document(git_commit=git_commit)
    h = content_hash(doc)
    doc["content_hash"] = h
    path = out_dir / f"preregistration_{SCHEMA_VERSION}_{ts}_{h[:12]}.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    # Pointer file lists latest without mutating prior artifacts
    latest = out_dir / "LATEST.txt"
    latest.write_text(str(path.name) + "\n", encoding="utf-8")
    return {"path": str(path), "content_hash": h, "schema_version": SCHEMA_VERSION, "document": doc}
