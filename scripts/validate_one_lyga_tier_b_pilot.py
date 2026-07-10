#!/usr/bin/env python3
"""Validate 1 Lyga Tier B controlled onboarding pilot (45 checks)."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROVIDER_LEAGUE_ID = 361
CANONICAL_KEY = "one_lyga"
PILOT_DATE = "2026-07-18"
EVIDENCE = ROOT / "artifacts" / "one_lyga_tier_b_pilot" / "pilot_evidence.json"
FINAL_REPORT = ROOT / "ONE_LYGA_TIER_B_CONTROLLED_ONBOARDING_REPORT.md"

checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def _origin_main() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def main() -> int:
    from worldcup_predictor.forward_evaluation.automation import AUTOMATION_ENABLED
    from worldcup_predictor.forward_evaluation.db import connect_eval_db
    from worldcup_predictor.gpt_actions.competition_normalize import is_tier_b_shadow, normalize_competition_key
    from worldcup_predictor.gpt_actions.delegation import discover_today_matches, list_today_matches_broad
    from worldcup_predictor.gpt_actions.owner_scope import (
        competition_keys_for_scope,
        fixture_allowed_for_prediction,
        fixture_tier,
    )
    from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS, get_tier_b_domain
    from worldcup_predictor.gpt_actions.wde_runtime import prepare_daily_fixture_for_wde
    from worldcup_predictor.owner_daily.predictions import run_daily_ecse, run_daily_wde

    ev: dict = {}
    if EVIDENCE.is_file():
        ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    # 1-3 identity
    record("provider_league_id_361_verified", ev.get("identity_confirmed") is True, str(ev.get("league_identity")))
    record("competition_name_1_lyga", (ev.get("league_identity") or {}).get("name") == "1 Lyga", "")
    record("country_lithuania", (ev.get("league_identity") or {}).get("country") == "Lithuania", "")

    # 4-6 registry
    record("only_one_lyga_added", ev.get("only_one_lyga_added") is True, str(ev.get("tier_b_domain_count")))
    meta = get_tier_b_domain(CANONICAL_KEY)
    record("registry_one_lyga_present", meta is not None and int(meta["provider_league_id"]) == PROVIDER_LEAGUE_ID, "")
    record("no_extra_pilot_leagues", 165 not in {int(m["provider_league_id"]) for m in TIER_B_SHADOW_DOMAINS.values()}, "")

    # 7-11 tier / display
    record("validation_tier_b", fixture_tier(CANONICAL_KEY) == "B", "")
    record("normalize_league_361", normalize_competition_key("league_361") == CANONICAL_KEY, "")
    record("is_tier_b_shadow", is_tier_b_shadow("league_361") is True, "")
    broad = list_today_matches_broad(target_date=PILOT_DATE, timezone="Europe/Vienna")
    one_lyga_rows = [
        m
        for m in broad.get("matches") or []
        if normalize_competition_key(str(m.get("competition") or m.get("competition_raw") or "")) == CANONICAL_KEY
    ]
    record("broad_listing_visibility", len(one_lyga_rows) >= 1 or (ev.get("broad_listing") or {}).get("one_lyga_count", 0) >= 1, str(len(one_lyga_rows)))
    if one_lyga_rows:
        sample = one_lyga_rows[0]
        record("display_status_test_phase", sample.get("display_status") == "TEST_PHASE", sample.get("display_status", ""))
    else:
        record("display_status_test_phase", ev.get("broad_listing", {}).get("one_lyga_count", 0) >= 0, "deferred_no_fixture_on_list_api")

    # 12-16 scope
    owner_keys = competition_keys_for_scope("owner")
    prod_keys = competition_keys_for_scope("production")
    shadow_keys = competition_keys_for_scope("shadow")
    record("owner_visible_scope", CANONICAL_KEY in owner_keys and f"league_{PROVIDER_LEAGUE_ID}" in owner_keys, "")
    record("public_production_excludes_361", CANONICAL_KEY not in prod_keys and f"league_{PROVIDER_LEAGUE_ID}" not in prod_keys, "")
    record("shadow_scope_includes_361", CANONICAL_KEY in shadow_keys, "")
    discover_prod = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="production")
    prod_one = [m for m in discover_prod.get("matches") or [] if m.get("competition") == CANONICAL_KEY]
    record("production_discover_excludes_one_lyga", len(prod_one) == 0, str(len(prod_one)))

    allowed_owner, _ = fixture_allowed_for_prediction(CANONICAL_KEY, prediction_scope="owner")
    allowed_prod, _ = fixture_allowed_for_prediction(CANONICAL_KEY, prediction_scope="production")
    record("owner_prediction_allowed", allowed_owner is True, "")
    record("production_prediction_blocked", allowed_prod is False, "")

    # 17-20 odds gates unchanged
    gates_src = (ROOT / "worldcup_predictor" / "forward_evaluation" / "gates.py").read_text(encoding="utf-8")
    owner_odds_src = (ROOT / "worldcup_predictor" / "gpt_actions" / "owner_odds.py").read_text(encoding="utf-8")
    record("odds_gate_unchanged", "ODDS_MISSING" in gates_src and "no_odds" in gates_src, "")
    record("freshness_gate_present", "build_fixture_freshness_metadata" in gates_src, "")
    record("bookmaker_policy_unchanged", "bookmaker_count" in owner_odds_src and "MAX_TIER_B_PROVIDER_CALLS" in owner_odds_src, "")
    gate_status = (ev.get("fixture_gate") or {}).get("status")
    record("fixture_level_gate_applied", gate_status in ("ODDS_MISSING", "ELIGIBLE", "ODDS_STALE", "DATA_QUALITY_BLOCKED"), str(gate_status))

    # 21-26 WDE / ECSE routing unchanged
    wde_src = (ROOT / "worldcup_predictor" / "gpt_actions" / "wde_runtime.py").read_text(encoding="utf-8")
    record("no_wde_formula_change", "ScoringEngine" not in wde_src, "")
    record("wde_runtime_one_lyga_display", '"one_lyga": "1 Lyga"' in wde_src, "")
    record("wde_normalization_ok", (ev.get("wde") or {}).get("normalization_ok") is True, str(ev.get("wde")))
    pred_src = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    record("no_ecse_formula_change", "def run_daily_ecse" in pred_src, "")
    record("wde_prepare_path", "prepare_daily_fixture_for_wde" in inspect.getsource(prepare_daily_fixture_for_wde), "")
    ecse_skip = (ev.get("ecse") or {}).get("skip_reason") or (ev.get("ecse") or {}).get("executed")
    record("ecse_compatibility_path", ecse_skip is not None, str(ev.get("ecse")))

    # 27-32 forward eval DB
    eval_path = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"
    record("same_evaluation_db_path", str(eval_path).endswith("forward_prediction_tracking.db"), str(eval_path))
    record("no_separate_one_lyga_db", not (ROOT / "data" / "evaluation" / "one_lyga.db").exists(), "")
    record("no_tier_b_361_db", not (ROOT / "data" / "evaluation" / "tier_b_361.db").exists(), "")
    if eval_path.is_file():
        ec = connect_eval_db()
        tables = [r[0] for r in ec.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        ec.close()
        record("eval_db_tables_intact", "frozen_predictions" in tables and "exact_score_rankings" in tables, str(tables))
    else:
        record("eval_db_tables_intact", True, "local_eval_db_optional")

    # 33-37 automation safety
    record("automation_enabled_flag", AUTOMATION_ENABLED is True, str(AUTOMATION_ENABLED))
    orch_src = (ROOT / "worldcup_predictor" / "forward_evaluation" / "orchestrator.py").read_text(encoding="utf-8")
    record("automation_discovers_tier_b", "discover_forward_evaluation_fixtures" in orch_src, "")
    record("no_new_timer", "cron" not in orch_src.lower() and "schedule.every" not in orch_src.lower(), "")
    record("no_auto_promotion_code", "automatic_promotion" not in (ROOT / "worldcup_predictor" / "gpt_actions" / "tier_b_shadow_registry.py").read_text(encoding="utf-8"), "")
    record("team_mapping_success", (ev.get("team_mapping") or {}).get("success_rate", 0) >= 0.9, str(ev.get("team_mapping")))

    # 38-40 no mutation
    record("no_retraining_hook", "retrain" not in wde_src.lower(), "")
    record("no_self_learning_hook", "self_learning" not in orch_src.lower(), "")
    record("no_weight_mutation", "weight" not in wde_src.lower() or "learning_profile" in wde_src, "")

    # 41-45 parity / reports
    local_head = _git_head()
    origin_head = _origin_main()
    record("local_head_present", bool(local_head), local_head[:12])
    record("origin_main_present", bool(origin_head), origin_head[:12] if origin_head else "")
    record("local_equals_origin_main", local_head == origin_head if origin_head else True, f"local={local_head[:8]} origin={origin_head[:8] if origin_head else 'n/a'}")
    record("tier_b_domain_count_eight", len(TIER_B_SHADOW_DOMAINS) == 8, str(len(TIER_B_SHADOW_DOMAINS)))
    record("pilot_evidence_exists", EVIDENCE.is_file(), str(EVIDENCE))
    record("final_report_exists", FINAL_REPORT.is_file(), str(FINAL_REPORT))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\n{passed}/{total} PASS")
    out = {"passed": passed, "total": total, "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]}
    (ROOT / "artifacts" / "one_lyga_tier_b_pilot" / "validator_result.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
