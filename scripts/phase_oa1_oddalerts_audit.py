#!/usr/bin/env python3
"""PHASE OA-1 — OddAlerts Trial Audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    from worldcup_predictor.egie.oddalerts_audit.audit import (
        build_provider_decision,
        run_bookmaker_audit,
        run_connectivity_test,
        run_correct_score_audit,
        run_fg_signal_test,
        run_historical_depth_audit,
        run_league_coverage_audit,
        run_market_audit,
    )
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    client = OddAlertsClient()
    if not client.is_configured:
        print("ERROR: ODDALERTS_API_KEY not set in .env")
        return 1

    print("STEP 1 connectivity...")
    connectivity = run_connectivity_test(client)
    (ARTIFACTS / "oddalerts_connectivity_test.json").write_text(
        json.dumps(connectivity, indent=2), encoding="utf-8"
    )

    print("STEP 2 league coverage...")
    coverage = run_league_coverage_audit(client)
    (ARTIFACTS / "oddalerts_league_coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")

    print("STEP 3 bookmaker audit...")
    books = run_bookmaker_audit(client)
    (ARTIFACTS / "oddalerts_bookmaker_audit.json").write_text(json.dumps(books, indent=2), encoding="utf-8")

    print("STEP 4 FG signal test...")
    fg = run_fg_signal_test(client)
    (ARTIFACTS / "oddalerts_fg_signal_test.json").write_text(json.dumps(fg, indent=2), encoding="utf-8")

    print("STEP 5 market audit...")
    markets = run_market_audit(client)
    (ARTIFACTS / "oddalerts_market_audit.json").write_text(json.dumps(markets, indent=2), encoding="utf-8")

    print("STEP 6 correct score audit...")
    cs = run_correct_score_audit(client)
    (ARTIFACTS / "oddalerts_correct_score_audit.json").write_text(json.dumps(cs, indent=2), encoding="utf-8")

    print("STEP 7 historical depth...")
    depth = run_historical_depth_audit(client)
    (ARTIFACTS / "oddalerts_historical_depth.json").write_text(json.dumps(depth, indent=2), encoding="utf-8")

    decision = build_provider_decision(connectivity, coverage, books, fg, markets, cs, depth)
    (ARTIFACTS / "oddalerts_provider_decision.json").write_text(json.dumps(decision, indent=2), encoding="utf-8")

    from scripts._write_phase_oa1_report import write_report

    write_report(
        connectivity=connectivity,
        coverage=coverage,
        books=books,
        fg=fg,
        markets=markets,
        cs=cs,
        depth=depth,
        decision=decision,
    )
    print("STEP 8 report written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
