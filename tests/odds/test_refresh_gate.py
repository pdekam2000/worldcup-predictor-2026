"""Tests for odds refresh gate and dynamic TTL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from worldcup_predictor.odds.freshness_policy import (
    FreshnessStatus,
    classify_odds_freshness,
    get_allowed_odds_ttl_seconds,
)
from worldcup_predictor.odds.refresh_gate import (
    _median_1x2_decimal,
    ensure_fresh_odds_before_prediction,
    refresh_live_odds,
    validate_legitimate_1x2_snapshot,
)
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture


def test_dynamic_ttl_more_than_24h_before_kickoff():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    kickoff = (now + timedelta(hours=30)).isoformat()
    assert get_allowed_odds_ttl_seconds(kickoff, now) == 6 * 3600


def test_dynamic_ttl_24h_to_6h_before_kickoff():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    kickoff = (now + timedelta(hours=12)).isoformat()
    assert get_allowed_odds_ttl_seconds(kickoff, now) == 2 * 3600


def test_dynamic_ttl_6h_to_1h_before_kickoff():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    kickoff = (now + timedelta(hours=3)).isoformat()
    assert get_allowed_odds_ttl_seconds(kickoff, now) == 30 * 60


def test_dynamic_ttl_less_than_1h_before_kickoff():
    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    kickoff = (now + timedelta(minutes=30)).isoformat()
    assert get_allowed_odds_ttl_seconds(kickoff, now) == 10 * 60


def test_post_kickoff_invalid_without_live_support():
    now = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
    kickoff = (now - timedelta(hours=1)).isoformat()
    assert get_allowed_odds_ttl_seconds(kickoff, now) is None
    cls = classify_odds_freshness(
        odds_snapshot_at=now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        kickoff_utc=kickoff,
        has_odds=True,
    )
    assert cls.requires_fresh_odds is True


def test_fresh_odds_no_refresh_required():
    now = datetime.now(timezone.utc)
    snap = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S UTC")
    kickoff = (now + timedelta(hours=2)).isoformat()
    row = {
        "fixture_id": 1,
        "home_team": "A",
        "away_team": "B",
        "kickoff_utc": kickoff,
        "competition_key": "allsvenskan",
        "status": "NS",
    }
    daily = DailyFixture(
        fixture_id=1,
        provider_fixture_id=1,
        competition_key="allsvenskan",
        home_team="A",
        away_team="B",
        kickoff_utc=kickoff,
        status="NS",
        season=2026,
    )
    conn = MagicMock()
    with (
        patch("worldcup_predictor.odds.refresh_gate._freshness_for_row") as fresh,
        patch("worldcup_predictor.odds.refresh_gate.validate_legitimate_1x2_snapshot") as legit,
        patch("worldcup_predictor.odds.refresh_gate.refresh_live_odds") as relive,
    ):
        fresh.return_value = {
            "odds_freshness_status": FreshnessStatus.FRESH_ODDS.value,
            "requires_fresh_odds": False,
            "odds_snapshot_at": snap,
        }
        legit.return_value = (True, None, {"valid": True})
        out = ensure_fresh_odds_before_prediction(conn, row, daily, refresh_if_needed=True)
        assert out["allowed"] is True
        relive.assert_not_called()


def test_stale_odds_refresh_succeeds():
    row = {
        "fixture_id": 2,
        "home_team": "C",
        "away_team": "D",
        "kickoff_utc": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "competition_key": "allsvenskan",
        "status": "NS",
    }
    daily = DailyFixture(
        fixture_id=2,
        provider_fixture_id=2,
        competition_key="allsvenskan",
        home_team="C",
        away_team="D",
        kickoff_utc=row["kickoff_utc"],
        status="NS",
        season=2026,
    )
    conn = MagicMock()
    fresh_seq = [
        {"odds_freshness_status": FreshnessStatus.STALE_ODDS.value, "requires_fresh_odds": True},
        {"odds_freshness_status": FreshnessStatus.FRESH_ODDS.value, "requires_fresh_odds": False},
    ]
    legit_seq = [(False, "STALE_ODDS", {}), (True, None, {"valid": True})]
    with (
        patch("worldcup_predictor.odds.refresh_gate._freshness_for_row", side_effect=fresh_seq),
        patch("worldcup_predictor.odds.refresh_gate.validate_legitimate_1x2_snapshot", side_effect=legit_seq),
        patch(
            "worldcup_predictor.odds.refresh_gate.refresh_live_odds",
            return_value={"success": True, "status": "imported_live", "provider": "api-football", "attempts": []},
        ),
    ):
        out = ensure_fresh_odds_before_prediction(conn, row, daily, refresh_if_needed=True)
        assert out["allowed"] is True
        assert out["refresh_success"] is True


def test_stale_odds_refresh_fails_blocks():
    row = {
        "fixture_id": 3,
        "home_team": "E",
        "away_team": "F",
        "kickoff_utc": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "competition_key": "allsvenskan",
        "status": "NS",
    }
    daily = DailyFixture(
        fixture_id=3,
        provider_fixture_id=3,
        competition_key="allsvenskan",
        home_team="E",
        away_team="F",
        kickoff_utc=row["kickoff_utc"],
        status="NS",
        season=2026,
    )
    conn = MagicMock()
    with (
        patch(
            "worldcup_predictor.odds.refresh_gate._freshness_for_row",
            return_value={"odds_freshness_status": FreshnessStatus.STALE_ODDS.value, "requires_fresh_odds": True},
        ),
        patch(
            "worldcup_predictor.odds.refresh_gate.validate_legitimate_1x2_snapshot",
            return_value=(False, "STALE_ODDS", {}),
        ),
        patch(
            "worldcup_predictor.odds.refresh_gate.refresh_live_odds",
            return_value={"success": False, "status": "all_live_providers_failed", "attempts": []},
        ),
        patch("worldcup_predictor.odds.refresh_gate.get_settings") as gs,
    ):
        gs.return_value.api_football_configured = True
        gs.return_value.sportmonks_configured = False
        out = ensure_fresh_odds_before_prediction(conn, row, daily, refresh_if_needed=True)
        assert out["allowed"] is False
        assert out["final_block_reason"] == "STALE_ODDS_REFRESH_FAILED"


def test_incomplete_1x2_rejected():
    class Line:
        def __init__(self, bm, market, sel, odd):
            self.bookmaker = bm
            self.market_name = market
            self.selection = sel
            self.odd = odd

    odds = _median_1x2_decimal(
        [
            Line("bk1", "Match Winner", "home", "2.1"),
            Line("bk1", "Match Winner", "away", "3.2"),
        ]
    )
    assert odds["valid"] is False


def test_odds_timestamp_missing_blocks():
    conn = MagicMock()
    with patch("worldcup_predictor.odds.refresh_gate._latest_odds_snapshot") as snap:
        snap.return_value = {"payload": {"bookmakers": []}, "snapshot_at": None}
        ok, reason, _ = validate_legitimate_1x2_snapshot(conn, 99)
        assert ok is False
        assert reason == "ODDS_TIMESTAMP_MISSING"


def test_missing_odds_all_providers_fail():
    row = {
        "fixture_id": 4,
        "home_team": "G",
        "away_team": "H",
        "kickoff_utc": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "competition_key": "allsvenskan",
        "status": "NS",
    }
    daily = DailyFixture(
        fixture_id=4,
        provider_fixture_id=4,
        competition_key="allsvenskan",
        home_team="G",
        away_team="H",
        kickoff_utc=row["kickoff_utc"],
        status="NS",
        season=2026,
    )
    conn = MagicMock()
    with (
        patch(
            "worldcup_predictor.odds.refresh_gate._freshness_for_row",
            return_value={"odds_freshness_status": FreshnessStatus.ODDS_MISSING.value, "requires_fresh_odds": True},
        ),
        patch(
            "worldcup_predictor.odds.refresh_gate.validate_legitimate_1x2_snapshot",
            return_value=(False, "NO_LEGITIMATE_1X2_ODDS", {}),
        ),
        patch(
            "worldcup_predictor.odds.refresh_gate.refresh_live_odds",
            return_value={"success": False, "status": "all_live_providers_failed", "attempts": []},
        ),
        patch("worldcup_predictor.odds.refresh_gate.get_settings") as gs,
    ):
        gs.return_value.api_football_configured = True
        gs.return_value.sportmonks_configured = True
        out = ensure_fresh_odds_before_prediction(conn, row, daily, refresh_if_needed=True)
        assert out["allowed"] is False
        assert out["final_block_reason"] == "NO_LEGITIMATE_1X2_ODDS_AFTER_REFRESH"


def test_missing_odds_refresh_succeeds():
    row = {
        "fixture_id": 5,
        "home_team": "I",
        "away_team": "J",
        "kickoff_utc": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
        "competition_key": "allsvenskan",
        "status": "NS",
    }
    daily = DailyFixture(
        fixture_id=5,
        provider_fixture_id=5,
        competition_key="allsvenskan",
        home_team="I",
        away_team="J",
        kickoff_utc=row["kickoff_utc"],
        status="NS",
        season=2026,
    )
    conn = MagicMock()
    with (
        patch(
            "worldcup_predictor.odds.refresh_gate._freshness_for_row",
            side_effect=[
                {"odds_freshness_status": FreshnessStatus.ODDS_MISSING.value, "requires_fresh_odds": True},
                {"odds_freshness_status": FreshnessStatus.FRESH_ODDS.value, "requires_fresh_odds": False},
            ],
        ),
        patch(
            "worldcup_predictor.odds.refresh_gate.validate_legitimate_1x2_snapshot",
            side_effect=[(False, "NO_LEGITIMATE_1X2_ODDS", {}), (True, None, {"valid": True})],
        ),
        patch(
            "worldcup_predictor.odds.refresh_gate.refresh_live_odds",
            return_value={"success": True, "status": "imported_live", "provider": "api-football", "attempts": []},
        ),
    ):
        out = ensure_fresh_odds_before_prediction(conn, row, daily, refresh_if_needed=True)
        assert out["allowed"] is True
        assert out["refresh_success"] is True
