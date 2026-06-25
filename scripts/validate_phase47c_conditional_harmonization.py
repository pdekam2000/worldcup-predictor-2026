#!/usr/bin/env python3
"""Phase 47C — conditional harmonization (Rule A) validation."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

REPLAY = Path("data/shadow/phase18_harmonization_replay.jsonl")
EXPECTED_RULE_A = 0.3671497584541063
EXPECTED_WDE = 0.34782608695652173
EXPECTED_CURRENT = 0.2995169082125604
TOLERANCE = 0.002


def _report(checks: list[tuple[str, bool, str]]) -> int:
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    out = Path("artifacts/phase47c_conditional_harmonization_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "phase": "47C",
                "passed": passed,
                "total": total,
                "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Phase 47C validation: {passed}/{total} PASS")
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    return 0 if passed == total else 1


def _load_replay() -> list[dict]:
    if not REPLAY.exists():
        return []
    return [
        json.loads(line)
        for line in REPLAY.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _replay_accuracy(rows: list[dict], pick_fn) -> float:
    return sum(1 for r in rows if pick_fn(r) == r["actual"]) / max(len(rows), 1)


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
        ScorelinePrediction,
    )
    from worldcup_predictor.prediction.consistency_engine import harmonize_prediction, is_consistent
    from worldcup_predictor.prediction.rule_a_gate.policy import resolve_rule_a_1x2

    # Policy unit checks
    pick, used, src, reason = resolve_rule_a_1x2(
        wde_selection="home_win",
        scoreline_implied="draw",
        odds_available=False,
        conditional_enabled=True,
    )
    record("rule_a_keeps_wde_without_odds", pick == "home_win" and not used and src == "wde")

    pick2, used2, src2, _ = resolve_rule_a_1x2(
        wde_selection="home_win",
        scoreline_implied="draw",
        odds_available=True,
        conditional_enabled=True,
    )
    record("rule_a_scoreline_with_odds", pick2 == "draw" and used2 and src2 == "scoreline")

    base = MatchPrediction(
        fixture_id=1,
        competition_key="test",
        match_name="A vs B",
        one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.55),
        over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=0.5),
        scoreline=ScorelinePrediction(home_goals=1.0, away_goals=1.0),
        halftime=HalftimePrediction(estimated_total_goals=1.2),
        first_goal=FirstGoalPrediction(team="A"),
        confidence_score=55.0,
        confidence_level=ConfidenceLevel.MEDIUM,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=50.0,
            h2h_score=50.0,
            injuries_score=50.0,
            lineups_score=50.0,
            odds_score=50.0,
            data_quality_score=50.0,
            total=55.0,
        ),
        risk_level="medium",
    )

    rule_a_pred = harmonize_prediction(
        base,
        home_team="A",
        away_team="B",
        wde_one_x_two="home_win",
        odds_available=False,
        conditional_1x2=True,
    )
    record(
        "harmonize_rule_a_1x2_preserved",
        rule_a_pred.one_x_two.selection == "home_win",
        rule_a_pred.one_x_two.selection,
    )
    record(
        "harmonize_ou_still_applied",
        rule_a_pred.over_under.selection == "under_2_5",
        rule_a_pred.over_under.selection,
    )
    record(
        "telemetry_fields_present",
        all(
            rule_a_pred.metadata.get(k)
            for k in ("harmonization_used", "harmonization_reason", "harmonization_source")
        ),
        str(rule_a_pred.metadata.get("harmonization_reason")),
    )
    record(
        "ou_consistent_when_1x2_skipped",
        is_consistent(rule_a_pred, require_1x2_match=False),
    )

    unconditional = harmonize_prediction(
        base,
        home_team="A",
        away_team="B",
        conditional_1x2=False,
    )
    record(
        "unconditional_still_forces_draw",
        unconditional.one_x_two.selection == "draw",
    )

    rows = _load_replay()
    record("replay_dataset_loaded", len(rows) >= 200, str(len(rows)))

    if rows:
        acc_current = _replay_accuracy(rows, lambda r: r["final"])
        acc_wde = _replay_accuracy(rows, lambda r: r["wde"])
        acc_rule_a = _replay_accuracy(
            rows,
            lambda r: r["scoreline"] if r.get("has_odds") else r["wde"],
        )

        record(
            "replay_current_accuracy",
            abs(acc_current - EXPECTED_CURRENT) <= TOLERANCE,
            f"{acc_current:.1%}",
        )
        record(
            "replay_wde_accuracy",
            abs(acc_wde - EXPECTED_WDE) <= TOLERANCE,
            f"{acc_wde:.1%}",
        )
        record(
            "replay_rule_a_accuracy",
            abs(acc_rule_a - EXPECTED_RULE_A) <= TOLERANCE,
            f"{acc_rule_a:.1%}",
        )

        conflicts = [r for r in rows if r["wde"] != r["scoreline"]]
        old_overrides = len(conflicts)
        new_overrides = sum(
            1
            for r in conflicts
            if r.get("has_odds") and r["scoreline"] != r["wde"]
        )
        harmful_before = sum(
            1 for r in conflicts if r.get("override_outcome") == "harmful"
        )
        harmful_after = sum(
            1
            for r in conflicts
            if r.get("override_outcome") == "harmful" and r.get("has_odds")
        )
        beneficial = sum(
            1 for r in conflicts if r.get("override_outcome") == "helpful"
        )
        beneficial_odds_n = sum(
            1
            for r in conflicts
            if r.get("override_outcome") == "helpful" and r.get("has_odds")
        )

        record(
            "override_rate_reduced",
            new_overrides < old_overrides,
            f"before={old_overrides/len(rows):.1%} after~={new_overrides/len(rows):.1%}",
        )
        record(
            "harmful_overrides_reduced",
            harmful_after < harmful_before,
            f"before={harmful_before} after={harmful_after}",
        )
        record(
            "beneficial_odds_cohort_preserved",
            beneficial_odds_n == 5,
            f"odds_helpful={beneficial_odds_n}/5 total_helpful={beneficial}",
        )

    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()
    record("default_rule_a_mode_active", get_settings().rule_a_gate_mode == "active")

    return _report(checks)


if __name__ == "__main__":
    raise SystemExit(main())
