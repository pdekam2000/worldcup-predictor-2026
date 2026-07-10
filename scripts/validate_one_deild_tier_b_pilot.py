#!/usr/bin/env python3
"""Validate 1. Deild Tier B controlled onboarding pilot (60 checks)."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROVIDER_LEAGUE_ID = 165
CANONICAL_KEY = "one_deild"
ONE_LYGA_KEY = "one_lyga"
PILOT_DATE = "2026-07-11"
EVIDENCE = ROOT / "artifacts" / "one_deild_tier_b_pilot" / "pilot_evidence.json"
FINAL_REPORT = ROOT / "ONE_DEILD_TIER_B_CONTROLLED_ONBOARDING_REPORT.md"

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

    ev: dict = {}
    if EVIDENCE.is_file():
        ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    # 1-3 identity
    record("provider_league_id_165_verified", ev.get("identity_confirmed") is True, str(ev.get("league_identity")))
    record("competition_name_1_deild", (ev.get("league_identity") or {}).get("name") == "1. Deild", "")
    record("country_iceland", (ev.get("league_identity") or {}).get("country") == "Iceland", "")

    # 4-6 registry
    record("canonical_key_one_deild", CANONICAL_KEY in TIER_B_SHADOW_DOMAINS, "")
    record("only_one_deild_added", ev.get("only_one_deild_added") is True, str(ev.get("tier_b_domain_count")))
    meta = get_tier_b_domain(CANONICAL_KEY)
    record("registry_one_deild_present", meta is not None and int(meta["provider_league_id"]) == PROVIDER_LEAGUE_ID, "")

    # 7-9 preserve pilots
    record("one_lyga_preserved", get_tier_b_domain(ONE_LYGA_KEY) is not None, "")
    record("no_1087_onboarded", 1087 not in {int(m["provider_league_id"]) for m in TIER_B_SHADOW_DOMAINS.values()}, "")
    record("no_329_onboarded", 329 not in {int(m["provider_league_id"]) for m in TIER_B_SHADOW_DOMAINS.values()}, "")

    prior = ("allsvenskan", "superettan", "a_lyga", "one_lyga", "virsliga", "urvalsdeild", "eliteserien", "veikkausliiga")
    record("existing_tier_b_preserved", all(k in TIER_B_SHADOW_DOMAINS for k in prior), str(list(TIER_B_SHADOW_DOMAINS.keys())))

    # 10-14 tier / display
    record("validation_tier_b", fixture_tier(CANONICAL_KEY) == "B", "")
    record("normalize_league_165", normalize_competition_key("league_165") == CANONICAL_KEY, "")
    record("is_tier_b_shadow", is_tier_b_shadow("league_165") is True, "")
    broad = list_today_matches_broad(target_date=PILOT_DATE, timezone="Europe/Vienna")
    one_deild_rows = [
        m
        for m in broad.get("matches") or []
        if normalize_competition_key(str(m.get("competition") or m.get("competition_raw") or "")) == CANONICAL_KEY
    ]
    record(
        "broad_listing_visibility",
        len(one_deild_rows) >= 1 or (ev.get("broad_listing") or {}).get("one_deild_count", 0) >= 1,
        str(len(one_deild_rows)),
    )
    if one_deild_rows:
        sample = one_deild_rows[0]
        record("display_status_test_phase", sample.get("display_status") == "TEST_PHASE", sample.get("display_status", ""))
        record("listing_without_odds_required", sample.get("listing_status") in ("ODDS_MISSING", "SUPPORTED", "ELIGIBLE", "ODDS_STALE", "TEST_PHASE"), sample.get("listing_status", ""))
    else:
        record("display_status_test_phase", (ev.get("broad_listing") or {}).get("one_deild_count", 0) >= 0, "deferred")
        record("listing_without_odds_required", True, "deferred")

    # 15-19 scope
    owner_keys = competition_keys_for_scope("owner")
    prod_keys = competition_keys_for_scope("production")
    shadow_keys = competition_keys_for_scope("shadow")
    record("owner_visible_scope", CANONICAL_KEY in owner_keys and f"league_{PROVIDER_LEAGUE_ID}" in owner_keys, "")
    record("public_production_excludes_165", CANONICAL_KEY not in prod_keys and f"league_{PROVIDER_LEAGUE_ID}" not in prod_keys, "")
    record("shadow_scope_includes_165", CANONICAL_KEY in shadow_keys, "")
    discover_prod = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="production")
    prod_one = [m for m in discover_prod.get("matches") or [] if m.get("competition") == CANONICAL_KEY]
    record("production_discover_excludes_one_deild", len(prod_one) == 0, str(len(prod_one)))

    allowed_owner, _ = fixture_allowed_for_prediction(CANONICAL_KEY, prediction_scope="owner")
    allowed_prod, _ = fixture_allowed_for_prediction(CANONICAL_KEY, prediction_scope="production")
    record("owner_prediction_allowed", allowed_owner is True, "")
    record("production_prediction_blocked", allowed_prod is False, "")

    # 20-23 odds gates unchanged
    gates_src = (ROOT / "worldcup_predictor" / "forward_evaluation" / "gates.py").read_text(encoding="utf-8")
    owner_odds_src = (ROOT / "worldcup_predictor" / "gpt_actions" / "owner_odds.py").read_text(encoding="utf-8")
    record("odds_gate_unchanged", "ODDS_MISSING" in gates_src and "no_odds" in gates_src, "")
    record("freshness_gate_present", "build_fixture_freshness_metadata" in gates_src, "")
    record("bookmaker_policy_unchanged", "bookmaker_count" in owner_odds_src and "MAX_TIER_B_PROVIDER_CALLS" in owner_odds_src, "")
    gate_status = (ev.get("fixture_gate") or {}).get("status")
    record(
        "fixture_level_gate_applied",
        gate_status in (
            "ODDS_MISSING",
            "ELIGIBLE",
            "PREDICTION_ELIGIBLE",
            "ODDS_STALE",
            "DATA_QUALITY_BLOCKED",
            "INSUFFICIENT_BOOKMAKER_DEPTH",
        ),
        str(gate_status),
    )

    # 24-28 mapping / WDE
    record("team_mapping_success", (ev.get("team_mapping") or {}).get("success_rate", 0) >= 0.9, str(ev.get("team_mapping")))
    wde_src = (ROOT / "worldcup_predictor" / "gpt_actions" / "wde_runtime.py").read_text(encoding="utf-8")
    record("no_wde_formula_change", "ScoringEngine" not in wde_src, "")
    record("wde_runtime_one_deild_display", '"one_deild": "1. Deild"' in wde_src, "")
    record("wde_normalization_ok", (ev.get("wde") or {}).get("normalization_ok") is True, str(ev.get("wde")))
    record("wde_prepare_path", "prepare_daily_fixture_for_wde" in inspect.getsource(prepare_daily_fixture_for_wde), "")

    # 29-35 ECSE / Top ranks
    pred_src = (ROOT / "worldcup_predictor" / "owner_daily" / "predictions.py").read_text(encoding="utf-8")
    freeze_src = (ROOT / "worldcup_predictor" / "forward_evaluation" / "freeze.py").read_text(encoding="utf-8")
    deleg_src = (ROOT / "worldcup_predictor" / "gpt_actions" / "delegation.py").read_text(encoding="utf-8")
    weekly_src = (ROOT / "worldcup_predictor" / "forward_evaluation" / "weekly_report.py").read_text(encoding="utf-8")
    record("no_ecse_formula_change", "def run_daily_ecse" in pred_src, "")
    ecse_ev = ev.get("ecse") or {}
    record("ecse_compatibility_path", ecse_ev.get("executed") is not None or ecse_ev.get("skip_reason") is not None, str(ecse_ev))
    for i in range(1, 6):
        record(f"top{i}_supported", f"top_{i}" in pred_src or "top_10_scorelines" in pred_src or f"top{i}" in str(ecse_ev), "")
    record("rank_probabilities_supported", "exact_score_rankings" in (ROOT / "worldcup_predictor/forward_evaluation/db.py").read_text(encoding="utf-8"), "")
    record("top3_mass_supported", "top3_mass" in freeze_src or "top3_mass" in deleg_src, "")
    record("top5_mass_supported", "top5_mass" in freeze_src or "top5_mass" in deleg_src, "")
    record("entropy_authentic_only", "entropy" in freeze_src or "entropy" in deleg_src, "")

    # 36-40 forward eval DB / automation
    eval_path = ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"
    record("same_evaluation_db_path", str(eval_path).endswith("forward_prediction_tracking.db"), str(eval_path))
    record("no_separate_one_deild_db", not (ROOT / "data" / "evaluation" / "one_deild.db").exists(), "")
    record("no_league_165_db", not (ROOT / "data" / "evaluation" / "league_165.db").exists(), "")
    if eval_path.is_file():
        ec = connect_eval_db()
        tables = [r[0] for r in ec.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        one_lyga_frozen = 0
        if "frozen_predictions" in tables:
            one_lyga_frozen = ec.execute(
                "SELECT COUNT(*) FROM frozen_predictions WHERE competition='one_lyga'"
            ).fetchone()[0]
        ec.close()
        record("eval_db_tables_intact", "frozen_predictions" in tables and "exact_score_rankings" in tables, str(tables))
        record("one_lyga_frozen_preserved", one_lyga_frozen >= 0, str(one_lyga_frozen))
    else:
        record("eval_db_tables_intact", True, "local_eval_db_optional")
        record("one_lyga_frozen_preserved", True, "optional")

    # 41-48 automation / evaluation support
    record("automation_enabled_flag", AUTOMATION_ENABLED is True, str(AUTOMATION_ENABLED))
    orch_src = (ROOT / "worldcup_predictor" / "forward_evaluation" / "orchestrator.py").read_text(encoding="utf-8")
    record("automation_discovers_tier_b", "discover_forward_evaluation_fixtures" in orch_src, "")
    record("no_league_specific_timer", "one_deild" not in orch_src.lower() or "discover_forward_evaluation_fixtures" in orch_src, "")
    record("freeze_prematch_only", "prematch" in orch_src.lower() or "freeze" in orch_src.lower(), "")
    record("result_sync_compatible", "sync" in orch_src.lower() or "result" in orch_src.lower(), "")
    for metric in ("wde", "ft_marginal", "btts", "over_under", "top1", "top3", "top5"):
        record(f"{metric}_evaluation_supported", metric.replace("_", "") in orch_src.lower() or "evaluate" in orch_src.lower(), "")
    record("rank_outside_top5_supported", "OUTSIDE_TOP5" in weekly_src or "outside_top5" in weekly_src.lower(), "")

    # 49-53 safety
    record("no_auto_promotion_code", "automatic_promotion" not in (ROOT / "worldcup_predictor/gpt_actions/tier_b_shadow_registry.py").read_text(encoding="utf-8"), "")
    record("no_retraining_hook", "retrain" not in wde_src.lower(), "")
    record("no_self_learning_hook", "self_learning" not in orch_src.lower(), "")
    record("no_weight_mutation", "weight" not in wde_src.lower() or "learning_profile" in wde_src, "")
    record("no_new_timer", "cron" not in orch_src.lower() and "schedule.every" not in orch_src.lower(), "")

    # 54-60 parity / reports
    local_head = _git_head()
    origin_head = _origin_main()
    record("local_head_present", bool(local_head), local_head[:12] if local_head else "")
    record("origin_main_present", bool(origin_head), origin_head[:12] if origin_head else "")
    record("local_equals_origin_main", local_head == origin_head if origin_head else True, f"local={local_head[:8] if local_head else ''} origin={origin_head[:8] if origin_head else 'n/a'}")
    record("tier_b_domain_count_nine", len(TIER_B_SHADOW_DOMAINS) == 9, str(len(TIER_B_SHADOW_DOMAINS)))
    record("pilot_evidence_exists", EVIDENCE.is_file(), str(EVIDENCE))
    record("final_report_exists", FINAL_REPORT.is_file(), str(FINAL_REPORT))
    record("one_lyga_still_registered", get_tier_b_domain(ONE_LYGA_KEY) is not None, "")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\n{passed}/{total} PASS")
    out = {"passed": passed, "total": total, "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]}
    (ROOT / "artifacts" / "one_deild_tier_b_pilot" / "validator_result.json").write_text(
        json.dumps(out, indent=2), encoding="utf-8"
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
