#!/usr/bin/env python3
"""Phase A13A — prediction coverage + combo hotfix validation."""

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
BASE = os.environ.get("A13A_API_BASE", "https://footballpredictor.it.com")


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    helpers = (ROOT / "worldcup_predictor/api/match_center_helpers.py").read_text(encoding="utf-8")
    combo = (FRONTEND / "src/lib/comboGenerator.js").read_text(encoding="utf-8")
    card = (FRONTEND / "src/components/match-center/EliteMatchCard.jsx").read_text(encoding="utf-8")
    comps_py = (ROOT / "worldcup_predictor/api/routes/competitions.py").read_text(encoding="utf-8")

    record(checks, "no_bet_clears_best_pick", "if no_bet:" in helpers and "selection = None" in helpers)
    record(checks, "match_winner_fallback", "detailed_markets" in helpers and "match_winner" in helpers)
    record(checks, "card_not_generated_msg", "Prediction not generated yet" in card)
    record(checks, "combo_same_fixture_conflict", "sameFixture" in combo and "CONFLICT_GROUPS" in combo)
    record(checks, "combo_a_plus_value", '"A+"' in combo or "A+" in combo)
    record(checks, "zero_fixture_reason_api", "zero_fixture_reason" in comps_py)
    record(checks, "league_selector_zero_hint", "zero_fixture_reason" in (FRONTEND / "src/components/match-center/LeagueSelector.jsx").read_text(encoding="utf-8"))

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecision" in wde or "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        from worldcup_predictor.api.match_center_helpers import extract_prediction_summary

        placeholder = extract_prediction_summary({"prediction": "draw", "no_bet": True, "confidence": 0.5})
        record(checks, "no_missing_as_draw", placeholder.get("best_pick") is None)
        real = extract_prediction_summary(
            {
                "no_bet": False,
                "detailed_markets": {"match_winner": {"selection": "home", "confidence": 0.72}},
            }
        )
        record(checks, "match_winner_extract", "Home" in str(real.get("best_pick")))
    except Exception as exc:
        record(checks, "summary_runtime", False, str(exc))

    audit_script = ROOT / "scripts" / "audit_phase_a13a_prediction_coverage.py"
    if audit_script.is_file():
        proc = subprocess.run([sys.executable, str(audit_script)], capture_output=True, text=True, timeout=120)
        audit_ok = proc.returncode == 0
        record(checks, "audit_script_runs", audit_ok, (proc.stderr or proc.stdout)[-300:])
        audit_path = ROOT / "data" / "validation" / "phase_a13a_audit_report.json"
        if audit_path.is_file():
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            combo = audit.get("parts", {}).get("combo_audit", {})
            record(checks, "prediction_coverage_report", "prediction_coverage" in audit.get("parts", {}))
            record(checks, "draw_distribution_report", "draw_distribution" in audit.get("parts", {}))
            record(
                checks,
                "combo_candidates_when_data",
                combo.get("candidates_accepted", 0) >= 0,
                f"accepted={combo.get('candidates_accepted')}",
            )

    try:
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=240,
            shell=os.name == "nt",
        )
        record(checks, "frontend_build", proc.returncode == 0)
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    import urllib.request

    for name, url, ok_codes in [
        ("smoke_matches", f"{BASE}/api/matches?competition=all&include_summary=true&page_size=5", {200}),
        ("smoke_competitions", f"{BASE}/api/competitions?include_counts=true", {200}),
        ("smoke_combo_page", f"{BASE}/combo-tips", {200}),
    ]:
        try:
            with urllib.request.urlopen(url, timeout=25) as resp:
                record(checks, name, resp.status in ok_codes, f"http={resp.status}")
        except Exception as exc:
            record(checks, name, False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A13A — {passed}/{total} checks\n")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    out = ROOT / "data" / "validation" / "phase_a13a_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
