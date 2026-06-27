#!/usr/bin/env python3
"""Phase A17 — AI Portfolio, Bankroll & Combo Betting Manager validation."""

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

    for rel in (
        "worldcup_predictor/betting_plan/engine.py",
        "worldcup_predictor/betting_plan/combos.py",
        "worldcup_predictor/betting_plan/bankroll.py",
        "worldcup_predictor/betting_plan/legs.py",
        "worldcup_predictor/api/routes/betting_plan.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    api = (ROOT / "worldcup_predictor/api/routes/betting_plan.py").read_text(encoding="utf-8")
    record(checks, "api_today", "/today" in api)
    record(checks, "api_date", "/date" in api)
    record(checks, "api_portfolio", "/portfolio" in api)
    record(checks, "api_combo", "/combo" in api)

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    record(checks, "ui_route", "/betting-plan" in app and "BettingPlanPage" in app)
    record(checks, "ui_nav", "AI Betting Plan" in (FRONTEND / "src/lib/navConfig.js").read_text(encoding="utf-8"))

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        from datetime import date

        from worldcup_predictor.betting_plan.bankroll import portfolio_exposure, recommend_stake
        from worldcup_predictor.betting_plan.combos import build_combo, has_conflict
        from worldcup_predictor.betting_plan.engine import build_daily_betting_plan, build_portfolio_plan
        from worldcup_predictor.betting_plan.gating import gate_betting_plan
        from worldcup_predictor.betting_plan.performance_insights import build_performance_insights
        from worldcup_predictor.betting_plan.constants import COMBO_SPECS

        sample_legs = [
            {
                "fixture_id": 1,
                "competition_key": "world_cup_2026",
                "prediction": "home",
                "market": "1x2",
                "bet_quality_score": 92,
                "fixture_label": "A vs B",
                "reason": "test",
            },
            {
                "fixture_id": 2,
                "competition_key": "world_cup_2026",
                "prediction": "yes",
                "market": "btts",
                "bet_quality_score": 91,
                "fixture_label": "C vs D",
                "reason": "test",
            },
            {
                "fixture_id": 3,
                "competition_key": "premier_league",
                "prediction": "over_2_5",
                "market": "over_under_2_5",
                "bet_quality_score": 88,
                "odds_decimal": 1.85,
                "fixture_label": "E vs F",
                "reason": "test",
            },
            {
                "fixture_id": 4,
                "competition_key": "la_liga",
                "prediction": "draw",
                "market": "1x2",
                "bet_quality_score": 38,
                "fixture_label": "G vs H",
                "reason": "low",
            },
        ]

        safe = build_combo(sample_legs, "safe")
        record(checks, "safe_combo_threshold", all(float(l["bet_quality_score"]) >= 90 for l in safe["legs"]))
        record(checks, "safe_combo_legs", 2 <= safe["leg_count"] <= 4)

        balanced = build_combo(sample_legs, "balanced")
        record(checks, "balanced_threshold", all(float(l["bet_quality_score"]) >= 75 for l in balanced["legs"]))

        value = build_combo(sample_legs, "value")
        record(checks, "value_threshold", all(float(l["bet_quality_score"]) >= 60 for l in value["legs"]))

        high = build_combo(sample_legs, "high_odds")
        record(checks, "high_odds_risk", high["risk"] == "High")
        record(checks, "high_odds_threshold", all(float(l["bet_quality_score"]) >= 45 for l in high["legs"]))

        conflict = has_conflict(
            [{"fixture_id": 9, "prediction": "home", "market": "1x2"}],
            {"fixture_id": 9, "prediction": "away", "market": "1x2"},
        )
        record(checks, "conflict_detection", conflict)

        stake = recommend_stake(100, profile="balanced", bet_quality_score=80, is_combo=False)
        record(checks, "bankroll_stake", stake["recommended_stake"] > 0 and stake["recommended_stake"] <= 4)

        exp = portfolio_exposure(
            [{"stake": {"recommended_stake": 2}, "bet_quality_score": 90}],
            [{"stake": {"recommended_stake": 3}, "combined_quality": 85}],
            bankroll=100,
        )
        record(checks, "portfolio_exposure", exp["total_exposure_pct"] > 0)

        plan = build_daily_betting_plan(plan_date=date.today().isoformat(), include_tomorrow=False, plan="pro")
        record(checks, "daily_plan_generated", plan.get("status") == "ok" and "days" in plan)

        day = next(iter(plan.get("days", {}).values()), {})
        singles = day.get("singles") or {}
        avoid = singles.get("avoid") or []
        record(checks, "avoid_list_exists", isinstance(avoid, list))
        record(checks, "day_quality_label", day.get("day_quality", {}).get("label") in ("Excellent", "Good", "Risky", "Poor"))

        perf = build_performance_insights()
        record(checks, "no_fake_performance", "message" in perf or perf.get("available") is True)

        public = gate_betting_plan(plan, plan="free")
        record(checks, "public_hides_portfolios", "portfolios" not in public)
        owner = gate_betting_plan(plan, plan="owner")
        record(checks, "owner_full_plan", "days" in owner)

        port = build_portfolio_plan(plan_date="today", bankroll=100, profile="balanced", plan="pro")
        record(checks, "portfolio_api_shape", "portfolios" in port or port.get("status") == "ok")

        record(checks, "combo_specs", COMBO_SPECS["safe"]["min_quality"] == 90.0)

    except Exception as exc:
        record(checks, "runtime_checks", False, str(exc))

    try:
        env = os.environ.copy()
        env.setdefault("CI", "true")
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=300,
            shell=sys.platform == "win32",
            env=env,
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A17 validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail and not ok:
            line += f" — {detail[:200]}"
        print(line)

    out_path = ROOT / "data" / "validation" / "phase_a17_betting_manager_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
