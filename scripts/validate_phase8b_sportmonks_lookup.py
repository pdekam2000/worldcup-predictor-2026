"""Validate Sportmonks fixture lookup — no secrets logged."""

from __future__ import annotations

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

FIXTURE_ID = 1489388


def main() -> int:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.providers.sportmonks_fixture_lookup import (
        lookup_world_cup_fixture,
        team_names_match,
    )

    checks: list[tuple[str, bool]] = []

    checks.append(("team_alias_korea", team_names_match("South Korea", "Korea Republic")))
    checks.append(("team_alias_mexico", team_names_match("Mexico", "Mexico")))

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    row = repo.get_fixture_row(FIXTURE_ID)
    home = str((row or {}).get("home_team") or "Mexico")
    away = str((row or {}).get("away_team") or "South Korea")
    kickoff = str((row or {}).get("kickoff_utc") or "")[:10] or "2026-06-19"

    if not settings.sportmonks_configured:
        print("SKIP live lookup: sportmonks not configured")
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'}: {name}")
        return 0

    lookup = lookup_world_cup_fixture(
        api_fixture_id=FIXTURE_ID,
        home_team=home,
        away_team=away,
        kickoff_date=kickoff,
        settings=settings,
    )

    print(f"fixture_id: {FIXTURE_ID}")
    print(f"teams: {home} vs {away}")
    print(f"kickoff_date: {kickoff}")
    print(f"sportmonks_fixture_found: {lookup.found}")
    print(f"endpoint: {lookup.endpoint}")
    print(f"status_code: {lookup.status_code}")
    print(f"reason: {lookup.reason}")
    print(f"from_cache: {lookup.from_cache}")
    if lookup.sportmonks_fixture_id:
        print(f"sportmonks_fixture_id: {lookup.sportmonks_fixture_id}")

    checks.append(("no_http_400", lookup.status_code != 400))
    checks.append(("lookup_ok_or_not_found", lookup.status_code in (200, None) or lookup.found))
    checks.append(
        ("found_has_participants",
         not lookup.found
         or bool((lookup.fixture or {}).get("participants"))),
    )

    # Second call should be cache hit (0 additional date fetches)
    lookup2 = lookup_world_cup_fixture(
        api_fixture_id=FIXTURE_ID,
        home_team=home,
        away_team=away,
        kickoff_date=kickoff,
        settings=settings,
    )
    checks.append(("second_call_cache", lookup2.from_cache))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed")
        return 1
    print(f"\nAll {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
