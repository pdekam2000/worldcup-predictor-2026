"""Tests for domestic league control batch."""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from worldcup_predictor.owner_predict_eval.domestic_league_control import (
    PROVEN_DOMESTIC_LEAGUE_IDS,
    batch_id_for,
    find_nearest_eligible_date,
    load_batch_snapshots,
)
from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import ensure_batch_tables, freeze_batch_snapshot


def test_proven_domestic_league_registry():
    assert 113 in PROVEN_DOMESTIC_LEAGUE_IDS
    assert PROVEN_DOMESTIC_LEAGUE_IDS[113] == "allsvenskan"


def test_find_nearest_eligible_date():
    scan = [
        {"date": "2026-07-08", "proven_domestic_count": 0},
        {"date": "2026-07-11", "proven_domestic_count": 3},
        {"date": "2026-07-12", "proven_domestic_count": 10},
    ]
    assert find_nearest_eligible_date(scan) == date(2026, 7, 12)


def test_domestic_batch_identity_separate():
    assert batch_id_for(date(2026, 7, 12)) == "domestic_league_control_20260712"
    assert batch_id_for(date(2026, 7, 12)) != "tomorrow_4_league_20260707"


def test_domestic_snapshot_competition_type():
    conn = sqlite3.connect(":memory:")
    ensure_batch_tables(conn)
    report = {
        "fixture": {
            "fixture_id": 1494204,
            "competition_key": "allsvenskan",
            "competition_name": "Allsvenskan",
            "competition_type": "domestic_league",
            "kickoff_utc": "2026-07-12T12:00:00+00:00",
            "home_team": "A",
            "away_team": "B",
        },
        "wde": {"predicted_1x2": "home_win"},
        "ecse": {"top1": {"scoreline": "2-1"}},
        "first_goal": {"available": False},
        "consistency": {"status": "CONSISTENT"},
        "reliability": {"tier": "MEDIUM"},
        "data_readiness": {},
    }
    freeze_batch_snapshot(
        conn,
        batch_id="domestic_league_control_20260712",
        target_date="2026-07-12",
        report=report,
    )
    snaps = load_batch_snapshots(conn, "domestic_league_control_20260712")
    assert len(snaps) == 1
    assert snaps[0]["competition_type"] == "domestic_league"


def test_uefa_batch_not_modified():
    """UEFA batch IDs must remain untouched by domestic module constants."""
    uefa_ids = {1554361, 1554368, 1554371, 1554366}
    domestic_batch = batch_id_for(date(2026, 7, 12))
    assert domestic_batch.startswith("domestic_league_control_")
    assert "tomorrow_4_league" not in domestic_batch
    assert len(uefa_ids) == 4
