"""Phase 32E — Reality calibration validation."""

from __future__ import annotations

import argparse
import json
import os
import runpy
from pathlib import Path
from statistics import mean, pstdev
from unittest.mock import patch

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
            "report": report,
        }


def _summarize(rows: list[dict]) -> dict:
    conf = [r["confidence"] for r in rows if "confidence" in r]
    valid = [r for r in rows if "no_bet" in r]
    rec = [r for r in rows if "recommended" in r]
    return {
        "fixtures": len(rows),
        "avg_confidence": round(mean(conf), 2) if conf else None,
        "max_confidence": round(max(conf), 2) if conf else None,
        "no_bet_rate": round(sum(1 for r in valid if r["no_bet"]) / len(valid), 3) if valid else 1.0,
        "recommendation_rate": round(sum(1 for r in rec if r["recommended"]) / len(rec), 3) if rec else 0.0,
        "fixtures_gte_60": sum(1 for c in conf if c >= 60),
        "fixtures_gte_70": sum(1 for c in conf if c >= 70),
    }


def _audit_leakage(rows: list[dict]) -> dict:
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
    from worldcup_predictor.intelligence.national_team.data_resolver import resolve_match_history
    from worldcup_predictor.intelligence.national_team.history_filters import count_history_violations
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository()
    total_future = total_circular = 0
    for row in rows:
        report = row.get("report")
        if report is None:
            continue
        hist = resolve_match_history(report, repo=repo)
        kick = None
        from worldcup_predictor.intelligence.national_team.history_filters import history_filter_context

        kick, fid = history_filter_context(report, repo=repo)
        for key in ("home_recent_fixtures", "away_recent_fixtures", "h2h_meetings"):
            v = count_history_violations(
                hist.get(key),
                before_kickoff=kick,
                exclude_fixture_id=fid,
            )
            total_future += v["future_leaks"]
            total_circular += v["circular_refs"]
    return {
        "future_leaks": total_future,
        "circular_refs": total_circular,
        "fixtures_audited": len(rows),
    }


def _consensus_distribution(rows: list[dict]) -> dict:
    vals = [
        float((r.get("national") or {}).get("consensus_strength_score"))
        for r in rows
        if (r.get("national") or {}).get("consensus_strength_score") is not None
    ]
    if not vals:
        return {"count": 0}
    at_95 = sum(1 for v in vals if v >= 94.5)
    return {
        "count": len(vals),
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
        "avg": round(mean(vals), 2),
        "stdev": round(pstdev(vals), 2) if len(vals) > 1 else 0.0,
        "at_or_above_95": at_95,
        "saturation_rate": round(at_95 / len(vals), 3),
    }


def _injury_distribution(rows: list[dict]) -> dict:
    vals = [
        float((r.get("national") or {}).get("injury_impact_score"))
        for r in rows
        if (r.get("national") or {}).get("injury_impact_score") is not None
    ]
    if not vals:
        return {"count": 0}
    at_95 = sum(1 for v in vals if v >= 94.5)
    return {
        "count": len(vals),
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
        "avg": round(mean(vals), 2),
        "at_or_above_95": at_95,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 32E reality calibration.")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    fixture_ids = _load_wc_fixture_ids(args.limit)
    record("wc_fixtures_loaded", len(fixture_ids) > 0, f"count={len(fixture_ids)}")

    rows_32b = [_replay_fixture(fid, national_enabled=False) for fid in fixture_ids]
    rows_32e = [_replay_fixture(fid, national_enabled=True) for fid in fixture_ids]

    leakage = _audit_leakage(rows_32e)
    record("no_future_leakage", leakage["future_leaks"] == 0, f"future={leakage['future_leaks']}")
    record("no_circular_history", leakage["circular_refs"] == 0, f"circular={leakage['circular_refs']}")

    cons_dist = _consensus_distribution(rows_32e)
    record(
        "no_consensus_saturation",
        cons_dist.get("at_or_above_95", 99) == 0 and cons_dist.get("max", 100) <= 93,
        f"max={cons_dist.get('max')}, at_95={cons_dist.get('at_or_above_95')}, stdev={cons_dist.get('stdev')}",
    )
    record(
        "consensus_distribution_spread",
        cons_dist.get("stdev", 0) >= 1.0,
        f"min={cons_dist.get('min')} max={cons_dist.get('max')} avg={cons_dist.get('avg')}",
    )

    inj_dist = _injury_distribution(rows_32e)
    record(
        "no_injury_inflation",
        inj_dist.get("at_or_above_95", 99) == 0 and inj_dist.get("max", 100) <= 72,
        f"max={inj_dist.get('max')} avg={inj_dist.get('avg')}",
    )

    s32b = _summarize(rows_32b)
    s32e = _summarize(rows_32e)

    phase32c_path = Path("artifacts/phase32c_national_history_validation.json")
    s32c = None
    if phase32c_path.exists():
        s32c = json.loads(phase32c_path.read_text(encoding="utf-8")).get("comparison", {}).get("after_32c")

    record("confidence_comparison_generated", s32e["avg_confidence"] is not None)
    record(
        "32e_lower_than_32c",
        s32c is not None and s32e["avg_confidence"] < float(s32c.get("avg_confidence") or 999),
        f"32e={s32e['avg_confidence']} vs 32c={s32c.get('avg_confidence') if s32c else 'n/a'}",
    )
    record(
        "32e_higher_than_32b_intel_off",
        s32e["avg_confidence"] > s32b["avg_confidence"],
        f"32e={s32e['avg_confidence']} vs 32b_off={s32b['avg_confidence']}",
    )
    record(
        "32e_avg_in_target_band",
        65 <= (s32e["avg_confidence"] or 0) <= 72,
        f"avg={s32e['avg_confidence']} target 65-72",
    )

    comparison = {
        "fixtures": len(fixture_ids),
        "after_32b_intel_off": s32b,
        "after_32c": s32c,
        "after_32e": s32e,
        "leakage_audit": leakage,
        "consensus_distribution": cons_dist,
        "injury_distribution": inj_dist,
        "per_fixture_32e": [
            {
                "fixture_id": r.get("fixture_id"),
                "match": r.get("match"),
                "confidence": r.get("confidence"),
                "national": r.get("national"),
                "breakdown": r.get("breakdown"),
                "recommended": r.get("recommended"),
            }
            for r in rows_32e
        ],
    }

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print("PHASE 32E — Reality Calibration Validation")
    print("=" * 58)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    print("-" * 58)
    print(f"32B (intel off) avg/max: {s32b['avg_confidence']}/{s32b['max_confidence']}")
    if s32c:
        print(f"32C avg/max: {s32c.get('avg_confidence')}/{s32c.get('max_confidence')}")
    print(f"32E avg/max: {s32e['avg_confidence']}/{s32e['max_confidence']}")
    print(f"32E rec rate: {s32e['recommendation_rate']} | >=60: {s32e['fixtures_gte_60']}/{len(fixture_ids)}")
    print(f"Consensus dist: {cons_dist}")
    print(f"Injury dist: {inj_dist}")
    print("-" * 58)
    print(f"Result: {passed}/{total} checks passed")

    out = Path("artifacts/phase32e_reality_calibration_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": checks, "comparison": comparison}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
