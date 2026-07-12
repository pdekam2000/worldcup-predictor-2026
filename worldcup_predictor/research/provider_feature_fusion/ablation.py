"""Ablation study from fusion experiment results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.provider_feature_fusion.constants import ABLATION_PATH, EXPERIMENTS_PATH, PHASE

FEATURE_FAMILIES = (
    ("odds", "B_baseline_plus_odds_features"),
    ("xg", "C_baseline_plus_xg_diagnostic"),
    ("form", "D_baseline_plus_form_proxy"),
    ("lineup_injury", "E_baseline_plus_lineup_injury_proxy"),
    ("pressure", "F_baseline_plus_pressure_proxy"),
    ("odds_xg", "G_baseline_plus_odds_and_xg_diagnostic"),
    ("full_safe", "H_full_safe_fusion"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_ablation_report(experiments: dict[str, Any] | None = None) -> dict[str, Any]:
    data = experiments or json.loads(EXPERIMENTS_PATH.read_text(encoding="utf-8"))
    variants = data.get("variants") or {}
    baseline = (variants.get("A_baseline_production_odds") or {}).get("holdout") or {}
    base_1x2 = (baseline.get("wde_1x2") or {})

    rows: list[dict[str, Any]] = []
    for family, key in FEATURE_FAMILIES:
        v = variants.get(key) or {}
        hold = v.get("holdout") or {}
        m = hold.get("wde_1x2") or {}
        rows.append(
            {
                "feature_family": family,
                "variant": key,
                "sample_size": m.get("n"),
                "coverage": v.get("feature_coverage_train"),
                "baseline_accuracy": base_1x2.get("accuracy"),
                "variant_accuracy": m.get("accuracy"),
                "delta_accuracy": v.get("delta_vs_baseline_1x2_accuracy"),
                "log_loss": m.get("log_loss"),
                "brier_score": m.get("brier_score"),
                "calibration_error": m.get("calibration_error"),
                "ou25_accuracy": (hold.get("ou25") or {}).get("accuracy"),
                "btts_accuracy": (hold.get("btts") or {}).get("accuracy"),
                "ecse_top1": (hold.get("ecse_odds_proxy") or {}).get("top1_hit_rate"),
                "ecse_top5": (hold.get("ecse_odds_proxy") or {}).get("top5_hit_rate"),
                "leakage_flags": v.get("leakage_flags") or [],
                "failure_modes": (
                    ["no_improvement_vs_baseline"]
                    if (v.get("delta_vs_baseline_1x2_accuracy") or 0) <= 0
                    else []
                ),
            }
        )

    report = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "baseline_variant": "A_baseline_production_odds",
        "baseline_holdout_1x2": base_1x2,
        "families": rows,
        "conclusion_note": "Deltas computed on chronological holdout; xG family is diagnostic-only (post-match leakage).",
    }
    ABLATION_PATH.parent.mkdir(parents=True, exist_ok=True)
    ABLATION_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
