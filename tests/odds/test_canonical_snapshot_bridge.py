"""Canonical odds snapshot bridge — filter and prediction must read the same snapshot."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from worldcup_predictor.gpt_actions.delegation import _match_odds
from worldcup_predictor.odds.canonical_snapshot import (
    MARKET_FULL_TIME_1X2,
    extract_odds_fetched_at_utc,
    get_latest_valid_1x2_odds_snapshot,
    normalize_odds_market_name,
)
from worldcup_predictor.odds.freshness_metadata import build_fixture_freshness_metadata
from worldcup_predictor.odds.freshness_policy import FreshnessStatus
from worldcup_predictor.odds.refresh_gate import ensure_fresh_odds_before_prediction, validate_legitimate_1x2_snapshot
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _bookmakers(n: int = 14, market: str = "Match Winner") -> list[dict]:
    out = []
    for i in range(n):
        out.append(
            {
                "name": f"Bookmaker{i + 1}",
                "bets": [
                    {
                        "name": market,
                        "values": [
                            {"value": "Home", "odd": "2.90"},
                            {"value": "Draw", "odd": "3.40"},
                            {"value": "Away", "odd": "2.35"},
                        ],
                    }
                ],
            }
        )
    return out


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL,
            competition_key TEXT NOT NULL,
            snapshot_at TEXT,
            payload_json TEXT NOT NULL
        )
        """
    )
    return conn


def _insert_snapshot(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    payload: dict,
    snapshot_at: str | None = None,
    competition_key: str = "eliteserien",
) -> int:
    cur = conn.execute(
        "INSERT INTO odds_snapshots(fixture_id, competition_key, snapshot_at, payload_json) VALUES (?, ?, ?, ?)",
        (fixture_id, competition_key, snapshot_at, json.dumps(payload)),
    )
    conn.commit()
    return int(cur.lastrowid)


@pytest.fixture
def conn():
    c = _make_conn()
    yield c
    c.close()


def test_reproduction_filter_sees_odds_freshness_not_missing(conn):
    """Reproduces production impossible state: complete odds visible but ODDS_MISSING blocked."""
    fid = 1494694
    fetched = _iso(_utc_now() - timedelta(minutes=8))
    payload = {
        "provider": "api-football",
        "bookmakers": _bookmakers(14),
        "fetched_at_utc": fetched,
    }
    _insert_snapshot(conn, fixture_id=fid, payload=payload, snapshot_at=None)
    kickoff = (_utc_now() + timedelta(hours=3)).isoformat()

    filter_odds = _match_odds(conn, fid)
    assert filter_odds["bookmaker_count"] == 14
    assert filter_odds["home"] is not None

    meta = build_fixture_freshness_metadata(conn, fixture_id=fid, kickoff_utc=kickoff, round_name=None, status="NS")
    assert meta["odds_freshness_class"] != "ODDS_MISSING"
    assert meta.get("odds_age_hours") is not None or meta["canonical_odds_snapshot"].get("odds_age_minutes") is not None


def test_filter_and_validator_select_same_snapshot(conn):
    fid = 1581037
    fetched = _iso(_utc_now() - timedelta(minutes=5))
    row_id = _insert_snapshot(
        conn,
        fixture_id=fid,
        payload={"provider": "api-football", "bookmakers": _bookmakers(14), "fetched_at_utc": fetched},
        snapshot_at=None,
    )
    kickoff = (_utc_now() + timedelta(hours=2)).isoformat()
    filter_odds = _match_odds(conn, fid)
    ok, _, legit = validate_legitimate_1x2_snapshot(conn, fid, kickoff_utc=kickoff)
    assert filter_odds["canonical_row_id"] == row_id
    assert legit["row_id"] == row_id
    assert ok is True
    assert filter_odds["home"] == legit["home_odds"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("fetched_at", "2026-07-11 18:00:00 UTC"),
        ("fetched_at_utc", "2026-07-11 18:00:00+00:00"),
        ("last_odds_fetched_at", "2026-07-11T18:00:00Z"),
    ],
)
def test_timestamp_alias_fields_recognized(conn, field, value):
    fid = 1
    payload = {"provider": "api-football", "bookmakers": _bookmakers(3), field: value}
    _insert_snapshot(conn, fixture_id=fid, payload=payload, snapshot_at=None)
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.fetched_at_utc is not None
    assert snap.timestamp_source_field == f"payload.{field}"


def test_snapshot_at_column_recognized(conn):
    fid = 2
    ts = "2026-07-11 19:00:00 UTC"
    payload = {"provider": "api-football", "bookmakers": _bookmakers(2)}
    _insert_snapshot(conn, fixture_id=fid, payload=payload, snapshot_at=ts)
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.timestamp_source_field == "snapshot_at_column"


def test_created_at_legacy_fallback(conn):
    fid = 3
    payload = {
        "provider": "api-football",
        "bookmakers": _bookmakers(2),
        "created_at": "2026-07-11 20:00:00 UTC",
    }
    _insert_snapshot(conn, fixture_id=fid, payload=payload, snapshot_at=None)
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.timestamp_source_field == "payload.created_at"


def test_naive_utc_normalized(conn):
    row = {"snapshot_at": "2026-07-11 21:00:00 UTC", "payload": {}}
    dt, iso, field = extract_odds_fetched_at_utc(row)
    assert dt is not None
    assert dt.tzinfo is not None
    assert field == "snapshot_at_column"


def test_invalid_timestamp_odds_timestamp_missing(conn):
    fid = 4
    payload = {"provider": "api-football", "bookmakers": _bookmakers(2), "fetched_at_utc": "not-a-date"}
    _insert_snapshot(conn, fixture_id=fid, payload=payload, snapshot_at="also-bad")
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.freshness_class == "ODDS_TIMESTAMP_MISSING"


def test_no_row_odds_missing(conn):
    snap = get_latest_valid_1x2_odds_snapshot(conn, 99999)
    assert snap.freshness_class == "ODDS_MISSING"


def test_provider_missing_classification(conn):
    fid = 5
    fetched = _iso(_utc_now() - timedelta(minutes=10))
    payload = {"bookmakers": _bookmakers(2), "fetched_at_utc": fetched}
    _insert_snapshot(conn, fixture_id=fid, payload=payload)
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.freshness_class == "ODDS_PROVIDER_MISSING"


def test_unsupported_market_classification(conn):
    fid = 6
    fetched = _iso(_utc_now() - timedelta(minutes=10))
    payload = {"provider": "api-football", "bookmakers": _bookmakers(2, market="First Half Winner"), "fetched_at_utc": fetched}
    _insert_snapshot(conn, fixture_id=fid, payload=payload)
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.freshness_class == "ODDS_MARKET_NOT_SUPPORTED"


def test_incomplete_hda_classification(conn):
    fid = 7
    fetched = _iso(_utc_now() - timedelta(minutes=10))
    bms = [
        {
            "name": "OnlyHome",
            "bets": [{"name": "Match Winner", "values": [{"value": "Home", "odd": "2.0"}]}],
        }
    ]
    payload = {"provider": "api-football", "bookmakers": bms, "fetched_at_utc": fetched}
    _insert_snapshot(conn, fixture_id=fid, payload=payload)
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.freshness_class == "ODDS_INCOMPLETE"


def test_stale_row_real_age(conn):
    fid = 8
    fetched = _iso(_utc_now() - timedelta(hours=5))
    payload = {"provider": "api-football", "bookmakers": _bookmakers(4), "fetched_at_utc": fetched}
    _insert_snapshot(conn, fixture_id=fid, payload=payload)
    kickoff = (_utc_now() + timedelta(hours=2)).isoformat()
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=kickoff)
    assert snap.freshness_class == "ODDS_STALE"
    assert snap.odds_age_minutes is not None
    assert snap.odds_age_minutes > 60


def test_fresh_row_real_age(conn):
    fid = 9
    fetched = _iso(_utc_now() - timedelta(minutes=3))
    payload = {"provider": "api-football", "bookmakers": _bookmakers(4), "fetched_at_utc": fetched}
    _insert_snapshot(conn, fixture_id=fid, payload=payload)
    kickoff = (_utc_now() + timedelta(hours=2)).isoformat()
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=kickoff)
    assert snap.freshness_class == "ODDS_FRESH"
    assert snap.odds_age_minutes is not None


def test_malformed_newer_row_falls_back_to_valid(conn):
    fid = 10
    good = _iso(_utc_now() - timedelta(minutes=15))
    _insert_snapshot(
        conn,
        fixture_id=fid,
        payload={"provider": "api-football", "bookmakers": _bookmakers(3), "fetched_at_utc": good},
    )
    _insert_snapshot(
        conn,
        fixture_id=fid,
        payload={"provider": "api-football", "bookmakers": _bookmakers(1, market="First Half Winner"), "fetched_at_utc": _iso(_utc_now())},
    )
    snap = get_latest_valid_1x2_odds_snapshot(conn, fid, kickoff_utc=(_utc_now() + timedelta(hours=2)).isoformat())
    assert snap.freshness_class in {"ODDS_FRESH", "ODDS_STALE"}
    assert snap.bookmaker_count == 3


@pytest.mark.parametrize(
    "market,expected",
    [
        ("Match Winner", MARKET_FULL_TIME_1X2),
        ("FT Result", MARKET_FULL_TIME_1X2),
        ("first-half result", None),
        ("qualification winner", None),
    ],
)
def test_market_normalizer(market, expected):
    assert normalize_odds_market_name(market) == expected


def test_refresh_import_visible_to_freshness_reader(conn):
    fid = 1495730
    kickoff = (_utc_now() + timedelta(hours=4)).isoformat()
    fetched = _iso(_utc_now() - timedelta(minutes=2))
    _insert_snapshot(
        conn,
        fixture_id=fid,
        payload={"provider": "api-football", "bookmakers": _bookmakers(14), "fetched_at_utc": fetched},
        snapshot_at=fetched,
    )
    meta = build_fixture_freshness_metadata(conn, fixture_id=fid, kickoff_utc=kickoff, round_name=None, status="NS")
    assert meta["odds_freshness_class"] == "ODDS_FRESH"
    assert meta["canonical_odds_snapshot"]["bookmaker_count"] == 14


def test_successful_import_stale_classified_separately(conn):
    row = {
        "fixture_id": 1494206,
        "home_team": "Mjallby",
        "away_team": "AIK",
        "kickoff_utc": (_utc_now() + timedelta(hours=2)).isoformat(),
        "competition_key": "allsvenskan",
        "status": "NS",
    }
    daily = DailyFixture(
        fixture_id=1494206,
        provider_fixture_id=1494206,
        competition_key="allsvenskan",
        home_team="Mjallby",
        away_team="AIK",
        kickoff_utc=row["kickoff_utc"],
        status="NS",
        season=2026,
    )
    stale_meta = {
        "odds_freshness_status": FreshnessStatus.STALE_ODDS.value,
        "requires_fresh_odds": True,
        "odds_freshness_class": "ODDS_STALE",
        "odds_snapshot_at": _iso(_utc_now() - timedelta(hours=4)),
    }
    with (
        patch("worldcup_predictor.odds.refresh_gate._freshness_for_row", side_effect=[stale_meta, stale_meta]),
        patch(
            "worldcup_predictor.odds.refresh_gate.validate_legitimate_1x2_snapshot",
            side_effect=[(True, None, {"valid": True}), (True, None, {"valid": True})],
        ),
        patch(
            "worldcup_predictor.odds.refresh_gate.refresh_live_odds",
            return_value={
                "success": True,
                "provider_request_success": True,
                "refresh_success": True,
                "refresh_imported_rows": 1,
                "provider": "api-football",
                "attempts": [],
            },
        ),
    ):
        out = ensure_fresh_odds_before_prediction(conn, row, daily, refresh_if_needed=True)
    assert out["refresh_success"] is True
    assert out["allowed"] is False
    assert out["final_block_reason"] == "STALE_ODDS_AFTER_REFRESH"


def test_provider_failure_classified_separately():
    row = {
        "fixture_id": 1494692,
        "home_team": "Aalesund",
        "away_team": "Molde",
        "kickoff_utc": (_utc_now() + timedelta(hours=2)).isoformat(),
        "competition_key": "eliteserien",
        "status": "NS",
    }
    daily = DailyFixture(
        fixture_id=1494692,
        provider_fixture_id=1494692,
        competition_key="eliteserien",
        home_team="Aalesund",
        away_team="Molde",
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
            return_value={"success": False, "provider_request_success": False, "attempts": []},
        ),
        patch("worldcup_predictor.odds.refresh_gate.get_settings") as gs,
    ):
        gs.return_value.api_football_configured = True
        gs.return_value.sportmonks_configured = False
        out = ensure_fresh_odds_before_prediction(conn, row, daily, refresh_if_needed=True)
    assert out["refresh_success"] is False
    assert out["final_block_reason"] == "STALE_ODDS_REFRESH_FAILED"


def test_diagnostics_no_secrets():
    from worldcup_predictor.odds.refresh_gate import _build_block_diagnostics

    diag = _build_block_diagnostics(
        row={"fixture_id": 1, "home_team": "A", "away_team": "B", "kickoff_utc": "x", "competition_key": "c"},
        freshness={"odds_freshness_status": "STALE_ODDS", "explanation": "stale"},
        refresh_result={"attempts": [{"provider": "api-football", "error": "key=SECRET123"}]},
        final_block_reason="STALE_ODDS_AFTER_REFRESH",
        legitimate={"home_odds": 2.0},
    )
    blob = json.dumps(diag)
    assert "SECRET123" not in blob
    assert "api_key" not in blob.lower()


def test_wde_not_called_when_freshness_invalid():
    from worldcup_predictor.mcp_server import runtime as mcp_runtime

    with (
        patch.object(mcp_runtime, "connect") as connect_mock,
        patch.object(mcp_runtime, "ensure_ecse_live_tables"),
        patch.object(mcp_runtime, "_fixture_row", return_value={"fixture_id": 1, "home_team": "A", "away_team": "B", "kickoff_utc": "x", "competition_key": "c", "status": "NS"}),
        patch.object(mcp_runtime, "_to_daily_fixture"),
        patch.object(
            mcp_runtime,
            "ensure_fresh_odds_before_prediction",
            return_value={"allowed": False, "final_block_reason": "STALE_ODDS_AFTER_REFRESH", "freshness": {}, "diagnostics": {}},
        ),
        patch.object(mcp_runtime, "_run_wde_prediction", create=True) as wde,
    ):
        connect_mock.return_value.__enter__ = lambda s: s
        connect_mock.return_value.close = lambda: None
        out = mcp_runtime.run_fixture_prediction(1, refresh_if_stale=False)
    assert out["quality"]["status"] == "BLOCKED"
    if wde.called:
        pytest.fail("WDE should not run when freshness invalid")
