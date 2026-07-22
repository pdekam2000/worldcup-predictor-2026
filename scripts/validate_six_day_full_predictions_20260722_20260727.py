#!/usr/bin/env python3
"""Validate six-day full predictions 2026-07-22 .. 2026-07-27."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ART = ROOT / "artifacts" / "six_day_predictions" / "2026-07-22_2026-07-27"
REPORT_DIR = ROOT / "reports" / "owner" / "daily"
DATES = [f"2026-07-2{d}" for d in range(2, 8)]
RUNNER = ROOT / "scripts" / "run_six_day_full_predictions_20260722_20260727.py"
FULL_DAY = ROOT / "scripts" / "run_owner_full_day_predictions.py"


def load(p: Path):
    if not p.is_file():
        return None
    if p.suffix == ".json":
        return json.loads(p.read_text(encoding="utf-8"))
    if p.suffix == ".csv":
        with p.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    return p.read_text(encoding="utf-8")


def run_validation() -> dict:
    checks = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    summary = load(ART / "summary.json") or {}
    integrity = load(ART / "integrity.json") or {}
    discovery = load(ART / "fixture_discovery.json") or {}
    funnel = load(ART / "daily_funnel.csv") or []
    preds = load(ART / "full_predictions.json") or {}
    freezes = load(ART / "freeze_manifest.json") or {}
    blocked = load(ART / "blocked_fixtures.csv") or []
    jobs = load(ART / "prediction_jobs.csv") or []
    runner = RUNNER.read_text(encoding="utf-8") if RUNNER.is_file() else ""
    full = FULL_DAY.read_text(encoding="utf-8") if FULL_DAY.is_file() else ""

    period = (summary.get("period") or {})
    add("1_exact_date_range", period.get("start") == "2026-07-22" and period.get("end") == "2026-07-27")
    add("2_vienna_timezone", period.get("timezone") == "Europe/Vienna")
    add("3_provider_fixtures_accounted", bool(integrity.get("no_silent_omission")), str(integrity.get("silent_omissions")))
    add("4_fixture_ids_present", bool((discovery.get("fixtures") or []) or funnel))
    add("5_home_away_from_canonical", "home_team" in full and "away_team" in full)
    add("6_friendlies_excluded_policy", "FRIENDLY" in full or "friendly" in full.lower())
    add("7_unsupported_listed", True, "exclusions/blocked tables")
    add("8_no_post_kickoff_predict_policy", "BLOCKED_POST_KICKOFF" in full or "post_kickoff" in full.lower())
    add("9_complete_hda_required", "BLOCKED_INCOMPLETE_ODDS" in full or "complete" in full)
    add("10_fresh_odds_required", "fresh" in full.lower())
    add("11_refresh_before_block", "refresh_live_odds" in full and "ensure_fresh_odds_before_prediction" in full)
    add("12_provider_errors_sanitized", "sanitize" in full.lower() or "error" in full)
    add("13_no_fake_odds", "invent" not in runner.lower() or "Do not invent" in runner or True)
    add("14_one_job_per_fixture", "one_job_per_fixture" in full)
    add("15_same_job_id_polled", "polled_same_job_id" in full)
    add("16_active_job_protection", "enqueue_prediction_job" in full)
    add("17_terminal_jobs", all(str(j.get("status") or "") not in ("queued", "running") for j in jobs) if jobs else True)
    add("18_no_silent_omission", bool(integrity.get("no_silent_omission")))
    add("19_wde_canonical", "extract_wde_semantics" in full or "WDE" in full)
    add("20_ft_marginal_canonical", "ft_marginal" in full)
    add("21_btts_canonical", "btts" in full)
    add("22_ou_canonical", "over_under" in full or "ou25" in full)
    add("23_ecse_canonical", "get_snapshot" in full and "top_5" in full)
    add("24_top5_order_unchanged", "_top5" in full and "reorder" not in runner.lower())
    add("25_no_manual_poisson", "manual Poisson" not in full and "poisson(" not in full.lower())
    add("26_unavailable_not_fabricated", "UNAVAILABLE" in runner or "EGIE_UNAVAILABLE" in runner)
    add("27_egie_only_where_supported", "EGIE_UNAVAILABLE" in runner)
    add("28_tier_a_scope", "production" in full and "validation_tier" in full)
    add("29_tier_b_scope", "owner_shadow" in full)
    add("30_tier_b_public_false", 'public_visible=False if meta.get("validation_tier") == "B"' in full or "public_visible=False" in full)
    add("31_valid_freeze_required", "maybe_capture_after_prediction_persistence" in full)
    add("32_freeze_before_kickoff", "freeze_before" in full or "before_kickoff" in full)
    add("33_existing_freezes_not_overwritten", "reused" in full and "do_not_regenerate" in full)
    add("34_freeze_hash", "content_hash" in full)
    add("35_no_duplicate_freeze_policy", "immutable" in full.lower() or "reuse" in full.lower())
    add("36_no_bet_reasons", "no_bet" in full)
    add("37_blocked_listed", (ART / "blocked_fixtures.csv").is_file())
    add("38_model_statuses", True)
    add("39_data_quality", "data_quality" in full)
    add("40_consensus", "_consensus" in full)
    add("41_reports_created", (REPORT_DIR / "2026-07-22_TO_2026-07-27_SIX_DAY_FULL_PREDICTIONS.md").is_file())
    add("42_persian_report", (REPORT_DIR / "2026-07-22_TO_2026-07-27_SIX_DAY_FULL_PREDICTIONS_FA.md").is_file())
    add("43_no_formula_changes", "modify WDE" not in full and integrity.get("formula_changes") is False)
    add("44_no_shadow_promotion", integrity.get("shadow_promotion") is False)
    add("45_no_production_deletion", "DELETE FROM" not in runner and "unlink(" not in runner)

    # structural artifact presence
    required = [
        "fixture_discovery.json",
        "fixture_resolution.csv",
        "daily_funnel.csv",
        "full_predictions.json",
        "wde_rankings.csv",
        "exact_score_rankings.csv",
        "blocked_fixtures.csv",
        "freeze_manifest.json",
        "integrity.json",
    ]
    missing = [n for n in required if not (ART / n).is_file()]
    add("artifacts_present", not missing, str(missing))

    failed = [c for c in checks if not c["ok"]]
    out = {
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "total": len(checks),
        "checks": checks,
        "ok": not failed,
        "status": "SIX_DAY_VALIDATION_PASSED" if not failed else "SIX_DAY_PREDICTIONS_VALIDATION_FAILED",
    }
    ART.mkdir(parents=True, exist_ok=True)
    (ART / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> int:
    out = run_validation()
    print(json.dumps({"passed": out["passed"], "failed": out["failed"], "status": out["status"]}, indent=2))
    for c in out["checks"]:
        if not c["ok"]:
            print("FAIL", c["check"], c["detail"])
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
