"""Phase 50A validation — Odds API credit guard."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ["ODDS_API_DAILY_SOFT_LIMIT"] = "15"
os.environ["ODDS_API_DAILY_HARD_LIMIT"] = "16"
os.environ["ODDS_API_MONTHLY_LIMIT"] = "500"
os.environ["ODDS_API_CACHE_HOURS"] = "6"
os.environ["THE_ODDS_API_KEY"] = "test-key-for-validation"


def _fresh_repo():
    db = Path(tempfile.gettempdir()) / f"phase50a_{uuid.uuid4().hex}.db"
    os.environ["FOOTBALL_DB_PATH"] = str(db)
    from worldcup_predictor.providers.odds_api_credit import repository as repo_mod

    repo_mod._repo = None
    return db, repo_mod


def _guard_mod():
    from worldcup_predictor.providers.odds_api_credit import guard as guard_mod

    return guard_mod


def _minimal_fixture(*, fixture_id: int = 1):
    from datetime import datetime, timezone

    from worldcup_predictor.domain.fixture import Fixture

    return Fixture(
        id=fixture_id,
        competition_key="world_cup_2026",
        home_team="A",
        away_team="B",
        kickoff_utc=datetime.now(timezone.utc),
        venue="TBD",
        stage="Group",
        league_id=1,
        season=2026,
    )


def _minimal_report(*, fixture_id: int = 1, odds=None):
    from worldcup_predictor.domain.intelligence import MatchIntelligenceReport, TeamIntelligence

    home = TeamIntelligence(team_name="A", team_id=1)
    away = TeamIntelligence(team_name="B", team_id=2)
    return MatchIntelligenceReport(
        fixture_id=fixture_id,
        fixture=None,
        home_team=home,
        away_team=away,
        odds=odds,
    )


def test_daily_15_allows_next() -> None:
    from worldcup_predictor.config.settings import get_settings

    db, repo_mod = _fresh_repo()
    guard_mod = _guard_mod()
    try:
        repo = repo_mod.get_odds_api_repository()
        for i in range(14):
            repo.record_usage(endpoint="sports/x/odds", fixture_id=1000 + i, credits_used=1, source="validation")

        settings = get_settings()
        fixture = _minimal_fixture()
        decision = guard_mod.evaluate_odds_api_call(_minimal_report(), fixture, settings, force=True)
        assert decision.allowed, "16th credit (14+2) within hard limit should be allowed"
        assert decision.daily_used == 14
    finally:
        repo_mod._repo = None
        try:
            db.unlink()
        except OSError:
            pass


def test_daily_16_blocks() -> None:
    from worldcup_predictor.config.settings import get_settings

    db, repo_mod = _fresh_repo()
    guard_mod = _guard_mod()
    try:
        repo = repo_mod.get_odds_api_repository()
        for i in range(8):
            repo.record_usage(endpoint="sports/x/odds", fixture_id=2000 + i, credits_used=2, source="validation")

        settings = get_settings()
        fixture = _minimal_fixture()
        decision = guard_mod.evaluate_odds_api_call(_minimal_report(), fixture, settings, force=True)
        assert not decision.allowed
        assert decision.reason == "daily_hard_limit_exceeded"
    finally:
        repo_mod._repo = None
        try:
            db.unlink()
        except OSError:
            pass


def test_cache_prevents_repeat() -> None:
    from worldcup_predictor.config.settings import get_settings

    db, repo_mod = _fresh_repo()
    guard_mod = _guard_mod()
    try:
        repo = repo_mod.get_odds_api_repository()
        repo.set_cache(99, "h2h,totals", {"home_team": "A", "away_team": "B", "bookmakers": []})

        settings = get_settings()
        fixture = _minimal_fixture(fixture_id=99)
        decision = guard_mod.evaluate_odds_api_call(_minimal_report(fixture_id=99), fixture, settings, force=False)
        assert decision.allowed
        assert decision.from_cache
        assert decision.reason == "cache_hit"
    finally:
        repo_mod._repo = None
        try:
            db.unlink()
        except OSError:
            pass


def test_predict_works_without_odds_api_key() -> None:
    db, repo_mod = _fresh_repo()
    guard_mod = _guard_mod()
    try:

        class _Unconfigured:
            the_odds_api_configured = False

        decision = guard_mod.evaluate_odds_api_call(
            _minimal_report(),
            _minimal_fixture(),
            _Unconfigured(),  # type: ignore[arg-type]
            force=True,
        )
        assert not decision.allowed
        assert decision.reason == "not_configured"
    finally:
        repo_mod._repo = None
        try:
            db.unlink()
        except OSError:
            pass


def main() -> int:
    tests = [
        test_daily_15_allows_next,
        test_daily_16_blocks,
        test_cache_prevents_repeat,
        test_predict_works_without_odds_api_key,
    ]
    for fn in tests:
        fn()
        print(f"PASS: {fn.__name__}")
    print("\nPhase 50A validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
