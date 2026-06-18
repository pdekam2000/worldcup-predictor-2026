from __future__ import annotations

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().with_name('bootstrap_path.py')))

import sys
import tempfile
from pathlib import Path


def _temp_repo():
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    path = Path(tempfile.mkstemp(suffix=".db")[1])
    return FootballIntelligenceRepository(str(path)), path


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.competition.competition_service import CompetitionService
        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.intelligence.league_context_engine import build_league_context
        from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
        from worldcup_predictor.prediction.extended_markets import load_extended_markets_from_prediction
        from worldcup_predictor.prediction.scoring_engine import ScoringEngine
        from worldcup_predictor.schedule.competition_schedule import create_schedule_service

        svc = CompetitionService()
        checks.append(("european_leagues", len(svc.list_european_leagues()) == 8))
        checks.append(("default_season_pl", svc.get_default_season("premier_league") == 2025))

        schedule = create_schedule_service(Settings(), competition_key="premier_league", season=2024)
        checks.append(("schedule_with_season", schedule is not None))

        repo, _db_path = _temp_repo()
        ctx = build_league_context(
            repo,
            competition_key="premier_league",
            home_team="Arsenal",
            away_team="Chelsea",
            season=2023,
        )
        checks.append(("league_context_shape", "data_gaps" in ctx))

        adjusted = ScoringEngine._apply_league_context_goals(
            2.5,
            {"league_tendencies": {"avg_total_goals": 3.0, "over_2_5_rate": 0.6}},
        )
        checks.append(("league_goals_adjust", adjusted > 2.5))

        wc = PredictPipeline(Settings(), locale="en", competition_key="world_cup_2026").run(
            1489374, record_history=False
        )
        checks.append(("world_cup_predict", wc.success))

        import inspect

        sig = inspect.signature(PredictPipeline.run)
        checks.append(("pipeline_league_id_param", "league_id" in sig.parameters))
        checks.append(("pipeline_competition_profile_param", "competition_profile" in sig.parameters))

        if wc.success:
            snap = load_extended_markets_from_prediction(wc.prediction)
            checks.append(("extended_markets", snap is not None))
    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
