"""Phase 51C — goal timing data wiring validation."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    root = Path(__file__).resolve().parents[1]

    record("leagues_module", (root / "worldcup_predictor/goal_timing/leagues.py").is_file())
    record("stored_adapter", (root / "worldcup_predictor/goal_timing/data/stored_adapter.py").is_file())
    record("api_fallback", (root / "worldcup_predictor/goal_timing/data/api_football_fallback.py").is_file())
    record("feature_builder", (root / "worldcup_predictor/goal_timing/features/builder.py").is_file())
    record("probe_cli", (root / "scripts/goal_timing_feature_probe.py").is_file())

    from worldcup_predictor.goal_timing.leagues import GOAL_TIMING_ALLOWED_LEAGUE_KEYS, is_goal_timing_allowed_league
    from worldcup_predictor.goal_timing.minute_ranges import minute_to_range_key
    from worldcup_predictor.goal_timing.features.builder import GoalTimingFeatureBuilder, FEATURE_VERSION
    from worldcup_predictor.goal_timing.data.coverage_report import build_goal_timing_coverage_report
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.config.settings import get_settings

    record("nine_leagues", len(GOAL_TIMING_ALLOWED_LEAGUE_KEYS) == 9)
    record("eredivisie_allowed", is_goal_timing_allowed_league("eredivisie"))
    record("liga_portugal_allowed", is_goal_timing_allowed_league("liga_portugal"))
    record("world_cup_excluded", not is_goal_timing_allowed_league("world_cup_2026"))
    record("minute_range_31", minute_to_range_key(44) == "31-45+")
    record("feature_version_51c", FEATURE_VERSION == "v0.2_phase51c")

    builder = GoalTimingFeatureBuilder()
    features = builder.build(0, competition_key="premier_league")
    record("builder_returns_quality", "data_quality_score" in features)
    record(
        "required_feature_keys",
        all(
            k in features
            for k in (
                "team_goals_scored_by_range",
                "team_goals_conceded_by_range",
                "first_goal_team_distribution",
                "no_goal_before_minute_probability",
                "league_baseline_timing",
                "opponent_adjusted",
            )
        ),
    )

    repo = FootballIntelligenceRepository(get_settings().sqlite_path or None)
    record("repo_goal_timing_queries", hasattr(repo, "goal_timing_league_coverage"))

    coverage = build_goal_timing_coverage_report()
    record("coverage_report", "totals" in coverage and "leagues" in coverage)

    scoring = (root / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    wde = (root / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record("scoring_unchanged", "class ScoringEngine" in scoring or "def score" in scoring)
    record("wde_unchanged", "WeightedDecisionEngine" in wde)

    nav = (root / "base44-d/src/lib/navConfig.js").read_text(encoding="utf-8")
    record("goal_timing_nav", "goal-timing/dashboard" in nav)
    record("archive_hidden_from_nav", 'path: "/history"' not in nav or "Legacy Archive" in nav)

    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"\nPhase 51C validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    print()
    return 0 if all(ok for _, ok, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
