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
        from worldcup_predictor.database.connection import init_database
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.ingestion.league_history_importer import LeagueHistoryImporter, LeagueImportResult
        from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item

        conn = init_database(":memory:")
        checks.append(("schema_init", conn is not None))
        repo, _db_path = _temp_repo()
        checks.append(("fixture_enrichment_table", "fixture_enrichment" in repo.TABLE_NAMES))
        checks.append(("league_import_runs_table", "league_import_runs" in repo.TABLE_NAMES))

        run_id = repo.start_league_import_run(
            competition_key="premier_league",
            league_id=39,
            season=2023,
            started_at="2026-01-01T00:00:00",
        )
        repo.finish_league_import_run(
            run_id,
            status="ok",
            fixtures_imported=0,
            fixtures_skipped=0,
            enrichment_errors=0,
            message="test",
            finished_at="2026-01-01T00:01:00",
        )
        runs = repo.list_league_import_runs(competition_key="premier_league")
        checks.append(("import_run_logged", len(runs) == 1))

        sample = {
            "fixture": {"id": 999001, "date": "2023-08-12T14:00:00+00:00", "status": {"short": "FT"}},
            "teams": {"home": {"name": "Home FC"}, "away": {"name": "Away FC"}},
            "goals": {"home": 2, "away": 1},
            "score": {"halftime": {"home": 1, "away": 0}},
            "league": {"round": "Regular Season", "country": "England"},
        }
        parsed = parse_api_fixture_item(sample, source="historical")
        checks.append(("parse_fixture", parsed is not None))
        if parsed:
            from worldcup_predictor.config.competitions import PREMIER_LEAGUE

            repo.upsert_competition(PREMIER_LEAGUE)
            saved = repo.upsert_fixture(
                parsed,
                competition_key="premier_league",
                league_id=39,
                season=2023,
            )
            checks.append(("upsert_fixture", saved))
            repo.upsert_fixture_result(parsed, competition_key="premier_league")
            count = repo.count_fixtures_for_league_season(competition_key="premier_league", season=2023)
            checks.append(("count_fixtures", count == 1))

        importer = LeagueHistoryImporter(enrich=False)
        checks.append(("importer_class", hasattr(importer, "import_league_season")))
        checks.append(("import_result_dataclass", hasattr(LeagueImportResult, "to_dict")))
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
