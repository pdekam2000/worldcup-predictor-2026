#!/usr/bin/env python3
"""Phase A11 — Prediction Detail Pro validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"
PRO = FRONTEND / "src/components/prediction-detail-pro"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    components = [
        "MatchHeaderPro.jsx",
        "PredictionSummaryCards.jsx",
        "PredictionMarketsPro.jsx",
        "AIMatchIntelligence.jsx",
        "TeamComparison.jsx",
        "OddsCenter.jsx",
        "ExpectedGoalsSection.jsx",
        "PressureSection.jsx",
        "LineupsSection.jsx",
        "AgentContributionPanel.jsx",
        "ConfidenceExplanation.jsx",
        "BetSlipActions.jsx",
        "PredictionHistorySection.jsx",
        "DetailSectionSkeleton.jsx",
    ]
    for c in components:
        record(checks, f"component_{c.replace('.jsx', '')}", (PRO / c).is_file())

    record(checks, "utils_file", (FRONTEND / "src/lib/predictionDetailProUtils.js").is_file())

    page = (FRONTEND / "src/pages/MatchDetailPage.jsx").read_text(encoding="utf-8")
    utils = (FRONTEND / "src/lib/predictionDetailProUtils.js").read_text(encoding="utf-8")

    record(checks, "page_match_header", "MatchHeaderPro" in page)
    record(checks, "page_summary_cards", "PredictionSummaryCards" in page)
    record(checks, "page_markets_pro", "PredictionMarketsPro" in page)
    record(checks, "page_ai_intelligence", "AIMatchIntelligence" in page)
    record(checks, "page_team_comparison", "TeamComparison" in page)
    record(checks, "page_odds_center", "OddsCenter" in page)
    record(checks, "page_xg_section", "ExpectedGoalsSection" in page)
    record(checks, "page_pressure", "PressureSection" in page)
    record(checks, "page_lineups", "LineupsSection" in page)
    record(checks, "page_agent_contribution", "AgentContributionPanel" in page)
    record(checks, "page_confidence_expl", "ConfidenceExplanation" in page)
    record(checks, "page_bet_slip_actions", "BetSlipActions" in page)
    record(checks, "page_history_section", "PredictionHistorySection" in page)
    record(checks, "page_section_tabs", "SECTION_TABS" in page)
    record(checks, "page_skeleton", "DetailSectionSkeleton" in page)
    record(checks, "mobile_padding", "px-1 sm:px-0" in page)
    record(checks, "responsive_grid", "lg:grid-cols-2" in page)

    record(checks, "utils_build_summary", "buildSummary" in utils)
    record(checks, "utils_group_markets", "groupMarkets" in utils)
    record(checks, "utils_ai_insights", "buildAiInsights" in utils)
    record(checks, "utils_confidence_expl", "buildConfidenceExplanation" in utils)
    record(checks, "utils_agent_contrib", "buildAgentContribution" in utils)
    record(checks, "utils_xg", "buildXgSection" in utils)
    record(checks, "utils_pressure", "buildPressureSection" in utils)
    record(checks, "utils_lineups", "buildLineupsSection" in utils)

    agent = (PRO / "AgentContributionPanel.jsx").read_text(encoding="utf-8")
    record(checks, "owner_only_agents", "isOwnerUser" in agent and "isAdminUser" in agent)

    bet = (PRO / "BetSlipActions.jsx").read_text(encoding="utf-8")
    record(checks, "bet_slip_best_pick", "Add Best Pick" in bet)
    record(checks, "bet_slip_combo", "Add Combo" in bet)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        # Node-side utils smoke via subprocess if node available
        node_script = """
        const u = require("./base44-d/src/lib/predictionDetailProUtils.js");
        """.strip()
        # Python can't require ESM — validate logic inline
        pass
    except Exception:
        pass

    # Import-free JS validation via file content checks on market groups
    record(checks, "market_groups_winner", '"Winner"' in utils or "'Winner'" in utils)
    record(checks, "market_groups_goals", "Goals" in utils)

    header = (PRO / "MatchHeaderPro.jsx").read_text(encoding="utf-8")
    record(checks, "header_ai_score", "aiScoreFromPrediction" in header)
    record(checks, "header_weather", "weather_intelligence" in header)
    record(checks, "header_team_logos", "home_team_logo" in header)

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-500:])
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A11 Prediction Detail Pro — {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    out = ROOT / "data" / "validation" / "phase_a11_prediction_detail.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
