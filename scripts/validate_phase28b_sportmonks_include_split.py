"""Validate Phase 28B — Sportmonks base/premium include split and 403-safe cache."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import runpy

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

WORLD_CUP_LEAGUE = 732
SM_FIXTURE_ID = 99001
API_FIXTURE_ID = 88001

BASE_FIXTURE = {
    "id": SM_FIXTURE_ID,
    "league_id": WORLD_CUP_LEAGUE,
    "participants": [
        {"id": 10, "name": "Brazil", "meta": {"location": "home"}},
        {"id": 20, "name": "France", "meta": {"location": "away"}},
    ],
    "scores": [{"score": {"participant": "home", "goals": 0}}],
    "statistics": [],
    "lineups": [],
    "formations": [],
    "sidelined": [],
    "state": {"state": "NS"},
    "metadata": [],
}


def _mock_safe_get_factory(*, premium_403: bool = True):
    def _safe_get(_self, path: str, *, params: dict | None = None):
        include = str((params or {}).get("include") or "")
        if premium_403 and any(token in include for token in ("odds", "predictions", "xGFixture")):
            return (
                403,
                None,
                "HTTP 403: include 'predictions' not available on your plan (code 5002)",
            )
        return 200, {"data": dict(BASE_FIXTURE)}, None

    return _safe_get


def main() -> int:
    checks: list[tuple[str, bool]] = []

    try:
        from worldcup_predictor.agents.base import AgentContext
        from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence
        from worldcup_predictor.agents.specialists.sportmonks_prediction_agent import (
            SportmonksPredictionAgent,
        )
        from worldcup_predictor.agents.specialists.status_reasons import (
            SPORTMONKS_PLAN_NO_PREDICTIONS_ACCESS,
            SPORTMONKS_PLAN_NO_XG_ACCESS,
        )
        from worldcup_predictor.agents.specialists.xg_intelligence_agent import XGIntelligenceAgent
        from worldcup_predictor.config.settings import Settings
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.providers.sportmonks_consumption import (
            SPORTMONKS_ODDS_PREDICTION_KEY,
            SPORTMONKS_SUPPLEMENTAL_KEY,
            SPORTMONKS_XG_INTELLIGENCE_KEY,
            apply_sportmonks_consumption,
        )
        from worldcup_predictor.providers.sportmonks_enrichment import (
            BASE_WORLD_CUP_FIXTURE_INCLUDES,
            PREMIUM_WORLD_CUP_FIXTURE_INCLUDES,
            _cache_base_includes_complete,
            fetch_worldcup_fixture_enrichment,
            resolve_unified_worldcup_fixture_intelligence,
        )

        tmp = Path(tempfile.mkdtemp())
        db_path = tmp / "phase28b_test.db"
        settings = Settings(
            sqlite_path=str(db_path),
            sportmonks_api_token="test-token-phase28b",
            api_cache_dir=str(tmp / "cache"),
        )
        repo = FootballIntelligenceRepository(str(db_path))

        with patch(
            "worldcup_predictor.providers.sportmonks_enrichment.SportmonksProvider.safe_get",
            _mock_safe_get_factory(premium_403=True),
        ):
            result = fetch_worldcup_fixture_enrichment(
                SM_FIXTURE_ID,
                fixture_id_api_football=API_FIXTURE_ID,
                settings=settings,
                repo=repo,
                force_refresh=True,
            )

        checks.append(("base_enrichment_success", result.success is True))
        checks.append(("base_fixture_present", isinstance(result.fixture, dict)))
        checks.append(
            (
                "base_includes_present",
                all(k in (result.fixture or {}) or k in ("participants", "lineups")
                    for k in ("participants", "scores")),
            )
        )
        checks.append(("premium_not_in_payload", "odds" not in (result.fixture or {})))
        checks.append(("premium_access_dict", isinstance(result.premium_access, dict)))
        pa = result.premium_access or {}
        checks.append(("base_flag_set", pa.get("base_enrichment_available") is True))
        checks.append(
            (
                "premium_denied_flags",
                pa.get("premium_predictions_access_denied") is True
                or pa.get("premium_odds_access_denied") is True,
            )
        )
        checks.append(("api_calls_quota_bounded", result.api_calls_made == 2))

        row = repo.get_sportmonks_fixture_enrichment_cache(SM_FIXTURE_ID)
        checks.append(("sqlite_row_cached", row is not None))
        checks.append(
            (
                "sqlite_base_complete",
                row is not None and _cache_base_includes_complete(row),
            )
        )
        checks.append(
            (
                "sqlite_base_flag",
                row is not None and int(row.get("base_enrichment_available") or 0) == 1,
            )
        )

        mock_get = MagicMock(side_effect=_mock_safe_get_factory(premium_403=True))
        with patch(
            "worldcup_predictor.providers.sportmonks_enrichment.SportmonksProvider.safe_get",
            mock_get,
        ):
            cached = fetch_worldcup_fixture_enrichment(
                SM_FIXTURE_ID,
                fixture_id_api_football=API_FIXTURE_ID,
                settings=settings,
                repo=repo,
                force_refresh=False,
            )
            checks.append(("cache_hit_no_api", cached.source == "cache" and mock_get.call_count == 0))

        with patch(
            "worldcup_predictor.providers.sportmonks_enrichment.lookup_world_cup_fixture",
        ) as mock_lookup:
            mock_lookup.return_value = SimpleNamespace(
                found=True,
                sportmonks_fixture_id=SM_FIXTURE_ID,
                fixture={"id": SM_FIXTURE_ID, "participants": []},
                from_cache=True,
                endpoint="/fixtures/date/2026-06-15",
                reason=None,
            )
            with patch(
                "worldcup_predictor.providers.sportmonks_enrichment.SportmonksProvider.safe_get",
                _mock_safe_get_factory(premium_403=True),
            ):
                unified = resolve_unified_worldcup_fixture_intelligence(
                    api_fixture_id=API_FIXTURE_ID,
                    home_team="Brazil",
                    away_team="France",
                    kickoff_date="2026-06-15",
                    competition_key="world_cup_2026",
                    settings=settings,
                    repo=repo,
                    force_refresh=False,
                )

        checks.append(("unified_success_on_base_only", unified.success is True))
        checks.append(
            (
                "no_lookup_fallback_chain",
                "enrichment_failed_lookup_fallback" not in unified.source_chain,
            )
        )
        checks.append(
            (
                "unified_has_participants",
                isinstance(unified.fixture, dict) and bool(unified.fixture.get("participants")),
            )
        )

        report = MatchIntelligenceReport(
            fixture_id=API_FIXTURE_ID,
            fixture=None,
            home_team=TeamIntelligence(team_name="Brazil", team_id=10),
            away_team=TeamIntelligence(team_name="France", team_id=20),
            provider_metadata={
                "sportmonks_fixture": unified.fixture,
                "sportmonks_premium_access": unified.premium_access,
            },
        )
        enriched = apply_sportmonks_consumption(report)
        sm_sup = (enriched.supplemental_sources or {}).get(SPORTMONKS_SUPPLEMENTAL_KEY) or {}
        checks.append(("consumption_premium_access", isinstance(sm_sup.get("premium_access"), dict)))

        ctx = AgentContext(settings=settings, shared={"intelligence_reports": {API_FIXTURE_ID: enriched}})
        pred_agent = SportmonksPredictionAgent(ctx)
        pred_result = pred_agent.run(fixture_id=API_FIXTURE_ID)
        pred_signal = pred_result.data
        checks.append(
            (
                "prediction_agent_status_reason",
                getattr(pred_signal, "status_reason", None) == SPORTMONKS_PLAN_NO_PREDICTIONS_ACCESS,
            )
        )

        xg_agent = XGIntelligenceAgent(ctx)
        xg_result = xg_agent.run(fixture_id=API_FIXTURE_ID)
        xg_signal = xg_result.data
        checks.append(
            (
                "xg_agent_status_reason",
                getattr(xg_signal, "status_reason", None) == SPORTMONKS_PLAN_NO_XG_ACCESS,
            )
        )

        checks.append(
            (
                "include_groups_defined",
                len(BASE_WORLD_CUP_FIXTURE_INCLUDES) >= 8
                and len(PREMIUM_WORLD_CUP_FIXTURE_INCLUDES) == 3,
            )
        )
        checks.append(
            (
                "odds_block_empty",
                not (enriched.supplemental_sources or {})
                .get(SPORTMONKS_ODDS_PREDICTION_KEY, {})
                .get("available"),
            )
        )
        checks.append(
            (
                "xg_block_empty",
                not (enriched.supplemental_sources or {})
                .get(SPORTMONKS_XG_INTELLIGENCE_KEY, {})
                .get("available"),
            )
        )

        if row and row.get("raw_json"):
            payload = json.loads(row["raw_json"])
            checks.append(
                (
                    "cached_json_has_base_data",
                    isinstance(payload.get("data"), dict)
                    and bool(payload["data"].get("participants")),
                )
            )

    except Exception as exc:
        print(f"FAIL: {exc}")
        import traceback

        traceback.print_exc()
        return 1

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"\n{len(failed)} check(s) failed: {', '.join(failed)}")
        return 1
    print(f"\nAll {len(checks)} Phase 28B checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
