"""Phase 22B — unified Sportmonks fixture intelligence validation (no live API required)."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.providers.base import ProviderTier
    from worldcup_predictor.providers.sportmonks_client import SportmonksClient
    from worldcup_predictor.providers.sportmonks_enrichment import (
        WORLD_CUP_FIXTURE_INCLUDES,
        UnifiedFixtureIntelligenceResult,
        resolve_unified_worldcup_fixture_intelligence,
    )

    checks: list[tuple[str, bool]] = []

    checks.append(("includes_has_state", "state" in WORLD_CUP_FIXTURE_INCLUDES))
    checks.append(("includes_has_events", "events" in WORLD_CUP_FIXTURE_INCLUDES))
    checks.append(("includes_has_sidelined", "sidelined.sideline" in WORLD_CUP_FIXTURE_INCLUDES))

    class _FakeRepo:
        def __init__(self, row: dict | None = None) -> None:
            self._row = row
            self.saved: list[dict] = []

        def get_sportmonks_fixture_enrichment_by_api_fixture_id(self, fixture_id: int):
            return self._row

        def get_sportmonks_fixture_enrichment_cache(self, sportmonks_fixture_id: int):
            return self._row

        def save_sportmonks_fixture_enrichment(self, **kwargs):
            self.saved.append(kwargs)

    sample_fixture = {
        "id": 88001,
        "league_id": 732,
        "participants": [
            {"id": 10, "name": "Mexico", "meta": {"location": "home"}},
            {"id": 11, "name": "South Korea", "meta": {"location": "away"}},
        ],
        "state": {"short_name": "NS"},
        "events": [{"type": "goal"}],
        "statistics": [],
        "lineups": [],
        "sidelined": [],
    }
    cache_payload = {"data": sample_fixture}
    cache_row = {
        "sportmonks_fixture_id": 88001,
        "fixture_id_api_football": 1489388,
        "endpoint": "/fixtures/88001",
        "include_params": ";".join(WORLD_CUP_FIXTURE_INCLUDES),
        "raw_json": json.dumps(cache_payload),
        "expires_at_utc": "2099-01-01T00:00:00",
        "status": "ok",
    }

    from worldcup_predictor.config.settings import Settings

    settings = Settings.model_construct(
        sportmonks_api_token="test-token",
        sportmonks_api_key="",
    )

    unified = resolve_unified_worldcup_fixture_intelligence(
        api_fixture_id=1489388,
        home_team="Mexico",
        away_team="South Korea",
        kickoff_date="2026-06-19",
        settings=settings,
        repo=_FakeRepo(cache_row),
    )
    checks.append(("sqlite_short_circuit", unified.success))
    checks.append(("sqlite_zero_api_calls", unified.api_calls_made == 0))
    checks.append(("sqlite_source_chain", unified.source_chain == ("sqlite_by_api_fixture_id",)))
    checks.append(("sqlite_has_events", "events" in (unified.fixture or {})))
    checks.append(("sqlite_has_state", "state" in (unified.fixture or {})))

    client = SportmonksClient(settings)
    call = client.get_fixture_context(
        home_team="Mexico",
        away_team="South Korea",
        kickoff_date="2026-06-19",
        api_fixture_id=1489388,
        competition_key="world_cup_2026",
    )
    checks.append(("client_returns_fixture", call.available))
    checks.append(("client_trace_phase", (call.trace or {}).get("phase") == "22B_unified"))
    checks.append(("client_tier_enrichment", call.tier == ProviderTier.ENRICHMENT))

    skipped = resolve_unified_worldcup_fixture_intelligence(
        api_fixture_id=1489388,
        home_team="Mexico",
        away_team="South Korea",
        competition_key="bundesliga",
        settings=settings,
        repo=_FakeRepo(cache_row),
    )
    checks.append(("non_wc_skipped", not skipped.success))
    checks.append(("non_wc_no_fixture", skipped.fixture is None))

    failed = 0
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
        if not ok:
            failed += 1

    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
