"""Phase 42B-FIX final pre-deploy cross-market consistency audit."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


AUDITED_RELATIONSHIPS = [
    ("A", "1X2 vs Double Chance", "DOUBLE_CHANCE_1X2"),
    ("B", "1X2 vs Correct Score", "CORRECT_SCORE_1X2"),
    ("C", "BTTS vs Correct Score", "BTTS_CORRECT_SCORE"),
    ("D", "BTTS vs Goalscorer", "BTTS_GOALSCORER"),
    ("E", "Over/Under vs Goal Timing", "OU_GOAL_TIMING"),
    ("F", "First Team To Score vs Clean Sheet", "N/A_DISPLAY"),
    ("G", "Half Time vs Full Time Result", "INFORMATIONAL_ONLY"),
    ("H", "Expected Minute vs Minute Range", "TIMING_RANGE_CONSISTENCY"),
    ("I", "Team scores vs team does not score", "BTTS_GOALSCORER+OU_SCORE"),
    ("J", "Over/Under vs Correct Score total goals", "OU_CORRECT_SCORE_CONSISTENCY"),
    ("K", "0-0 Correct Score vs First Team To Score", "FIRST_GOAL_SCORELESS_CONSISTENCY"),
]


def _report(title: str, checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\n{title}: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()
    return 0 if passed == len(checks) else 1


def _run_script(name: str) -> tuple[bool, str]:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / name
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    tail = output.strip().splitlines()[-1] if output.strip() else f"exit={proc.returncode}"
    return proc.returncode == 0, tail


def _payload(**kwargs) -> dict:
    base = {
        "status": "ok",
        "home_team": "Germany",
        "away_team": "France",
        "detailed_markets": {
            "match_winner": {
                "selection": "home_win",
                "probabilities": {"home_win": 60.0, "draw": 22.0, "away_win": 18.0},
            },
            "over_under_25": {
                "selection": "under_2_5",
                "probability": 0.82,
                "probabilities": {"over_2_5": 18.0, "under_2_5": 82.0},
            },
            "btts": {
                "selection": "no",
                "probability": 0.75,
                "probabilities": {"yes": 25.0, "no": 75.0},
            },
            "first_goal": {"team": "Germany", "minute_range": "31-45", "expected_minute": 38},
            "goalscorer": {"available": True, "player": "M", "team": "France", "confidence": 0.4},
            "double_chance": {"home_or_draw": 82.0, "home_or_away": 78.0, "draw_or_away": 40.0},
            "correct_scores": [{"label": "2-1", "probability": 14.0}],
            "halftime": {
                "probabilities": {"home_win": 35.0, "draw": 40.0, "away_win": 25.0},
            },
        },
        "sportmonks_xg": {"home_xg": 1.5, "away_xg": 0.2},
    }
    base.update(kwargs)
    return base


def main() -> int:
    checks: list[tuple[str, bool, str]] = []
    root = Path(__file__).resolve().parents[1]
    guard_path = root / "worldcup_predictor/prediction/market_consistency_guard.py"
    guard_src = guard_path.read_text(encoding="utf-8")

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    for code, label, rule in AUDITED_RELATIONSHIPS:
        if rule == "N/A_DISPLAY":
            record(f"audit_{code}_{label.replace(' ', '_').lower()}", True, "clean sheet not displayed in Prediction Detail")
            continue
        if rule == "INFORMATIONAL_ONLY":
            record(f"audit_{code}_{label.replace(' ', '_').lower()}", True, "HT/FT shown as probabilities only; no hard pick conflict")
            continue
        present = False
        if rule == "DOUBLE_CHANCE_1X2":
            present = "Double Chance leader" in guard_src
        elif rule == "CORRECT_SCORE_1X2":
            present = "1X2 leader" in guard_src and "Correct score" in guard_src
        elif rule == "BTTS_CORRECT_SCORE":
            present = "BTTS No is" in guard_src and "correct score" in guard_src
        elif rule == "BTTS_GOALSCORER":
            present = "goalscorer" in guard_src and "CONSISTENCY_BTTS_NO_THRESHOLD" in guard_src
        elif rule == "OU_GOAL_TIMING":
            present = "Under 2.5 is" in guard_src and "goal timing" in guard_src
        elif rule == "BTTS_GOALSCORER+OU_SCORE":
            present = "CONSISTENCY_BTTS_NO_THRESHOLD" in guard_src and "OU_CORRECT_SCORE_CONSISTENCY" in guard_src
        else:
            present = rule in guard_src
        record(f"audit_{code}_rule_present", present, rule)

    from worldcup_predictor.prediction.market_consistency_guard import apply_market_consistency_guard

    # J — Under high + 3-goal score withheld
    p_ou = _payload()
    p_ou["detailed_markets"]["correct_scores"] = [{"label": "2-1", "probability": 20.0}]
    out_ou = apply_market_consistency_guard(p_ou)
    cs_ou = out_ou["detailed_markets"]["correct_scores"][0]
    record(
        "ou_under_vs_3_goal_score_withheld",
        cs_ou.get("display_allowed") is False,
        cs_ou.get("withheld_reason", "")[:70],
    )

    # K — 0-0 vs first team to score (use draw-led 1X2 so 0-0 survives rule 3)
    p_fg = _payload()
    p_fg["detailed_markets"]["match_winner"] = {
        "selection": "draw",
        "probabilities": {"home_win": 20.0, "draw": 55.0, "away_win": 25.0},
    }
    p_fg["detailed_markets"]["correct_scores"] = [{"label": "0-0", "probability": 12.0}]
    p_fg["detailed_markets"]["over_under_25"] = {
        "selection": "under_2_5",
        "probability": 0.55,
        "probabilities": {"over_2_5": 45.0, "under_2_5": 55.0},
    }
    out_fg = apply_market_consistency_guard(p_fg)
    fg_block = out_fg["detailed_markets"]["first_goal"]
    record(
        "zero_zero_vs_first_goal_withheld",
        fg_block.get("display_allowed") is False,
        fg_block.get("consistency_status", ""),
    )

    # Consistent bundle passes guard
    p_ok = _payload()
    p_ok["detailed_markets"]["over_under_25"] = {
        "selection": "over_2_5",
        "probability": 0.58,
        "probabilities": {"over_2_5": 58.0, "under_2_5": 42.0},
    }
    p_ok["detailed_markets"]["btts"] = {
        "selection": "yes",
        "probability": 0.58,
        "probabilities": {"yes": 58.0, "no": 42.0},
    }
    p_ok["detailed_markets"]["goalscorer"] = {
        "available": True,
        "player": "Havertz",
        "team": "Germany",
        "confidence": 0.78,
    }
    p_ok["detailed_markets"]["correct_scores"] = [{"label": "2-1", "probability": 11.0}]
    out_ok = apply_market_consistency_guard(p_ok)
    record(
        "consistent_bundle_no_withheld_markets",
        len(out_ok["consistency_guard"].get("withheld_markets", [])) == 0,
    )

    record("display_helpers_wired", "apply_market_consistency_guard" in (root / "worldcup_predictor/api/display_helpers.py").read_text(encoding="utf-8"))
    record("prediction_detail_respects_display_allowed", "display_allowed" in (root / "base44-d/src/pages/PredictionDetail.jsx").read_text(encoding="utf-8"))

    audit_failed = _report("Phase 42B final consistency audit", checks)

    suite_failed = 0
    for script in (
        "validate_phase42b_global_market_consistency_guard.py",
        "validate_phase42b_consistency_guard_config_hardening.py",
        "validate_bugfix_timing_range_consistency.py",
    ):
        ok, tail = _run_script(script)
        print(f"Suite {script}: {'PASS' if ok else 'FAIL'} — {tail}")
        if not ok:
            suite_failed += 1

    deploy_ready = audit_failed == 0 and suite_failed == 0
    print(f"DEPLOY_READY={'YES' if deploy_ready else 'NO'}")
    return 0 if deploy_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
