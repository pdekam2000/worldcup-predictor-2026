"""Register TSBP-1 and mark GBGM-1 paused (in-process + artifact)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from worldcup_predictor.challenger.registry import get_model, list_models, register_model
from worldcup_predictor.challenger.tsbp.constants import (
    BIVARIATE_CORR,
    DOMAIN_POLICY_VERSION,
    GBGM1_MODEL_ID,
    GBGM1_STATUS,
    MAX_GOALS_GRID,
    TSBP_DISTRIBUTION,
    TSBP_FINAL_DECISION_AUTHORITY,
    TSBP_IS_SHADOW,
    TSBP_MODEL_FAMILY,
    TSBP_MODEL_ID,
    TSBP_MODEL_NAME,
    TSBP_MODEL_VERSION,
    TSBP_PUBLIC_VISIBLE,
    TSBP_STATUS,
)
from worldcup_predictor.challenger.tsbp.domain_policy import default_domain_policy, save_domain_policy

ROOT = Path(__file__).resolve().parents[3]
REG_ARTIFACT = ROOT / "artifacts" / "challenger_program" / "phase4b" / "tsbp_model_registry.json"


def _git_sha() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        return None


def register_tsbp_and_pause_gbgm(*, phase3b_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    save_domain_policy(default_domain_policy())
    phase3b_summary = phase3b_summary or {}
    selection = phase3b_summary.get("selection") or {}
    hold = selection.get("holdout_metrics") or {}

    tsbp_meta = {
        "model_id": TSBP_MODEL_ID,
        "model_name": TSBP_MODEL_NAME,
        "model_family": TSBP_MODEL_FAMILY,
        "model_version": TSBP_MODEL_VERSION,
        "distribution": TSBP_DISTRIBUTION,
        "status": TSBP_STATUS,
        "is_shadow": TSBP_IS_SHADOW,
        "public_visible": TSBP_PUBLIC_VISIBLE,
        "final_decision_authority": TSBP_FINAL_DECISION_AUTHORITY,
        "experiment_id": "H",
        "attack_strength_method": "mean_goals_scored / league_mean_goals",
        "defence_strength_method": "mean_goals_conceded / league_mean_goals",
        "home_advantage_method": "league_avg_home_goals - league_avg_away_goals (embedded in λ)",
        "time_decay_policy": "none_equal_weight_expanding",
        "league_normalization_policy": "per_competition",
        "competition_features": "competition_key only (no market features)",
        "parameter_estimation_method": "closed_form_relative_rates_FT_only",
        "draw_dependence_parameter": BIVARIATE_CORR,
        "score_grid_truncation": MAX_GOALS_GRID,
        "calibration_method": "none_in_v1_forward",
        "domain_policy_version": DOMAIN_POLICY_VERSION,
        "training_dataset_hash": "phase3b_expanding_train_via_strength_fit",
        "validation_dataset_hash": "phase3b_validation_split",
        "holdout_dataset_hash": "phase3b_holdout_split",
        "holdout_logloss_1x2": hold.get("logloss_1x2") or selection.get("holdout_metrics", {}).get("logloss_1x2"),
        "code_commit_sha": _git_sha(),
        "model_artifact_hash": None,
        "phase3b_chosen": selection.get("chosen_by_validation"),
        "not_gbgm": True,
    }
    raw = json.dumps({k: tsbp_meta[k] for k in sorted(tsbp_meta) if k != "model_artifact_hash"}, sort_keys=True)
    tsbp_meta["model_artifact_hash"] = hashlib.sha256(raw.encode()).hexdigest()
    register_model(TSBP_MODEL_ID, tsbp_meta)

    gbgm_meta = {
        "model_id": GBGM1_MODEL_ID,
        "model_version": "GBGM-1.0.0",
        "status": GBGM1_STATUS,
        "pause_gbgm1_new_generation": True,
        "preserve_history": True,
        "is_shadow": True,
        "public_visible": False,
        "final_decision_authority": False,
        "note": "Paused below league baseline; historical freezes/evals immutable; identity not overwritten by TSBP",
    }
    register_model(GBGM1_MODEL_ID, gbgm_meta)

    REG_ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tsbp": tsbp_meta, "gbgm1": gbgm_meta, "models": list_models()}
    REG_ARTIFACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Keep Phase 3B forward policy aligned
    pol_path = ROOT / "artifacts" / "challenger_program" / "phase3b" / "forward_policy.json"
    pol_path.parent.mkdir(parents=True, exist_ok=True)
    pol = {
        "forward_active": True,
        "reason": "TSBP_PHASE4B_ACTIVE",
        "activate_candidate": "H",
        "active_model_id": TSBP_MODEL_ID,
        "preserve_gbgm1_history": True,
        "pause_gbgm1_new_generation": True,
        "status": "GBGM_IMPROVED_CHALLENGER_READY",
        "is_shadow": True,
        "public_visible": False,
        "final_decision_authority": False,
    }
    pol_path.write_text(json.dumps(pol, indent=2), encoding="utf-8")
    return payload


def load_registered_tsbp() -> dict[str, Any] | None:
    if REG_ARTIFACT.exists():
        return json.loads(REG_ARTIFACT.read_text(encoding="utf-8")).get("tsbp")
    return get_model(TSBP_MODEL_ID)
