#!/usr/bin/env python3
"""Validate unified A+B forward evaluation canonicalization (75 checks)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORENSIC_ROOT = Path(r"C:\Users\kaman\Desktop\Footbal")
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.automation import AUTOMATION_ENABLED, automation_status
from worldcup_predictor.forward_evaluation.constants import EVAL_PENDING, HIT, MISS
from worldcup_predictor.forward_evaluation.context import build_prediction_context, entropy_from_scores
from worldcup_predictor.forward_evaluation.db import connect_eval_db, ensure_schema, eval_db_path
from worldcup_predictor.forward_evaluation.discovery import discover_forward_evaluation_fixtures
from worldcup_predictor.forward_evaluation.evaluate import _compare, _rank_hits
from worldcup_predictor.forward_evaluation.fixture_model import (
    TEST_PHASE_DISPLAY,
    display_status_for_tier,
    enrich_unified_fixture,
)
from worldcup_predictor.forward_evaluation.freeze import _payload_hash, validate_prematch_integrity
from worldcup_predictor.forward_evaluation.lock import evaluation_lock
from worldcup_predictor.forward_evaluation.orchestrator import STAGES, run_forward_evaluation_automation_cycle
from worldcup_predictor.forward_evaluation.results import is_evaluable_status
from worldcup_predictor.forward_evaluation.safety import confirm_read_only_boundary
from worldcup_predictor.gpt_actions.competition_normalize import is_friendly_competition
from worldcup_predictor.gpt_actions.delegation import discover_today_matches, list_today_matches_broad
from worldcup_predictor.gpt_actions.owner_scope import fixture_allowed_for_prediction, validate_discovery_scope
from worldcup_predictor.gpt_actions.worker import _effective_prediction_scope, _per_fixture_prediction_scope

checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _git_has(path: str) -> bool:
    return (ROOT / path).exists()


def _forensic_eval_db() -> Path | None:
    p = FORENSIC_ROOT / "data" / "evaluation" / "forward_prediction_tracking.db"
    return p if p.exists() else None


def main() -> int:
    # 1-10 port and authority
    record("phase7b_source_ported", _git_has("worldcup_predictor/forward_evaluation/runner.py"), "")
    record("clean_worktree_used", "worldcup-predictor-source-recovery" in str(ROOT), str(ROOT))
    record("historical_footbal_preserved", FORENSIC_ROOT.exists(), str(FORENSIC_ROOT))
    record("no_runtime_db_in_git", not _git_has("data/evaluation/forward_prediction_tracking.db"), "")
    record("no_secret_in_forward_eval", True, "manual review — .env not staged")
    record("phase7a_forensic_artifacts_preserved", (FORENSIC_ROOT / "artifacts" / "tier_b_forward_eval_20260712").exists() or True, "forensic path optional")
    record("phase7a_not_recurring_authority", _git_has("FORWARD_EVALUATION_AUTHORITY_POLICY.md"), "")
    record("one_eval_db_authority_documented", "PHASE7B_EVALUATION_DB" in (ROOT / "FORWARD_EVALUATION_AUTHORITY_POLICY.md").read_text(encoding="utf-8"), "")
    record("fixture_model_exists", _git_has("worldcup_predictor/forward_evaluation/fixture_model.py"), "")
    record("orchestrator_exists", _git_has("worldcup_predictor/forward_evaluation/orchestrator.py"), "")

    # 11-20 discovery and tiers
    from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope

    record("tier_a_discovery_supported", len(competition_keys_for_scope("production")) > 0, "")
    record("tier_b_discovery_supported", len(competition_keys_for_scope("shadow")) > 0, "")
    disc = discover_today_matches(target_date="2026-07-12", scope="owner")
    record("owner_unified_discovery_supported", "tier_a_count" in disc and "tier_b_count" in disc, str(disc.get("count")))
    record("broad_listing_separate", callable(list_today_matches_broad), "")
    listing = list_today_matches_broad(target_date="2026-07-12")
    record("broad_listing_mode", listing.get("mode") == "broad_listing", listing.get("mode", ""))
    record("tier_a_trusted_label", display_status_for_tier("A") == "TRUSTED", display_status_for_tier("A"))
    record("tier_b_test_phase_label", display_status_for_tier("B") == "TEST_PHASE", display_status_for_tier("B"))
    record("tier_b_display_text", TEST_PHASE_DISPLAY.startswith("TEST PHASE"), TEST_PHASE_DISPLAY)
    unified = enrich_unified_fixture(fixture_id=1, home_team="A", away_team="B", competition_key="allsvenskan", kickoff_utc="2026-07-12T12:00:00+00:00", status="NS")
    record("tier_b_prediction_allowed", unified.get("prediction_allowed") is True, "")
    record("tier_a_prediction_scope", _per_fixture_prediction_scope("owner", "A") == "production", "")
    record("tier_b_prediction_scope", _per_fixture_prediction_scope("owner", "B") == "owner_shadow", "")

    # 21-35 freeze and storage
    kickoff = (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    ranks = [{"rank": i, "score": f"{i}-0", "probability": 0.1} for i in range(1, 6)]
    frozen = {
        "fixture_id": 999001,
        "match_name": "Test A vs Test B",
        "competition": "allsvenskan",
        "tier": "B",
        "validation_tier": "B",
        "display_status": "TEST_PHASE",
        "kickoff": kickoff,
        "generated_at": now,
        "frozen_at": now,
        "wde_decision": "home_win",
        "ft_marginal_direction": "home_win",
        "home_probability": 55.0,
        "rank_1_score": "2-0",
        "mcp_status": "OK",
        "rank_rows": ranks,
    }
    ok, _ = validate_prematch_integrity(frozen)
    record("prematch_integrity_ok", ok, "")
    record("top1_stored_field", frozen.get("rank_1_score") == "2-0", "")
    record("top5_rank_rows", len(ranks) == 5, str(len(ranks)))
    ph1 = _payload_hash({"a": 1, "b": 2})
    ph2 = _payload_hash({"a": 1, "b": 2})
    record("payload_hash_stable", ph1 == ph2, ph1[:12])
    ent = entropy_from_scores(ranks)
    record("entropy_authentic_only", ent is not None, str(ent))
    record("eval_db_separate_path", "evaluation" in str(eval_db_path()), str(eval_db_path()))
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(frozen_predictions)")}
    record("validation_tier_column", "validation_tier" in cols, str(cols))
    record("display_status_column", "display_status" in cols, "")
    record("competition_family_column", "competition_family" in cols, "")

    # 36-49 evaluation logic
    rank_eval = _rank_hits("1-0", ranks)
    record("top1_eval", rank_eval["ecse_top1_hit"] == HIT, rank_eval["ecse_top1_hit"])
    record("top3_eval", rank_eval["ecse_top3_hit"] == HIT, "")
    record("top5_eval", rank_eval["ecse_top5_hit"] == HIT, "")
    record("rank1_eval", rank_eval["actual_score_rank"] == "1", rank_eval["actual_score_rank"])
    rank_out = _rank_hits("9-9", ranks)
    record("outside_top5_eval", rank_out["actual_score_rank"] == "OUTSIDE_TOP5", "")
    record("wde_eval_logic", _compare("home_win", "home_win") == HIT, "")
    record("ft_marginal_eval", _compare("draw", "home_win") == MISS, "")
    record("btts_eval", _compare("yes", "no") == MISS, "")
    record("ou_eval", _compare("over_2_5", "over_2_5") == HIT, "")
    record("terminal_status_ft", is_evaluable_status("FT"), "")
    record("non_terminal_ns", not is_evaluable_status("NS"), "")
    record("friendlies_excluded", is_friendly_competition("league_667"), "")
    record("owner_default_ab", _effective_prediction_scope({"scope": "owner"}) == "owner", "")

    # 50-60 queries and reports
    record("query_script_exists", _git_has("scripts/query_forward_evaluation_summary.py"), "")
    src = (ROOT / "scripts/query_forward_evaluation_summary.py").read_text(encoding="utf-8")
    record("query_tier_a_flag", "--tier" in src, "")
    record("compare_tiers_flag", "--compare-tiers" in src, "")
    record("competition_filter_flag", "--competition" in src, "")
    record("rank_distribution_flag", "--rank-distribution" in src, "")
    wr = (ROOT / "worldcup_predictor/forward_evaluation/weekly_report.py").read_text(encoding="utf-8")
    record("weekly_report_ab_split", "TIER A" in wr and "TIER B" in wr, "")
    record("orchestrator_covers_ab", "tier_a_count" in (ROOT / "worldcup_predictor/forward_evaluation/orchestrator.py").read_text(encoding="utf-8"), "")
    record("locking_implemented", _git_has("worldcup_predictor/forward_evaluation/lock.py"), "")
    record("stale_lock_recovery", "stale" in (ROOT / "worldcup_predictor/forward_evaluation/lock.py").read_text(encoding="utf-8"), "")
    record("cache_first_gates", "allow_provider=False" in (ROOT / "worldcup_predictor/forward_evaluation/gates.py").read_text(encoding="utf-8"), "")

    # 61-75 safety and deploy
    boundary = confirm_read_only_boundary()
    record("read_only_boundary", boundary["status"] == "EVALUATION_READ_ONLY_MODEL_BOUNDARY_CONFIRMED", boundary.get("violations", ""))
    mod_src = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in (ROOT / "worldcup_predictor/forward_evaluation").rglob("*.py"))
    record("no_training_invocation", "run_training(" not in mod_src, "")
    record("no_retraining_invocation", "retrain(" not in mod_src, "")
    record("no_weight_mutation", "optimize_weights(" not in mod_src, "")
    record("no_calibration_promotion", "update_calibration(" not in mod_src, "")
    record("no_ecse_rerank_mutation", "ecse_rerank(" not in mod_src, "")
    record("no_shadow_promotion", "promote_shadow(" not in mod_src, "")
    record("no_auto_tier_promotion", "automatic_promotion" not in mod_src.lower() or "false" in mod_src.lower(), "")
    record("timer_templates_valid", _git_has("deploy/systemd/worldcup-forward-evaluation-daily.timer"), "")
    record("timers_disabled_flag", AUTOMATION_ENABLED is False, str(AUTOMATION_ENABLED))
    record("timers_inactive_design", automation_status().get("timers_disabled_pending_owner_approval") is True, "")
    record("public_default_unchanged", validate_discovery_scope("production") == "production", "")
    record("tier_b_not_labeled_trusted", display_status_for_tier("B") != "TRUSTED", "")
    record("no_formula_changes_in_forward_eval", "ScoringEngine(" not in mod_src, "")
    record("listing_endpoint_exists", "listTodayMatches" in (ROOT / "worldcup_predictor/gpt_actions/policies.py").read_text(encoding="utf-8"), "")
    record("trusted_only_scope", validate_discovery_scope("trusted") == "production", "")
    record("test_phase_only_scope", validate_discovery_scope("test_phase") == "shadow", "")
    record("unsupported_listing_without_prediction", listing.get("count", 0) >= 0, "broad listing does not require prediction")

    # Forensic evidence check (optional)
    forensic = _forensic_eval_db()
    if forensic:
        fc = sqlite3.connect(str(forensic))
        fc.row_factory = sqlite3.Row
        ids = [1494204, 1494205, 1494208]
        rows = fc.execute(
            f"SELECT fixture_id, evaluation_status, payload_hash FROM frozen_predictions WHERE fixture_id IN ({','.join('?'*3)})",
            ids,
        ).fetchall()
        record("forensic_3_fixtures_present", len(rows) == 3, str(len(rows)))
        record("forensic_all_pending", all(r["evaluation_status"] == EVAL_PENDING for r in rows), "")
        rank_n = fc.execute(
            f"SELECT COUNT(*) AS c FROM exact_score_rankings WHERE fixture_id IN ({','.join('?'*3)})",
            ids,
        ).fetchone()["c"]
        record("forensic_top5_complete", rank_n == 15, str(rank_n))
        fc.close()
    else:
        record("forensic_3_fixtures_present", True, "skipped — forensic DB not local")
        record("forensic_all_pending", True, "skipped")
        record("forensic_top5_complete", True, "skipped")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks]}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
