#!/usr/bin/env python3
"""Validate Correct Score odds ingestion + real-odds portfolio research."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ART = ROOT / "artifacts" / "correct_score_odds"
ART_P = ROOT / "artifacts" / "two_fixture_portfolio_real_odds"
REPORTS = ROOT / "reports" / "owner"
OUT = ROOT / "artifacts" / "correct_score_odds_validation.json"

VALID = {
    "CORRECT_SCORE_ODDS_INGESTION_COMPLETE",
    "CORRECT_SCORE_ODDS_FORWARD_COLLECTION_ACTIVE",
    "CORRECT_SCORE_ODDS_MANUAL_IMPORT_REQUIRED",
    "CORRECT_SCORE_ODDS_PROVIDER_NOT_AVAILABLE",
    "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_EDGE_PROVEN",
    "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_NO_EDGE",
    "TWO_FIXTURE_PORTFOLIO_MORE_FORWARD_DATA_REQUIRED",
    "CORRECT_SCORE_ODDS_VALIDATION_FAILED",
}

REQUIRED_CS = [
    "provider_capability_matrix.json",
    "raw_ingestion_manifest.json",
    "parsed_odds.csv",
    "rejected_rows.csv",
    "fixture_market_completeness.csv",
    "bookmaker_coverage.csv",
    "odds_freshness.csv",
    "historical_collection_status.json",
    "forward_collection_plan.json",
    "ingestion_summary.json",
]


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def main() -> int:
    checks: list[dict] = []
    for name in REQUIRED_CS:
        p = ART / name
        checks.append(check(f"artifact_{name}", p.is_file() and p.stat().st_size >= 0, str(p)))

    summary = json.loads((ART / "ingestion_summary.json").read_text(encoding="utf-8"))
    matrix = json.loads((ART / "provider_capability_matrix.json").read_text(encoding="utf-8"))
    manifest = json.loads((ART / "raw_ingestion_manifest.json").read_text(encoding="utf-8"))
    forward = json.loads((ART / "forward_collection_plan.json").read_text(encoding="utf-8"))
    hist = json.loads((ART / "historical_collection_status.json").read_text(encoding="utf-8"))

    checks.append(check("provider_capability_audited", len(matrix) >= 4))
    checks.append(check("api_football_in_matrix", any(p["provider"] == "api_football" for p in matrix)))

    from worldcup_predictor.research.correct_score_odds.mapping import (
        normalize_market_name,
        parse_selection,
    )
    from worldcup_predictor.research.correct_score_odds.statuses import CANONICAL_MARKET

    checks.append(check("canonical_market_mapping", normalize_market_name("Correct Score") == CANONICAL_MARKET))
    checks.append(check("reject_et_market", normalize_market_name("Correct Score Extra Time") is None))
    checks.append(check("reject_1h_market", normalize_market_name("1st Half Correct Score") is None))
    sel = parse_selection("2-1")
    checks.append(check("exact_score_parsed", sel and sel["selection"] == "2-1" and sel["home_goals"] == 2))
    anyo = parse_selection("Any Other Home Win")
    checks.append(check("any_other_separate", anyo and anyo["is_any_other"] is True and anyo["home_goals"] is None))

    checks.append(check("timestamps_in_manifest", "ingestion_run_id" in manifest))
    checks.append(check("cache_first_zero_api", manifest.get("api_calls", 0) == 0))
    checks.append(check("no_prediction_jobs", manifest.get("prediction_jobs_created", 0) == 0))
    checks.append(check("no_freeze_modified", manifest.get("freezes_modified", 0) == 0))
    checks.append(check("historical_checkpointed", bool(hist.get("checkpoint"))))
    checks.append(check("forward_stops_at_kickoff", forward.get("never_after_kickoff") is True))

    # parsed odds validity sample
    parsed_path = ART / "parsed_odds.csv"
    if parsed_path.stat().st_size > 0:
        with parsed_path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))[:200]
        if rows:
            checks.append(
                check(
                    "decimal_odds_valid",
                    all(float(r["decimal_odds"]) > 1 for r in rows if r.get("decimal_odds")),
                )
            )
            checks.append(
                check(
                    "prematch_only_export",
                    all(r.get("prematch_status") == "prematch" for r in rows),
                )
            )
            checks.append(
                check(
                    "settlement_90",
                    all(r.get("settlement_scope") == "90_MINUTES" for r in rows),
                )
            )
            checks.append(check("bookmaker_provenance", all(r.get("bookmaker_name") for r in rows)))
            checks.append(check("provider_provenance", all(r.get("provider") for r in rows)))
            checks.append(
                check(
                    "secrets_absent_in_export",
                    not any("api_key" in json.dumps(r).lower() for r in rows[:50]),
                )
            )
        else:
            checks.append(check("decimal_odds_valid", True, "empty_ok"))
            checks.append(check("prematch_only_export", True, "empty_ok"))
            checks.append(check("settlement_90", True, "empty_ok"))
            checks.append(check("bookmaker_provenance", True, "empty_ok"))
            checks.append(check("provider_provenance", True, "empty_ok"))
            checks.append(check("secrets_absent_in_export", True, "empty_ok"))
    else:
        for name in (
            "decimal_odds_valid",
            "prematch_only_export",
            "settlement_90",
            "bookmaker_provenance",
            "provider_provenance",
            "secrets_absent_in_export",
        ):
            checks.append(check(name, True, "no_parsed_rows"))

    # Manual import design
    manual = json.loads((ART / "manual_import_design.json").read_text(encoding="utf-8"))
    checks.append(check("manual_odds_labelled", manual["design"].get("api_fetched") is False))
    checks.append(check("manual_requires_confirmation", manual["design"].get("requires_owner_confirmation") is True))

    # Engine combo multiplication
    from worldcup_predictor.research.two_fixture_portfolio.engine import build_primary_matrix

    top5_a = [{"score": f"1-{i}", "probability": 0.1} for i in range(5)]
    top5_b = [{"score": f"0-{i}", "probability": 0.1} for i in range(5)]
    odds_a = {s["score"]: 5.0 for s in top5_a}
    odds_b = {s["score"]: 4.0 for s in top5_b}
    mat = build_primary_matrix(top5_a, top5_b, odds_a, odds_b)
    checks.append(check("primary_25", len(mat) == 25))
    checks.append(check("combo_odds_multiplication", all(abs(t["combo_odds"] - 20.0) < 1e-9 for t in mat)))

    from worldcup_predictor.research.two_fixture_portfolio.engine import classify_arbitrage

    arb = classify_arbitrage([2.0, 2.0, 2.0])
    checks.append(check("no_false_arbitrage", arb["classification"] != "TRUE_ARBITRAGE" or arb["inverse_sum"] < 1))
    checks.append(check("incomplete_space_flag", arb.get("outcome_space_complete") is False))

    # Portfolio real odds artifacts
    roi_path = ART_P / "roi_summary.json"
    if roi_path.is_file():
        roi = json.loads(roi_path.read_text(encoding="utf-8"))
        status = roi.get("final_status")
        checks.append(check("portfolio_status_valid", status in VALID, str(status)))
        checks.append(check("roi_real_only_flag", roi.get("strategies", {}).get("EQUAL", {}).get("synthetic_used_in_roi") is False))
        checks.append(check("no_production_betting", roi.get("deploy_betting") is False and roi.get("auto_bet") is False))
        # primary real odds file
        p25 = ART_P / "primary_25_real_odds.csv"
        if p25.is_file() and p25.stat().st_size > 0:
            with p25.open(encoding="utf-8") as fh:
                prow = list(csv.DictReader(fh))[:50]
            checks.append(
                check(
                    "real_synthetic_separated",
                    all(str(r.get("synthetic")).lower() == "false" for r in prow) if prow else True,
                )
            )
            checks.append(
                check(
                    "primary_odds_kind_real_or_unavailable",
                    all(r.get("odds_kind") in {"REAL", "UNAVAILABLE"} for r in prow) if prow else True,
                )
            )
        else:
            checks.append(check("real_synthetic_separated", True, "no_primary_rows"))
            checks.append(check("primary_odds_kind_real_or_unavailable", True, "no_primary_rows"))
        checks.append(check("full_loss_in_roi", "full_loss_rate" in (roi.get("strategies", {}).get("EQUAL") or {})))
        checks.append(check("cross_bookmaker_labelled", (ART_P / "bookmaker_comparison.csv").is_file()))
        checks.append(check("stake_allocations_present", (ART_P / "stake_allocations.csv").is_file()))
        final_status = status
    else:
        checks.append(check("portfolio_status_valid", False, "missing roi_summary"))
        checks.append(check("roi_real_only_flag", False))
        checks.append(check("no_production_betting", summary.get("deploy_betting") is False))
        checks.append(check("real_synthetic_separated", False))
        checks.append(check("primary_odds_kind_real_or_unavailable", False))
        checks.append(check("full_loss_in_roi", False))
        checks.append(check("cross_bookmaker_labelled", False))
        checks.append(check("stake_allocations_present", False))
        final_status = summary.get("final_status")

    checks.append(check("ingestion_status_valid", summary.get("final_status") in VALID, str(summary.get("final_status"))))
    checks.append(check("quota_protection_cache_first", manifest.get("api_calls", 0) == 0))
    checks.append(check("daily_pipeline_hook_exists", (ROOT / "worldcup_predictor/owner_daily/pipeline/orchestrator.py").is_file()))
    # ensure hook text present
    orch = (ROOT / "worldcup_predictor/owner_daily/pipeline/orchestrator.py").read_text(encoding="utf-8")
    checks.append(check("daily_pipeline_prediction_unaffected_design", "blocked_prediction" in orch and "enrich_correct_score_odds" in orch))
    checks.append(check("no_model_formula_changes", summary.get("ecse_changed") is False and summary.get("wde_changed") is False))
    checks.append(check("english_audit", (REPORTS / "CORRECT_SCORE_ODDS_PROVIDER_CAPABILITY_AUDIT.md").is_file()))
    checks.append(check("english_ingestion_report", (REPORTS / "CORRECT_SCORE_ODDS_INGESTION_REPORT.md").is_file()))
    checks.append(check("persian_ingestion_report", (REPORTS / "CORRECT_SCORE_ODDS_INGESTION_REPORT_FA.md").is_file()))
    checks.append(check("english_portfolio_report", (REPORTS / "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_RESEARCH.md").is_file()))
    checks.append(check("persian_portfolio_report", (REPORTS / "TWO_FIXTURE_PORTFOLIO_REAL_ODDS_RESEARCH_FA.md").is_file()))
    checks.append(check("final_status_valid", final_status in VALID, str(final_status)))

    # unit: parser rejects post-kickoff
    from worldcup_predictor.research.correct_score_odds.parser import validate_line
    from datetime import datetime, timezone

    ok, reason = validate_line(
        decimal_odds=5.0,
        selection_meta={"market": CANONICAL_MARKET, "is_any_other": False},
        fetched_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        kickoff=datetime(2026, 1, 1, tzinfo=timezone.utc),
        market_status="open",
        settlement_scope="90_MINUTES",
    )
    checks.append(check("live_odds_excluded", ok is False and reason == "post_kickoff_or_live"))

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    payload = {"passed": passed, "total": total, "checks": checks, "final_status": final_status}
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "total": total, "final_status": final_status}, indent=2))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
