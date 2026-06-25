#!/usr/bin/env python3
"""Phase 47C production smoke tests."""

from __future__ import annotations

import json
import runpy
import sys
import urllib.error
import urllib.request
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _get(url: str) -> tuple[int, dict | str]:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body


def main() -> int:
    base = "http://127.0.0.1:8000"
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))

    code, health = _get(f"{base}/api/health")
    record("api_health", code == 200, str(health)[:60] if health else str(code))

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.prediction.consistency_engine import harmonize_prediction
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
        ScorelinePrediction,
    )

    settings = get_settings()
    record("rule_a_mode_active", settings.rule_a_gate_mode == "active", settings.rule_a_gate_mode)

    pred = MatchPrediction(
        fixture_id=99,
        competition_key="test",
        match_name="Smoke A vs B",
        one_x_two=MarketPrediction(market="1x2", selection="home_win", probability=0.55),
        over_under=MarketPrediction(market="over_under_2_5", selection="over_2_5", probability=0.5),
        scoreline=ScorelinePrediction(home_goals=1.0, away_goals=1.0),
        halftime=HalftimePrediction(estimated_total_goals=1.0),
        first_goal=FirstGoalPrediction(team="Smoke A"),
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
    out = harmonize_prediction(
        pred,
        home_team="Smoke A",
        away_team="Smoke B",
        wde_one_x_two="home_win",
        odds_available=False,
        conditional_1x2=True,
    )
    record(
        "rule_a_module",
        out.one_x_two.selection == "home_win"
        and out.metadata.get("harmonization_source") == "wde",
        out.metadata.get("harmonization_reason", ""),
    )

    code, _ = _get(f"{base}/api/performance/summary")
    record("performance_route", code == 200, str(code))

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"Smoke: {passed}/{len(checks)} PASS")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
