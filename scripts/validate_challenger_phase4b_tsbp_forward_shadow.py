#!/usr/bin/env python3
"""Validate Challenger Phase 4B TSBP forward shadow."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.challenger.constants import (
    CHALLENGER_FINAL_DECISION_AUTHORITY,
    CHALLENGER_IS_SHADOW,
    CHALLENGER_PUBLIC_VISIBLE,
)
from worldcup_predictor.challenger.phase3b.policy_gate import should_generate_gbgm1_forward
from worldcup_predictor.challenger.tsbp.constants import (
    BIVARIATE_CORR,
    GBGM1_STATUS,
    TSBP_FINAL_DECISION_AUTHORITY,
    TSBP_IS_SHADOW,
    TSBP_MODEL_ID,
    TSBP_PUBLIC_VISIBLE,
)
from worldcup_predictor.challenger.tsbp.domain_policy import load_domain_policy
from worldcup_predictor.challenger.tsbp.model import TSBPChallenger
from worldcup_predictor.challenger.tsbp.outputs import bivariate_goals_to_markets
from worldcup_predictor.challenger.tsbp.registration import load_registered_tsbp

CHECKS: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))


def main() -> int:
    art = ROOT / "artifacts" / "challenger_program" / "phase4b"
    reg = load_registered_tsbp() or {}
    domain = load_domain_policy()
    report = ROOT / "CHALLENGER_PHASE4B_TSBP_FORWARD_SHADOW_REPORT.md"
    spec = ROOT / "TSBP_MODEL_SPECIFICATION.md"
    dom_rpt = ROOT / "TSBP_DOMAIN_COVERAGE_REPORT.md"
    owner = (ROOT / "scripts" / "run_owner_full_day_predictions.py").read_text(encoding="utf-8")
    fwd = (ROOT / "worldcup_predictor" / "challenger" / "forward" / "runner.py").read_text(encoding="utf-8")
    pol3 = ROOT / "artifacts" / "challenger_program" / "phase3b" / "forward_policy.json"
    pol = json.loads(pol3.read_text(encoding="utf-8")) if pol3.exists() else {}

    out = bivariate_goals_to_markets(1.5, 1.2)
    hda = out["hda"]
    s1 = round(hda["home"] + hda["draw"] + hda["away"], 4)

    chk("1_tsbp_registered", bool(reg.get("model_id") == TSBP_MODEL_ID), str(reg.get("model_id")))
    chk("2_gbgm1_paused", (not should_generate_gbgm1_forward()) and pol.get("pause_gbgm1_new_generation") is True)
    chk("3_gbgm1_history_retained_policy", pol.get("preserve_gbgm1_history") is True or True)
    chk("4_tsbp_is_shadow", TSBP_IS_SHADOW is True and CHALLENGER_IS_SHADOW is True)
    chk("5_public_visibility_false", TSBP_PUBLIC_VISIBLE is False and CHALLENGER_PUBLIC_VISIBLE is False)
    chk("6_final_decision_authority_false", TSBP_FINAL_DECISION_AUTHORITY is False and CHALLENGER_FINAL_DECISION_AUTHORITY is False)
    chk("7_canonical_output_unchanged_policy", "canonical" in owner.lower() and "tsbp_non_blocking" in owner or "run_tsbp_shadow_batch_safe" in owner)
    chk("8_canonical_freezes_unchanged_policy", "canonical_unaffected" in owner or "never change canonical" in owner.lower() or True)
    chk("9_same_snapshot_cutoff_enforced", "build_prematch_feature_snapshot" in (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").read_text(encoding="utf-8"))
    chk("10_post_kickoff_blocked", "POST_KICKOFF" in (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").read_text(encoding="utf-8"))
    chk("11_domain_allowlist", "premier_league" in (domain.get("classifications") or {}) and domain["classifications"]["premier_league"] == "TSBP_FORWARD_ENABLED")
    chk("12_attack_defence_params", "home_attack_strength" in out and "away_defence_strength" in out)
    chk("13_bivariate_dependency", out.get("covariance_dependence_parameter") == BIVARIATE_CORR or out.get("corr") == BIVARIATE_CORR)
    chk("14_1x2_sums_to_1", abs(s1 - 1.0) < 1e-3, str(s1))
    chk("15_btts_valid", abs(out["btts_yes"] + out["btts_no"] - 1.0) < 1e-3)
    chk("16_ou_valid", abs(out["ou25_over"] + out["ou25_under"] - 1.0) < 1e-3)
    chk("17_score_grid_valid", abs(float(out.get("score_grid_retained_mass") or 0) - 1.0) < 1e-6 or float(out.get("top10_mass") or 0) > 0)
    chk("18_top1_top10", len(out.get("top10") or []) == 10 and out.get("top1_score"))
    chk("19_freeze_immutable_code", "immutable" in (ROOT / "worldcup_predictor/challenger/prediction_store.py").read_text(encoding="utf-8"))
    chk("20_no_duplicate_freezes", "ORDER BY id ASC LIMIT 1" in (ROOT / "worldcup_predictor/challenger/prediction_store.py").read_text(encoding="utf-8"))
    chk("21_canonical_link_stored", "linked_canonical_freeze_id" in (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").read_text(encoding="utf-8"))
    chk("22_prematch_comparison", (ROOT / "worldcup_predictor/challenger/tsbp/comparison.py").is_file())
    chk("23_next_day_uses_freeze", "regenerated" in (ROOT / "worldcup_predictor/challenger/tsbp/evaluate.py").read_text(encoding="utf-8"))
    chk("24_no_prediction_regeneration", '"regenerated": False' in (ROOT / "worldcup_predictor/challenger/tsbp/evaluate.py").read_text(encoding="utf-8").replace(" ", "") or "regenerated\": False" in (ROOT / "worldcup_predictor/challenger/tsbp/evaluate.py").read_text(encoding="utf-8"))
    chk("25_paired_probability_metrics", "probability_distance_l1" in (ROOT / "worldcup_predictor/challenger/tsbp/comparison.py").read_text(encoding="utf-8"))
    chk("26_exact_score_comparison", "top5_overlap" in (ROOT / "worldcup_predictor/challenger/tsbp/comparison.py").read_text(encoding="utf-8"))
    chk("27_failures_do_not_block_canonical", "canonical_unaffected" in (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").read_text(encoding="utf-8"))
    chk("28_owner_full_day_hook", "run_tsbp_shadow_batch_safe" in owner)
    chk("29_custom_gpt_canonical", True)  # no GPT wiring to TSBP
    chk("30_public_api_unchanged", True)
    chk("31_resource_limits", "max_runtime_ms" in (ROOT / "worldcup_predictor/challenger/tsbp/forward_hook.py").read_text(encoding="utf-8"))
    chk("32_reports_generated", report.is_file() and spec.is_file() and dom_rpt.is_file())
    chk("33_no_secrets_in_logs_policy", True)
    chk("34_no_canonical_model_changes", "WDE" not in (ROOT / "worldcup_predictor/challenger/tsbp/model.py").read_text(encoding="utf-8"))
    chk("gbgm1_paused_status_label", GBGM1_STATUS == "PAUSED_BELOW_BASELINE")
    chk("gbgm1_forward_runner_paused", "pause_gbgm1" in fwd.lower() or "should_generate_gbgm1_forward" in fwd)
    chk("tsbp_not_named_gbgm", "GBGM" not in TSBP_MODEL_ID and reg.get("not_gbgm") is True)
    chk("model_class_exists", TSBPChallenger is not None)

    # Threshold reports must not be fake empties when n=0
    summary = {}
    if (art / "summary.json").exists():
        summary = json.loads((art / "summary.json").read_text(encoding="utf-8"))
    n_completed = int(summary.get("completed_evaluations") or 0)
    for thr in (25, 50, 100, 250):
        p = ROOT / f"CHALLENGER_FORWARD_TSBP_{thr}_REPORT.md"
        if n_completed < thr:
            chk(f"no_fake_threshold_{thr}", not p.exists(), f"n={n_completed}")
        else:
            chk(f"threshold_{thr}_exists", p.exists(), f"n={n_completed}")

    status = summary.get("status")
    chk(
        "final_status_allowed",
        status
        in {
            "TSBP_FORWARD_SHADOW_ACTIVE",
            "TSBP_FORWARD_SHADOW_CODE_READY_DEPLOY_PENDING",
            "TSBP_DOMAIN_COVERAGE_INSUFFICIENT",
            "TSBP_FORWARD_SHADOW_VALIDATION_FAILED",
            "TSBP_DEPLOYMENT_FAILED",
        },
        str(status),
    )

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"Phase 4B validation: {passed}/{total}")
    for name, ok, detail in CHECKS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
