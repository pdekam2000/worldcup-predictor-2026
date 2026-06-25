"""Phase 32B — National team intelligence validation."""

from __future__ import annotations

import argparse
import json
import runpy
from dataclasses import replace
from pathlib import Path
from statistics import mean

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def _load_wc_fixture_ids(limit: int = 20) -> list[int]:
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository()
    rows = repo.list_upcoming_fixtures("world_cup_2026", season=2026, limit=limit)
    return [int(r["fixture_id"]) for r in rows[:limit]]


def _replay_fixture(fixture_id: int, *, national_enabled: bool) -> dict:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.backtesting.hybrid_replay import (
        CacheOnlyApiFootballClient,
        HybridReplayStats,
        build_hybrid_intelligence_report,
        _hybrid_offline_guard,
    )
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    import os
    from unittest.mock import patch

    os.environ["NATIONAL_TEAM_INTELLIGENCE_ENABLED"] = "true" if national_enabled else "false"
    get_settings.cache_clear()
    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    stats = HybridReplayStats()
    api_client = CacheOnlyApiFootballClient(settings, stats=stats)

    with patch("worldcup_predictor.config.settings.get_settings", return_value=settings), _hybrid_offline_guard(
        settings, stats
    ):
        try:
            report = build_hybrid_intelligence_report(
                fixture_id,
                repo=repo,
                api_client=api_client,
                settings=settings,
                stats=stats,
            )
        except ValueError as exc:
            return {"fixture_id": fixture_id, "error": str(exc)}

        context = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
        context.shared["intelligence_reports"] = {fixture_id: report}
        orch = SpecialistOrchestrator(context)
        orch_result = orch.run(fixture_id=fixture_id)
        specialist = orch_result.data if orch_result.success else None

        engine = ScoringEngine()
        prediction = engine.predict(report, specialist_report=specialist, use_weighted_decision=True)

        nat = (report.supplemental_sources or {}).get("national_team_intelligence") or {}
        bd = prediction.confidence_breakdown
        no_bet_60 = bool(prediction.no_bet_flag or float(prediction.confidence_score) < 60)
        return {
            "fixture_id": fixture_id,
            "match": prediction.match_name,
            "confidence": prediction.confidence_score,
            "no_bet": prediction.no_bet_flag,
            "no_bet_at_60": no_bet_60,
            "recommended": not no_bet_60,
            "breakdown": {
                "form": bd.form_score if bd else None,
                "h2h": bd.h2h_score if bd else None,
                "injuries": bd.injuries_score if bd else None,
                "lineups": bd.lineups_score if bd else None,
                "odds": bd.odds_score if bd else None,
                "dq": bd.data_quality_score if bd else None,
                "total": bd.total if bd else None,
            },
            "national": {
                "national_form_score": nat.get("national_form_score"),
                "national_h2h_score": nat.get("national_h2h_score"),
                "squad_strength_score": nat.get("squad_strength_score"),
                "injury_impact_score": nat.get("injury_impact_score"),
                "consensus_strength_score": nat.get("consensus_strength_score"),
                "data_coverage": nat.get("data_coverage"),
            },
            "api_calls_blocked": stats.live_fetch_attempts,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 32B national team intelligence.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--warm-cache", action="store_true", help="Fetch team/H2H cache via API (cache-first).")
    args = parser.parse_args()

    from worldcup_predictor.intelligence.national_team.consensus_engine import consensus_strength_score
    from worldcup_predictor.intelligence.national_team.form_engine import national_form_score, build_team_form_metrics
    from worldcup_predictor.intelligence.national_team.h2h_engine import national_h2h_score
    from worldcup_predictor.intelligence.national_team.injury_impact_engine import injury_impact_score
    from worldcup_predictor.intelligence.national_team.integration import verify_thresholds_unchanged
    from worldcup_predictor.intelligence.national_team.squad_strength_engine import squad_strength_score
    from worldcup_predictor.intelligence.national_team.data_resolver import warm_national_team_cache_for_fixture
    from worldcup_predictor.domain.intelligence import InjuryReport, MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.config.model_weights import DEFAULT_THRESHOLDS

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    sample_fixture = {
        "fixture": {"date": "2025-06-01T18:00:00+00:00", "venue": {"neutral": True}},
        "league": {"name": "World Cup Qualification UEFA", "id": 32},
        "teams": {"home": {"id": 10, "name": "Brazil"}, "away": {"id": 11, "name": "Argentina"}},
        "goals": {"home": 2, "away": 1},
    }
    hm = build_team_form_metrics(team_id=10, team_name="Brazil", recent_fixtures=[sample_fixture] * 6)
    am = build_team_form_metrics(team_id=11, team_name="Argentina", recent_fixtures=[sample_fixture] * 5)
    form_score, _ = national_form_score(home_metrics=hm, away_metrics=am)
    record("form_score_generated", form_score != 50.0, f"score={form_score}")

    h2h_score, _ = national_h2h_score([sample_fixture, sample_fixture], home_team_id=10, away_team_id=11)
    record("h2h_score_generated", h2h_score > 0, f"score={h2h_score}")

    report = MatchIntelligenceReport(
        fixture_id=1,
        fixture=None,
        home_team=TeamIntelligence(
            team_name="Brazil",
            injuries=InjuryReport(team_name="Brazil", team_id=10, players=[], available=True),
        ),
        away_team=TeamIntelligence(
            team_name="Argentina",
            injuries=InjuryReport(team_name="Argentina", team_id=11, players=[], available=True),
        ),
        lineups={"available": True, "items": [{"team": {"name": "Brazil"}, "startXI": [{}] * 11}]},
    )
    squad, _ = squad_strength_score(report)
    record("squad_score_generated", squad > 0, f"score={squad}")

    inj, _ = injury_impact_score(report)
    record("injury_score_generated", inj > 0, f"score={inj}")

    cons, _ = consensus_strength_score(report, None)
    record("consensus_score_generated", cons > 0, f"score={cons}")

    thresholds = verify_thresholds_unchanged()
    record("wde_confidence_min_60", thresholds.get("no_bet_confidence_minimum") == 60.0)
    record("wde_dq_min_50", thresholds.get("data_quality_no_bet_threshold") == 50.0)
    record("default_thresholds_unchanged", DEFAULT_THRESHOLDS["no_bet_confidence_minimum"] == 60.0)

    fixture_ids = _load_wc_fixture_ids(args.limit)
    record("wc_fixtures_loaded", len(fixture_ids) > 0, f"count={len(fixture_ids)}")

    warm_summary: list[dict] = []
    if args.warm_cache:
        from worldcup_predictor.config.settings import get_settings

        for fid in fixture_ids:
            warm_summary.append(warm_national_team_cache_for_fixture(fid, settings=get_settings()))

    before_rows = [_replay_fixture(fid, national_enabled=False) for fid in fixture_ids]
    after_rows = [_replay_fixture(fid, national_enabled=True) for fid in fixture_ids]

    before_conf = [r["confidence"] for r in before_rows if "confidence" in r]
    after_conf = [r["confidence"] for r in after_rows if "confidence" in r]
    record("confidence_comparison_generated", len(before_conf) == len(after_conf) and len(after_conf) > 0)

    def no_bet_rate(rows: list[dict]) -> float:
        valid = [r for r in rows if "no_bet" in r]
        if not valid:
            return 1.0
        return sum(1 for r in valid if r["no_bet"]) / len(valid)

    def rec_rate(rows: list[dict]) -> float:
        valid = [r for r in rows if "recommended" in r]
        if not valid:
            return 0.0
        return sum(1 for r in valid if r["recommended"]) / len(valid)

    comparison = {
        "fixtures": len(fixture_ids),
        "before": {
            "avg_confidence": round(mean(before_conf), 2) if before_conf else None,
            "max_confidence": round(max(before_conf), 2) if before_conf else None,
            "no_bet_rate": round(no_bet_rate(before_rows), 3),
            "recommendation_rate": round(rec_rate(before_rows), 3),
        },
        "after": {
            "avg_confidence": round(mean(after_conf), 2) if after_conf else None,
            "max_confidence": round(max(after_conf), 2) if after_conf else None,
            "no_bet_rate": round(no_bet_rate(after_rows), 3),
            "recommendation_rate": round(rec_rate(after_rows), 3),
        },
        "per_fixture": [
            {
                "fixture_id": b.get("fixture_id"),
                "match": b.get("match"),
                "before": {
                    "confidence": b.get("confidence"),
                    "breakdown": b.get("breakdown"),
                    "no_bet": b.get("no_bet"),
                },
                "after": {
                    "confidence": a.get("confidence"),
                    "breakdown": a.get("breakdown"),
                    "national": a.get("national"),
                    "no_bet": a.get("no_bet"),
                },
            }
            for b, a in zip(before_rows, after_rows)
        ],
        "warm_cache": warm_summary if args.warm_cache else None,
    }

    exceeds_60 = sum(1 for c in after_conf if c >= 60)
    record("any_confidence_exceeds_60", exceeds_60 > 0, f"{exceeds_60}/{len(after_conf)} fixtures >= 60")
    record("wde_integration_active", any(r.get("national") for r in after_rows))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print("PHASE 32B — National Team Intelligence Validation")
    print("=" * 58)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    print("-" * 58)
    print(f"Before avg/max conf: {comparison['before']['avg_confidence']}/{comparison['before']['max_confidence']}")
    print(f"After  avg/max conf: {comparison['after']['avg_confidence']}/{comparison['after']['max_confidence']}")
    print(f"No Bet rate before/after: {comparison['before']['no_bet_rate']} -> {comparison['after']['no_bet_rate']}")
    print(f"Recommendation rate before/after: {comparison['before']['recommendation_rate']} -> {comparison['after']['recommendation_rate']}")
    print(f"Fixtures >= 60 after: {exceeds_60}/{len(after_conf)}")
    print("-" * 58)
    print(f"Result: {passed}/{total} checks passed")

    out = Path("artifacts/phase32b_national_team_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": checks, "comparison": comparison}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
