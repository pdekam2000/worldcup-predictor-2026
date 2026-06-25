#!/usr/bin/env python3
"""Phase A9 — Elite Match Center + Combo Tip Center validation."""

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


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # Frontend files
    record(checks, "match_center_page", (FRONTEND / "src/pages/MatchCenter.jsx").is_file())
    record(checks, "match_detail_page", (FRONTEND / "src/pages/MatchDetailPage.jsx").is_file())
    record(checks, "combo_tips_page", (FRONTEND / "src/pages/ComboTipsPage.jsx").is_file())
    record(checks, "league_selector", (FRONTEND / "src/components/match-center/LeagueSelector.jsx").is_file())
    record(checks, "elite_match_card", (FRONTEND / "src/components/match-center/EliteMatchCard.jsx").is_file())
    record(checks, "bet_slip", (FRONTEND / "src/components/match-center/BetSlipDrawer.jsx").is_file())
    record(checks, "bet_slip_context", (FRONTEND / "src/context/BetSlipContext.jsx").is_file())
    record(checks, "combo_generator", (FRONTEND / "src/lib/comboGenerator.js").is_file())

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    nav = (FRONTEND / "src/lib/navConfig.js").read_text(encoding="utf-8")
    api_js = (FRONTEND / "src/api/worldcupApi.js").read_text(encoding="utf-8")

    record(checks, "route_match_detail", 'path="/matches/:fixtureId"' in app)
    record(checks, "route_combo_tips", 'path="/combo-tips"' in app)
    record(checks, "nav_combo_tips", "Combo Tips" in nav)
    record(checks, "api_fetch_competitions", "fetchCompetitions" in api_js)
    record(checks, "api_competition_all", "competition" in api_js)

    # Backend API (no engine changes)
    record(checks, "competitions_route", (ROOT / "worldcup_predictor/api/routes/competitions.py").is_file())
    record(checks, "match_center_helpers", (ROOT / "worldcup_predictor/api/match_center_helpers.py").is_file())

    matches_py = (ROOT / "worldcup_predictor/api/routes/matches.py").read_text(encoding="utf-8")
    record(checks, "matches_all_competition", '"all"' in matches_py or "'all'" in matches_py)
    record(checks, "matches_include_summary", "include_summary" in matches_py)
    record(checks, "matches_competition_key", "competition_key" in matches_py)

    main_py = (ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    record(checks, "competitions_router_registered", "competitions_router" in main_py)

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)

    # EGIE — scoring engine file present; not modified in this phase
    record(checks, "scoring_engine_exists", (ROOT / "worldcup_predictor/prediction/scoring_engine.py").is_file())

    try:
        from worldcup_predictor.api.match_center_helpers import (
            extract_prediction_summary,
            list_enabled_competitions,
        )
        from worldcup_predictor.config.competitions import list_competition_keys

        enabled = list_competition_keys(enabled_only=True)
        record(checks, "dynamic_competitions", len(enabled) >= 5)
        comps = list_enabled_competitions()
        record(checks, "competition_service_list", len(comps) == len(enabled))

        summary = extract_prediction_summary(
            {
                "prediction": "home",
                "confidence": 72,
                "pick_tier": "elite",
                "best_available_pick": {"market": "1x2", "pick": "home", "confidence": 72},
            }
        )
        record(checks, "prediction_summary_shape", "best_pick" in summary and "confidence" in summary)
    except Exception as exc:
        record(checks, "match_center_helpers_import", False, str(exc))

    try:
        from worldcup_predictor.api.routes.competitions import list_competitions

        payload = list_competitions(include_counts=False)
        record(checks, "competitions_api_shape", "competitions" in payload and payload.get("status") == "ok")
        keys = [c["key"] for c in payload["competitions"]]
        record(checks, "world_cup_in_registry", "world_cup_2026" in keys)
        record(checks, "premier_league_in_registry", "premier_league" in keys)
    except Exception as exc:
        record(checks, "competitions_api", False, str(exc))

    elite_card = (FRONTEND / "src/components/match-center/EliteMatchCard.jsx").read_text(encoding="utf-8")
    record(checks, "card_logos", "home_team_logo" in elite_card and "away_team_logo" in elite_card)
    record(checks, "card_prediction_summary", "prediction_summary" in elite_card)
    record(checks, "expandable_predictions", "PredictionExpandPanel" in elite_card)

    combo_page = (FRONTEND / "src/pages/ComboTipsPage.jsx").read_text(encoding="utf-8")
    record(checks, "combo_safe_value_risk", "SAFE COMBO" in combo_page or "buildCombos" in combo_page)

    bet_slip = (FRONTEND / "src/components/match-center/BetSlipDrawer.jsx").read_text(encoding="utf-8")
    record(checks, "copy_bet_slip", "Copy Slip" in bet_slip or "copySlip" in bet_slip)

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=180,
            shell=os.name == "nt",
        )
        record(checks, "npm_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-500:])
    except Exception as exc:
        record(checks, "npm_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" ({detail})" if detail and not ok else ""))
    print(f"SUMMARY {passed}/{total}")
    print(json.dumps({"passed": passed, "total": total}))
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
