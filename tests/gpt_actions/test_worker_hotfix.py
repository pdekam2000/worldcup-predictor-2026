"""Regression tests for prediction worker tier fix and broad listing."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from worldcup_predictor.gpt_actions.app import create_app
from worldcup_predictor.gpt_actions.config import GptActionsConfig
from worldcup_predictor.gpt_actions.owner_scope import fixture_allowed_for_prediction, fixture_tier
from worldcup_predictor.gpt_actions.worker import _per_fixture_prediction_scope, execute_prediction_job
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture


@pytest.fixture
def test_config(tmp_path):
    return GptActionsConfig(
        host="127.0.0.1",
        port=8771,
        api_key="test-hotfix-key",
        audit_log_path=str(tmp_path / "audit.jsonl"),
        job_store_dir=str(tmp_path / "jobs"),
        max_jobs_retained=10,
        rate_limit_per_minute=1000,
        max_fixture_ids_per_job=5,
        max_response_chars=95000,
        poll_after_seconds=1,
    )


def _auth():
    return {"Authorization": "Bearer test-hotfix-key"}


def test_tier_resolved_before_eligibility():
    """Tier must be bound before fixture_allowed_for_prediction uses it."""
    comp_a = "world_cup_2026"
    comp_b = "veikkausliiga"
    tier_a = fixture_tier(comp_a)
    tier_b = fixture_tier(comp_b)
    assert tier_a == "A"
    assert tier_b == "B"
    ok_a, _ = fixture_allowed_for_prediction(comp_a, prediction_scope=_per_fixture_prediction_scope("owner", tier_a))
    ok_b, _ = fixture_allowed_for_prediction(comp_b, prediction_scope=_per_fixture_prediction_scope("owner", tier_b))
    assert ok_a is True
    assert ok_b is True
    ok_b_prod, reason = fixture_allowed_for_prediction(comp_b, prediction_scope="production")
    assert ok_b_prod is False
    assert reason == "tier_b_requires_owner_shadow_scope"


def test_worker_tier_a_production_job_completes(test_config, tmp_path):
    store = JobStore(test_config.job_store_dir)
    record = store.create(
        payload={
            "date": "2026-07-10",
            "fixture_ids": [1581821],
            "prediction_scope": "production",
            "include_all_predictions": True,
        }
    )
    job_id = record["job_id"]
    daily = DailyFixture(
        fixture_id=1581821,
        provider_fixture_id=1581821,
        competition_key="world_cup_2026",
        home_team="Spain",
        away_team="Belgium",
        kickoff_utc="2026-07-10T19:00:00",
        status="NS",
        season=2026,
    )
    mock_result = {
        "fixture": {"fixture_id": 1581821, "home_team": "Spain", "away_team": "Belgium", "kickoff_utc": "t"},
        "odds": {},
        "wde": {"prediction": "draw", "confidence": 51.7, "probability_argmax": "home_win"},
        "btts": {"prediction": "yes"},
        "over_under_2_5": {"prediction": "under_2_5"},
        "ecse": {"top_scores": [{"rank": 1, "score": "2-0", "probability": 0.14}]},
        "quality": {"status": "OK", "warnings": []},
    }
    with patch("worldcup_predictor.gpt_actions.worker._fixture_from_db", return_value=daily):
        with patch("worldcup_predictor.gpt_actions.worker.mcp_runtime.run_fixture_prediction", return_value=mock_result):
            with patch("worldcup_predictor.gpt_actions.worker.connect") as mock_conn:
                with patch("worldcup_predictor.gpt_actions.delegation.connect", mock_conn):
                    mock_conn.return_value = MagicMock()
                    execute_prediction_job(job_id, store=store, config=test_config)
    record = store.get(job_id)
    assert record["status"] in ("completed", "partial")
    assert record.get("error") is None
    assert (record.get("result") or {}).get("accepted_count") == 1


def test_worker_tier_b_owner_shadow_job(test_config):
    store = JobStore(test_config.job_store_dir)
    record = store.create(
        payload={
            "date": "2026-07-10",
            "fixture_ids": [1494204],
            "prediction_scope": "owner_shadow",
            "include_all_predictions": True,
        }
    )
    job_id = record["job_id"]
    daily = DailyFixture(
        fixture_id=1494204,
        provider_fixture_id=1494204,
        competition_key="veikkausliiga",
        home_team="VPS",
        away_team="SJK",
        kickoff_utc="2026-07-10T15:00:00",
        status="NS",
        season=2026,
    )
    mock_result = {
        "fixture": {"fixture_id": 1494204, "home_team": "VPS", "away_team": "SJK"},
        "odds": {},
        "wde": {"prediction": "home_win", "confidence": 45},
        "btts": {},
        "over_under_2_5": {},
        "ecse": {"top_scores": []},
        "quality": {"status": "PARTIAL", "warnings": []},
    }
    odds_meta = {"odds_found": True, "home": 2.1, "draw": 3.2, "away": 3.5, "bookmaker_count": 5}
    with patch("worldcup_predictor.gpt_actions.worker._fixture_from_db", return_value=daily):
        with patch("worldcup_predictor.gpt_actions.worker.controlled_owner_odds_lookup", return_value=odds_meta):
            with patch("worldcup_predictor.gpt_actions.worker.mcp_runtime.run_fixture_prediction", return_value=mock_result):
                with patch("worldcup_predictor.gpt_actions.worker.freeze_tier_b_shadow_prediction"):
                    with patch("worldcup_predictor.gpt_actions.worker.connect") as mock_conn:
                        with patch("worldcup_predictor.gpt_actions.delegation.connect", mock_conn):
                            mock_conn.return_value = MagicMock()
                            execute_prediction_job(job_id, store=store, config=test_config)
    record = store.get(job_id)
    assert record["status"] in ("completed", "partial")
    assert record.get("error") is None


def test_worker_rejects_friendlies(test_config):
    store = JobStore(test_config.job_store_dir)
    record = store.create(payload={"date": "2026-07-10", "fixture_ids": [999001], "prediction_scope": "owner"})
    job_id = record["job_id"]
    daily = DailyFixture(
        fixture_id=999001,
        provider_fixture_id=999001,
        competition_key="league_667",
        home_team="A",
        away_team="B",
        kickoff_utc="2026-07-10T12:00:00",
        status="NS",
        season=None,
    )
    with patch("worldcup_predictor.gpt_actions.worker._fixture_from_db", return_value=daily):
        with patch("worldcup_predictor.gpt_actions.worker.connect") as mock_conn:
            with patch("worldcup_predictor.gpt_actions.delegation.connect", mock_conn):
                mock_conn.return_value = MagicMock()
                execute_prediction_job(job_id, store=store, config=test_config)
    record = store.get(job_id)
    assert record["status"] == "failed"
    rejected = (record.get("result") or {}).get("rejected") or []
    assert any(r.get("reason") == "friendlies_unsupported" for r in rejected)


def test_broad_listing_includes_unsupported_and_friendly():
    from worldcup_predictor.gpt_actions.broad_fixture_discovery import classify_broad_record

    friendly = classify_broad_record(
        {
            "fixture_id": 1,
            "home_team": "A",
            "away_team": "B",
            "competition_key": "league_667",
            "kickoff_utc": "2026-07-10T12:00:00",
            "status": "NS",
            "coverage_sources": ["api_football"],
        }
    )
    assert friendly["prediction_support_status"] == "FRIENDLY"

    unsupported = classify_broad_record(
        {
            "fixture_id": 2,
            "home_team": "C",
            "away_team": "D",
            "competition_key": "league_99999",
            "kickoff_utc": "2026-07-10T13:00:00",
            "status": "NS",
            "coverage_sources": ["api_football"],
        }
    )
    assert unsupported["prediction_support_status"] == "NO_PREDICTION_SUPPORT"


def test_list_route_uses_broad_discovery(test_config):
    app = create_app(test_config)
    client = TestClient(app, raise_server_exceptions=False)
    mock_broad = {
        "date": "2026-07-10",
        "timezone": "Europe/Vienna",
        "mode": "broad_listing",
        "audit": {"provider_raw_count": 216, "deduplicated_count": 200},
        "count": 3,
        "tier_a_count": 1,
        "tier_b_count": 1,
        "friendly_count": 1,
        "unsupported_count": 0,
        "matches": [
            {"fixture_id": 1, "validation_tier": "A", "listing_status": "TRUSTED"},
            {"fixture_id": 2, "validation_tier": "B", "listing_status": "TEST_PHASE"},
            {"fixture_id": 3, "listing_status": "FRIENDLY", "prediction_support_status": "FRIENDLY"},
        ],
    }
    with patch("worldcup_predictor.gpt_actions.broad_fixture_discovery.discover_broad_fixtures", return_value=mock_broad):
        resp = client.get(
            "/api/gpt-actions/v1/matches/list",
            params={"date": "2026-07-10"},
            headers=_auth(),
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "broad_listing"
    assert body["count"] == 3
    assert body.get("audit", {}).get("provider_raw_count") == 216


def test_prediction_job_same_id_polling(test_config):
    app = create_app(test_config)
    client = TestClient(app, raise_server_exceptions=False)
    body = {"date": "2026-07-10", "fixture_ids": [1581821], "include_all_predictions": True}
    mock_result = {
        "fixture": {"fixture_id": 1581821, "home_team": "Spain", "away_team": "Belgium"},
        "odds": {},
        "wde": {"prediction": "draw", "confidence": 51.7},
        "btts": {},
        "over_under_2_5": {},
        "ecse": {"top_scores": [{"rank": 1, "score": "2-0", "probability": 0.14}]},
        "quality": {"status": "OK", "warnings": []},
    }
    daily = DailyFixture(
        fixture_id=1581821,
        provider_fixture_id=1581821,
        competition_key="world_cup_2026",
        home_team="Spain",
        away_team="Belgium",
        kickoff_utc="2026-07-10T19:00:00",
        status="NS",
        season=2026,
    )
    with patch("worldcup_predictor.gpt_actions.worker._fixture_from_db", return_value=daily):
        with patch("worldcup_predictor.gpt_actions.worker.mcp_runtime.run_fixture_prediction", return_value=mock_result):
            with patch("worldcup_predictor.gpt_actions.worker.connect") as mock_conn:
                with patch("worldcup_predictor.gpt_actions.delegation.connect", mock_conn):
                    mock_conn.return_value = MagicMock()
                    created = client.post("/api/gpt-actions/v1/prediction-jobs", json=body, headers=_auth())
                    assert created.status_code == 202
                    job_id = created.json()["job_id"]
                    deadline = time.time() + 5
                    final = None
                    while time.time() < deadline:
                        poll = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth())
                        final = poll.json()
                        if final["status"] in ("completed", "partial", "failed"):
                            break
                        time.sleep(0.2)
    assert final is not None
    assert final["status"] in ("completed", "partial")
    assert final.get("error") is None
