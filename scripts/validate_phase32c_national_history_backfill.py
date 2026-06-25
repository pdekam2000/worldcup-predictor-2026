"""Phase 32C — National team history backfill validation."""

from __future__ import annotations

import argparse
import json
import os
import runpy
from pathlib import Path
from statistics import mean
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
            return {"fixture_id": fixture_id, "error": str(exc), "api_calls_blocked": stats.live_fetch_attempts}

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
            "api_calls_blocked": stats.live_fetch_attempts + stats.http_calls,
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


def _contribution_analysis(rows: list[dict]) -> dict:
    factors = {
        "national_form": [],
        "national_h2h": [],
        "squad_strength": [],
        "injury_impact": [],
        "consensus_strength": [],
    }
    for r in rows:
        nat = r.get("national") or {}
        for key, col in (
            ("national_form", "national_form_score"),
            ("national_h2h", "national_h2h_score"),
            ("squad_strength", "squad_strength_score"),
            ("injury_impact", "injury_impact_score"),
            ("consensus_strength", "consensus_strength_score"),
        ):
            val = nat.get(col)
            if val is not None:
                factors[key].append(float(val))

    summary = {}
    for key, vals in factors.items():
        if vals:
            summary[key] = {
                "avg": round(mean(vals), 2),
                "max": round(max(vals), 2),
                "non_neutral_pct": round(sum(1 for v in vals if abs(v - 50) > 2) / len(vals), 3),
                "count": len(vals),
            }
        else:
            summary[key] = {"avg": None, "max": None, "non_neutral_pct": 0, "count": 0}

    ranked = sorted(
        [(k, v["avg"]) for k, v in summary.items() if v["avg"] is not None],
        key=lambda x: abs((x[1] or 50) - 50),
        reverse=True,
    )
    return {"factors": summary, "top_contributor": ranked[0][0] if ranked else None}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 32C national history backfill.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--skip-backfill", action="store_true")
    args = parser.parse_args()

    from worldcup_predictor.intelligence.national_team.history_backfill import run_phase32c

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    backfill_result = None if args.skip_backfill else run_phase32c(fixture_limit=args.limit)

    if backfill_result:
        audit_after = backfill_result["audit_after"]
        record(
            "team_ids_resolved",
            audit_after["missing_count"] == 0,
            f"resolved={audit_after['resolved_count']}/{audit_after['fixtures_audited']}",
        )
        record(
            "form_cache_created",
            backfill_result["form_cache"]["teams_built"] > 0,
            f"teams={backfill_result['form_cache']['teams_built']}",
        )
        record(
            "h2h_cache_created",
            backfill_result["h2h_cache"]["pairs_built"] > 0,
            f"pairs={backfill_result['h2h_cache']['pairs_built']}",
        )
        hit = backfill_result["cache_hit_rate"]
        record(
            "cache_hit_rate_measured",
            hit.get("target_met_90pct") or hit.get("form_fixture_hit_rate", 0) >= 0.9,
            f"form+fixture={hit.get('form_fixture_hit_rate', 0):.1%}, overall={hit.get('overall_hit_rate', 0):.1%}",
        )
        record("no_external_api_on_backfill", backfill_result["validation"]["external_api_calls"] == 0)

    fixture_ids = _load_wc_fixture_ids(args.limit)
    before_32b_rows = [_replay_fixture(fid, national_enabled=False) for fid in fixture_ids]
    after_32c_rows = [_replay_fixture(fid, national_enabled=True) for fid in fixture_ids]

    api_calls = sum(r.get("api_calls_blocked", 0) for r in after_32c_rows)
    replay_ok = sum(1 for r in after_32c_rows if "confidence" in r)
    record(
        "no_external_api_on_replay",
        replay_ok == len(fixture_ids),
        f"replayed={replay_ok}/{len(fixture_ids)}, guard_blocked={api_calls}",
    )

    before_32b = _summarize(before_32b_rows)
    after_32c = _summarize(after_32c_rows)

    phase32b_path = Path("artifacts/phase32b_national_team_validation.json")
    after_32b = None
    if phase32b_path.exists():
        phase32b = json.loads(phase32b_path.read_text(encoding="utf-8"))
        after_32b = phase32b.get("comparison", {}).get("after")

    record("confidence_comparison_generated", before_32b["avg_confidence"] is not None)
    record(
        "form_scores_populated",
        sum(1 for r in after_32c_rows if (r.get("national") or {}).get("national_form_score") not in (None, 50.0)) > 0,
    )
    record(
        "h2h_scores_populated",
        sum(1 for r in after_32c_rows if (r.get("national") or {}).get("national_h2h_score") not in (None, 50.0)) > 0,
    )

    contribution = _contribution_analysis(after_32c_rows)

    comparison = {
        "fixtures": len(fixture_ids),
        "before_32b": before_32b,
        "after_32b": after_32b,
        "after_32c": after_32c,
        "delta_32c_vs_32b": None,
        "contribution_analysis": contribution,
        "per_fixture": [
            {
                "fixture_id": r.get("fixture_id"),
                "match": r.get("match"),
                "after_32c": {
                    "confidence": r.get("confidence"),
                    "national": r.get("national"),
                    "no_bet": r.get("no_bet"),
                },
            }
            for r in after_32c_rows
        ],
    }
    if after_32b and after_32b.get("avg_confidence") is not None:
        comparison["delta_32c_vs_32b"] = {
            "avg_confidence": round(after_32c["avg_confidence"] - after_32b["avg_confidence"], 2),
            "recommendation_rate": round(after_32c["recommendation_rate"] - after_32b["recommendation_rate"], 3),
            "fixtures_gte_60": after_32c["fixtures_gte_60"] - after_32b.get("fixtures_gte_60", 0),
        }

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print("PHASE 32C — National Team History Backfill Validation")
    print("=" * 58)
    for name, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  [{mark}] {name}{suffix}")
    print("-" * 58)
    print(f"Before 32B avg/max: {before_32b['avg_confidence']}/{before_32b['max_confidence']}")
    if after_32b:
        print(f"After  32B avg/max: {after_32b.get('avg_confidence')}/{after_32b.get('max_confidence')}")
    print(f"After  32C avg/max: {after_32c['avg_confidence']}/{after_32c['max_confidence']}")
    print(f"Rec rate 32C: {after_32c['recommendation_rate']} | >=60: {after_32c['fixtures_gte_60']}/{len(fixture_ids)} | >=70: {after_32c['fixtures_gte_70']}")
    print(f"Top contributor: {contribution.get('top_contributor')}")
    print("-" * 58)
    print(f"Result: {passed}/{total} checks passed")

    out = Path("artifacts/phase32c_national_history_validation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "passed": passed,
                "total": total,
                "checks": checks,
                "backfill": backfill_result,
                "comparison": comparison,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
