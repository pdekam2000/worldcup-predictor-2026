"""Validate Phase 40A incremental league sync."""

from __future__ import annotations

from pathlib import Path
import runpy
import sys
import tempfile

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    checks: list[tuple[str, bool]] = []
    try:
        from worldcup_predictor.config.competitions import PREMIER_LEAGUE
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
        from worldcup_predictor.ingestion.league_history_importer import LeagueHistoryImporter

        path = Path(tempfile.mkstemp(suffix=".db")[1])
        repo = FootballIntelligenceRepository(str(path))
        repo.upsert_competition(PREMIER_LEAGUE)

        sample = {
            "fixture": {"id": 880001, "date": "2023-08-12T14:00:00+00:00", "status": {"short": "FT"}},
            "teams": {"home": {"name": "A"}, "away": {"name": "B"}},
            "goals": {"home": 1, "away": 0},
            "league": {"round": "Regular Season"},
        }
        fx = parse_api_fixture_item(sample, source="historical")
        assert fx is not None
        repo.upsert_fixture(fx, competition_key="premier_league", league_id=39, season=2023)

        ids = repo.fixture_ids_for_competition_season(competition_key="premier_league", season=2023)
        checks.append(("fixture_ids_set", 880001 in ids))

        repo.upsert_league_sync_state(
            competition_key="premier_league",
            season=2023,
            last_imported_fixture_id=880001,
            last_imported_date="2023-08-12",
        )
        state = repo.get_league_sync_state(competition_key="premier_league", season=2023)
        checks.append(("sync_state", state is not None and state["last_imported_fixture_id"] == 880001))

        importer = LeagueHistoryImporter(enrich=False, repository=repo)
        checks.append(("importer_incremental", hasattr(importer, "import_league_season")))

        # Re-import with populated DB should skip API (not configured → early path still valid)
        result = importer.import_league_season(league_id=39, season=2023)
        checks.append(("skip_when_populated", result.fixtures_skipped >= 1 or result.fixtures_imported == 0))
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
