"""Integration tests — owner_daily, MCP, GPT Actions bridge paths."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

from worldcup_predictor.forward_evaluation.bridge import ForwardEvalBridgeResult
from worldcup_predictor.gpt_actions.delegation import format_fixture_evidence
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.predictions import run_daily_predictions
from tests.forward_evaluation.conftest import seed_tier_a_fixture


@pytest.fixture
def patch_git_sha():
    with patch(
        "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
        return_value={"current_git_sha": "bridge123", "git_sha_source": "git_head"},
    ):
        yield


def _fixture(fixture_id: int = 930001) -> DailyFixture:
    return DailyFixture(
        fixture_id=fixture_id,
        provider_fixture_id=fixture_id,
        competition_key="world_cup_2026",
        home_team="Alpha FC",
        away_team="Beta FC",
        kickoff_utc="2026-08-01T18:00:00+00:00",
        status="NS",
        season=2026,
    )


def test_owner_daily_bridge_attaches_metadata(prod_db, eval_db, patch_git_sha, tmp_path):
    import sqlite3 as _sqlite3

    db_path = tmp_path / "owner_bridge.db"
    conn = _sqlite3.connect(str(db_path))
    conn.row_factory = _sqlite3.Row
    from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL

    conn.execute(
        """
        CREATE TABLE fixtures (
            fixture_id INTEGER PRIMARY KEY,
            competition_key TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            status TEXT,
            season INTEGER,
            league_id INTEGER,
            is_placeholder INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE worldcup_stored_predictions (
            fixture_id INTEGER PRIMARY KEY,
            competition_key TEXT,
            kickoff_utc TEXT,
            payload_json TEXT,
            source TEXT,
            predicted_at TEXT,
            updated_at TEXT,
            is_active INTEGER DEFAULT 1,
            is_quarantined INTEGER DEFAULT 0
        )
        """
    )
    for ddl in PHASE_ECSE_LIVE_DDL:
        conn.execute(ddl)
    conn.commit()
    seed_tier_a_fixture(conn, fixture_id=930001)

    class _Settings:
        sqlite_path = str(db_path)

    bridge_result = ForwardEvalBridgeResult(
        status="created",
        fixture_id=930001,
        freeze_id="freeze-test",
        created=True,
        source_prediction_id=930001,
        source_ecse_snapshot_id=1,
        bridge_origin="owner_daily",
        prediction_scope="owner_daily",
    )

    with patch("worldcup_predictor.owner_daily.predictions.get_settings", return_value=_Settings()):
        with patch("worldcup_predictor.owner_daily.predictions.connect", return_value=conn):
            with patch("worldcup_predictor.owner_daily.predictions.run_daily_wde", return_value=("generated", {"fixture_id": 930001})):
                with patch(
                    "worldcup_predictor.owner_daily.predictions.run_daily_ecse",
                    return_value=("generated", {"fixture_id": 930001, "snapshot_id": 1}),
                ):
                    with patch(
                        "worldcup_predictor.forward_evaluation.bridge.maybe_capture_after_prediction_persistence",
                        return_value=bridge_result,
                    ):
                        result = run_daily_predictions([_fixture()], dry_run=False, force=True)
    assert result.forward_eval_captures
    assert result.forward_eval_captures[0]["freeze_id"] == "freeze-test"


@patch("worldcup_predictor.owner_daily.predictions.run_daily_wde")
@patch("worldcup_predictor.owner_daily.predictions.run_daily_ecse")
def test_owner_daily_dry_run_skips_bridge(mock_ecse, mock_wde, prod_db, eval_db, patch_git_sha):
    mock_wde.return_value = ("generated", {"fixture_id": 930002})
    mock_ecse.return_value = ("generated", {"fixture_id": 930002, "snapshot_id": 1})
    with patch("worldcup_predictor.forward_evaluation.bridge.maybe_capture_after_prediction_persistence") as mock_bridge:
        result = run_daily_predictions([_fixture(930002)], dry_run=True, force=True)
        mock_bridge.assert_not_called()
    assert result.forward_eval_captures == []


def test_mcp_runtime_attaches_forward_evaluation(prod_db, eval_db, patch_git_sha):
    from worldcup_predictor.mcp_server import runtime as mcp_runtime

    seed_tier_a_fixture(prod_db, fixture_id=930003)
    row = {
        "fixture_id": 930003,
        "competition_key": "world_cup_2026",
        "home_team": "Alpha FC",
        "away_team": "Beta FC",
        "kickoff_utc": "2026-08-01T18:00:00+00:00",
        "status": "NS",
        "season": 2026,
    }
    bridge_result = ForwardEvalBridgeResult(
        status="created",
        fixture_id=930003,
        freeze_id="mcp-freeze",
        created=True,
        source_prediction_id=930003,
        source_ecse_snapshot_id=1,
    )

    with patch.object(mcp_runtime, "bootstrap_gpt_actions_runtime"):
        with patch.object(mcp_runtime, "connect", return_value=prod_db):
            with patch.object(mcp_runtime, "_fixture_row", return_value=row):
                with patch.object(mcp_runtime, "ensure_fresh_odds_before_prediction", return_value={"allowed": True}):
                    with patch.object(mcp_runtime, "_freshness_record", return_value={"odds_status": "FRESH"}):
                        with patch.object(mcp_runtime, "run_daily_wde", return_value=("generated", {"wde_execution_status": "executed"})):
                            with patch.object(mcp_runtime, "run_daily_ecse", return_value=("generated", {"snapshot_id": 1})):
                                with patch.object(mcp_runtime, "_load_stored_payload", return_value={"probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2}, "effective_1x2": {"pick": "home_win"}}):
                                    with patch("worldcup_predictor.research.ecse_live.store.get_snapshot") as mock_snap:
                                        mock_snap.return_value = {"id": 1, "top_5_scores": [{"rank": i, "scoreline": f"{i}-0", "probability": 0.1} for i in range(1, 6)], "top_10_scorelines": [], "generated_at": "2026-07-01T10:00:00+00:00", "model_version": "ECSE-v3", "lambda_home": 1.4, "lambda_away": 1.1}
                                        with patch(
                                            "worldcup_predictor.forward_evaluation.bridge.maybe_capture_after_prediction_persistence",
                                            return_value=bridge_result,
                                        ):
                                            out = mcp_runtime.run_fixture_prediction(
                                                930003,
                                                refresh_if_stale=False,
                                                bridge_context={"prediction_scope": "production", "bridge_origin": "mcp"},
                                            )
    assert out["forward_evaluation"]["freeze_id"] == "mcp-freeze"


def test_gpt_evidence_includes_forward_evaluation_block():
    raw = {
        "fixture": {"fixture_id": 1, "home_team": "A", "away_team": "B", "kickoff_utc": "2026-08-01T18:00:00+00:00"},
        "wde": {"decision_pick": "home_win", "probability_argmax": "home_win", "wde_execution_status": "executed"},
        "btts": {},
        "over_under_2_5": {},
        "ecse": {"top_scores": [{"rank": 1, "score": "1-0", "probability": 0.1}]},
        "quality": {"status": "OK"},
        "forward_evaluation": {
            "capture_status": "created",
            "freeze_id": "freeze-1",
            "evaluation_ready": "pending_result",
        },
    }
    evidence = format_fixture_evidence(raw, timezone="Europe/Vienna")
    assert evidence["forward_evaluation"]["freeze_id"] == "freeze-1"


def test_gpt_worker_passes_bridge_context():
    import inspect
    from worldcup_predictor.gpt_actions import worker

    src = inspect.getsource(worker.execute_prediction_job)
    assert "bridge_context" in src
    assert "source_job_id" in src
    assert "maybe_capture_after_prediction_persistence" not in src
