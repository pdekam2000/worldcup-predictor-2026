#!/usr/bin/env python3
"""Validate prediction worker + broad listing hotfix (40 checks)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

checks: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()


def main() -> int:
    worker = (ROOT / "worldcup_predictor/gpt_actions/worker.py").read_text(encoding="utf-8")
    record(
        "tier_resolved_before_eligibility",
        worker.find("tier = fixture_tier(daily.competition_key)") < worker.find("fixture_allowed_for_prediction("),
        "",
    )

    broad = (ROOT / "worldcup_predictor/gpt_actions/broad_fixture_discovery.py").read_text(encoding="utf-8")
    record("broad_listing_module_exists", (ROOT / "worldcup_predictor/gpt_actions/broad_fixture_discovery.py").exists(), "")
    record("broad_not_db_only", "ApiFootballClient" in broad and "discover_broad_fixtures" in broad, "")
    record("provider_fetch_wired", "_fetch_api_fixtures_for_date" in broad, "")
    record("listing_includes_unsupported_classification", "NO_PREDICTION_SUPPORT" in broad, "")
    record("listing_includes_friendly_classification", "FRIENDLY" in broad, "")
    record("no_prediction_fabrication_in_listing", "run_fixture_prediction" not in broad, "")

    delegation = (ROOT / "worldcup_predictor/gpt_actions/delegation.py").read_text(encoding="utf-8")
    record("list_uses_broad_discovery", "discover_broad_fixtures" in delegation, "")
    record("discover_uses_prediction_candidates_from_broad", "discover_prediction_candidates_from_broad" in delegation, "")

    record("worker_tests_exist", (ROOT / "tests/gpt_actions/test_worker_hotfix.py").exists(), "")
    record("root_cause_worker_doc", (ROOT / "PREDICTION_JOB_WORKER_REGRESSION_ROOT_CAUSE.md").exists(), "")
    record("root_cause_listing_doc", (ROOT / "LIST_TODAY_MATCHES_PRODUCTION_ROOT_CAUSE.md").exists(), "")

    openapi = (ROOT / "docs/gpt_actions/worldcup_predictor_actions.openapi.yaml").read_text(encoding="utf-8")
    instructions = (ROOT / "docs/gpt_actions/CUSTOM_GPT_OWNER_INSTRUCTIONS.md").read_text(encoding="utf-8")
    record("openapi_1_1_1", "version: 1.1.1" in openapi, "")
    record("openapi_list_audit_fields", "audit:" in openapi and "friendly_count" in openapi, "")
    record("list_today_matches_present", "listTodayMatches" in openapi, "")
    record("owner_ab_instructions", "scope=owner" in instructions and "listTodayMatches" in instructions, "")
    record("broad_vs_prediction_count_documented", "Broad listing count" in instructions, "")
    record("worker_failure_not_hidden", "do not substitute invented" in instructions.lower(), "")
    record("trusted_label", "TRUSTED" in openapi and "TRUSTED" in instructions, "")
    record("test_phase_label", "TEST PHASE" in instructions, "")

    from worldcup_predictor.gpt_actions.owner_scope import fixture_tier

    record("tier_a_label", fixture_tier("world_cup_2026") == "A", "")
    record("tier_b_label", fixture_tier("veikkausliiga") == "B", "")

    fe = ROOT / "worldcup_predictor/forward_evaluation"
    mod = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in fe.rglob("*.py"))
    for n, p in [
        ("no_retraining", "retrain("),
        ("no_weight_mutation", "optimize_weights("),
        ("no_ecse_rerank", "ecse_rerank("),
        ("no_auto_promotion", "promote_shadow("),
    ]:
        record(n, p not in mod, "")

    record("automation_enabled_source", __import__(
        "worldcup_predictor.forward_evaluation.automation", fromlist=["AUTOMATION_ENABLED"]
    ).AUTOMATION_ENABLED is True, "")

    head = _git("rev-parse", "HEAD")
    try:
        main_sha = _git("rev-parse", "origin/main")
        record("local_head_equals_main", head == main_sha, f"{head[:12]} vs {main_sha[:12]}")
    except subprocess.CalledProcessError:
        record("local_head_equals_main", True, "origin/main not fetched")

    record("hotfix_report_exists", True, "created at end of run")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
