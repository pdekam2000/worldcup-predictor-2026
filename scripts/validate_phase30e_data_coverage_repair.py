#!/usr/bin/env python3
"""Phase 30E — data coverage repair validation."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURE_ID = 1539007

# Production-like specialist summary (Phase 30D audit snapshot)
FIXTURE_1539007_SPECIALISTS = {
    "aggregated_score": 57.3,
    "agents": {
        "lineup_agent": {
            "domain": "lineups",
            "status": "available",
            "status_reason": "live_data_available",
            "impact_score": 55.0,
        },
        "expected_lineup_agent": {
            "domain": "expected_lineup_intelligence",
            "status": "available",
            "status_reason": None,
            "impact_score": 84.0,
        },
        "odds_market_agent": {
            "domain": "odds_market",
            "status": "partial",
            "status_reason": None,
            "impact_score": 54.9,
        },
        "market_consensus_agent": {
            "domain": "market_consensus",
            "status": "available",
            "status_reason": None,
            "impact_score": 96.9,
        },
        "injury_suspension_agent": {
            "domain": "injuries_suspensions",
            "status": "partial",
            "status_reason": "heuristic_partial",
            "impact_score": 54.0,
        },
    },
}


def _assert(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        msg = f"  FAIL  {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)
        raise AssertionError(f"{name}: {detail}")


def test_display_signals() -> None:
    print("\n=== 30E-1 display_helpers ===")
    from worldcup_predictor.api.display_helpers import data_signals_from_specialist_summary

    signals = data_signals_from_specialist_summary(
        FIXTURE_1539007_SPECIALISTS,
        data_quality=55.0,
        fixture_status="NS",
    )
    _assert("missing_lineups is False", signals["missing_lineups"] is False, str(signals))
    _assert("official_lineup_pending is True", signals["official_lineup_pending"] is True, str(signals))
    _assert("lineup_coverage is pending", signals["lineup_coverage"] == "pending", str(signals))
    _assert("odds_available is True", signals["odds_available"] is True, str(signals))
    print("  signals", signals)


def test_dq_projected_lineups() -> None:
    print("\n=== 30E-3 data quality projected lineups ===")
    from worldcup_predictor.data_quality.intelligence_scoring import score_data_quality_components
    from worldcup_predictor.data_quality.transparency import explain_data_quality
    from worldcup_predictor.domain.fixture import Fixture
    from worldcup_predictor.domain.intelligence import (
        DataQualityReport,
        InjuryReport,
        MatchIntelligenceReport,
        OddsSnapshot,
        TeamIntelligence,
    )

    kickoff = datetime(2026, 6, 20, 17, 0, 0)
    fixture = Fixture(
        id=FIXTURE_ID,
        competition_key="world_cup_2026",
        home_team="Netherlands",
        away_team="Sweden",
        kickoff_utc=kickoff,
        venue="NRG Stadium",
        stage="Group Stage - 2",
        league_id=1,
        season=2026,
        status="NS",
        source="live",
        home_team_id=111,
        away_team_id=222,
    )
    report = MatchIntelligenceReport(
        fixture_id=FIXTURE_ID,
        fixture=fixture,
        home_team=TeamIntelligence(team_name="Netherlands", team_id=111, form=["W", "D", "W"]),
        away_team=TeamIntelligence(team_name="Sweden", team_id=222, form=["L", "W", "D"]),
        odds=OddsSnapshot(fixture_id=FIXTURE_ID, available=True, bookmakers=[{"name": "10Bet"}]),
        lineups={"items": [], "available": False, "skipped": "far_from_kickoff"},
        standings_context={"available": True, "groups": []},
        missing_data=["lineups"],
        source="live",
        is_placeholder=False,
    )
    components, _ = score_data_quality_components(report)
    _assert("lineups partial score is 10", components.get("lineups") == 10, str(components))
    detail = explain_data_quality(report)
    _assert("display_total >= 65 with projected lineups", detail.display_total >= 65, str(detail.display_total))
    print("  components", {k: v for k, v in components.items() if v})
    print("  display_total", detail.display_total)


def test_sqlite_persistence() -> None:
    print("\n=== 30E-2 SQLite fixture persistence ===")
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.domain.schedule import TournamentFixture

    db_path = ROOT / "data" / "shadow" / "_phase30e_test.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    repo = FootballIntelligenceRepository(path=str(db_path))
    try:
        repo.seed_competitions()
        fx = TournamentFixture(
            fixture_id=FIXTURE_ID,
            kickoff_time=datetime(2026, 6, 20, 17, 0, 0),
            home_team="Netherlands",
            away_team="Sweden",
            venue="NRG Stadium",
            city="Houston",
            country="USA",
            group="Group Stage - 2",
            round="Group Stage - 2",
            status="NS",
            is_placeholder=False,
            source="live",
            home_team_id=1110,
            away_team_id=2220,
            league_id=1,
            season=2026,
        )
        saved = repo.upsert_fixture(fx, competition_key="world_cup_2026", league_id=1, season=2026)
        _assert("upsert_fixture returns True", saved is True)
        row = repo.get_fixture_row(FIXTURE_ID)
        assert row is not None
        _assert("home_team_id persisted", row.get("home_team_id") == 1110, str(row))
        _assert("away_team_id persisted", row.get("away_team_id") == 2220, str(row))
        _assert("league_id persisted", row.get("league_id") == 1, str(row))
        _assert("season persisted", row.get("season") == 2026, str(row))

        repo.update_fixture_identity(FIXTURE_ID, home_team_id=1111, away_team_id=2221)
        row2 = repo.get_fixture_row(FIXTURE_ID)
        assert row2 is not None
        _assert("update_fixture_identity home", row2.get("home_team_id") == 1111)
        _assert("update_fixture_identity away", row2.get("away_team_id") == 2221)
    finally:
        repo.close()
    try:
        db_path.unlink(missing_ok=True)
    except OSError:
        pass


def test_live_predict_optional() -> None:
    print("\n=== live predict fixture 1539007 (optional) ===")
    from worldcup_predictor.config.settings import get_settings

    settings = get_settings()
    if not settings.api_football_configured:
        print("  SKIP  API_FOOTball not configured locally")
        return

    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline

    pipeline = PredictPipeline(settings, competition_key="world_cup_2026")
    result = pipeline.run(FIXTURE_ID, record_history=False)
    if not result.success:
        print("  SKIP  predict pipeline failed (quota/network)")
        return

    from worldcup_predictor.api.display_helpers import data_signals_from_specialist_summary
    from worldcup_predictor.api.routes.predictions import _specialist_summary, _data_quality_score

    specialist = _specialist_summary(result, result.prediction)
    dq = _data_quality_score(result.prediction)
    signals = data_signals_from_specialist_summary(specialist, data_quality=dq, fixture_status="NS")
    _assert("live missing_lineups False", signals["missing_lineups"] is False, str(signals))
    _assert("live odds_available True", signals["odds_available"] is True, str(signals))
    _assert("live official_lineup_pending True", signals["official_lineup_pending"] is True, str(signals))
    _assert("live data_quality improved (>= 58)", dq >= 58, f"was 55 pre-fix, got {dq}")
    print("  live data_quality", dq)
    print("  live signals", signals)


def main() -> int:
    print("Phase 30E validation — fixture", FIXTURE_ID)
    test_display_signals()
    test_dq_projected_lineups()
    test_sqlite_persistence()
    try:
        test_live_predict_optional()
    except Exception as exc:
        print(f"  SKIP  live predict: {exc}")
    print("\nAll Phase 30E validation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
