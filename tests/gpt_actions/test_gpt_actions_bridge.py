"""Phase 4 GPT Actions bridge tests."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from worldcup_predictor.gpt_actions.app import create_app
from worldcup_predictor.gpt_actions.config import GptActionsConfig
from worldcup_predictor.gpt_actions.delegation import format_fixture_evidence, rank_best_matches
from worldcup_predictor.gpt_actions.policies import validate_timezone
from worldcup_predictor.gpt_actions.server import dry_test


@pytest.fixture
def test_config(tmp_path):
    return GptActionsConfig(
        host="127.0.0.1",
        port=8770,
        api_key="test-gpt-actions-key",
        audit_log_path=str(tmp_path / "audit.jsonl"),
        job_store_dir=str(tmp_path / "jobs"),
        max_jobs_retained=10,
        rate_limit_per_minute=1000,
        max_fixture_ids_per_job=5,
        max_response_chars=95000,
        poll_after_seconds=1,
    )


@pytest.fixture
def client(test_config):
    app = create_app(test_config)
    return TestClient(app, raise_server_exceptions=False)


def _auth_headers(**extra):
    return {"Authorization": "Bearer test-gpt-actions-key", **extra}


def test_dry_test_manifest():
    manifest = dry_test()
    assert manifest["route_count"] == 7
    assert manifest["bind_localhost_only"] is True


def test_authentication_success(client):
    with patch("worldcup_predictor.gpt_actions.delegation.get_system_status", return_value={"service": "ok"}):
        resp = client.get("/api/gpt-actions/v1/system/status", headers=_auth_headers())
    assert resp.status_code == 200


def test_authentication_failure(client):
    resp = client.get("/api/gpt-actions/v1/system/status", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_query_string_api_key_rejected(client):
    resp = client.get(
        "/api/gpt-actions/v1/system/status?api_key=leak",
        headers={"Authorization": "Bearer test-gpt-actions-key"},
    )
    assert resp.status_code == 400


def test_rate_limit(client, test_config):
    test_config_low = GptActionsConfig(
        host=test_config.host,
        port=test_config.port,
        api_key=test_config.api_key,
        audit_log_path=test_config.audit_log_path,
        job_store_dir=test_config.job_store_dir,
        max_jobs_retained=test_config.max_jobs_retained,
        rate_limit_per_minute=2,
        max_fixture_ids_per_job=test_config.max_fixture_ids_per_job,
        max_response_chars=test_config.max_response_chars,
        poll_after_seconds=test_config.poll_after_seconds,
    )
    limited = TestClient(create_app(test_config_low), raise_server_exceptions=False)
    with patch("worldcup_predictor.gpt_actions.delegation.get_system_status", return_value={"service": "ok"}):
        assert limited.get("/api/gpt-actions/v1/system/status", headers=_auth_headers()).status_code == 200
        assert limited.get("/api/gpt-actions/v1/system/status", headers=_auth_headers()).status_code == 200
        third = limited.get("/api/gpt-actions/v1/system/status", headers=_auth_headers())
    assert third.status_code == 429


def test_invalid_date(client):
    resp = client.get(
        "/api/gpt-actions/v1/matches/discover",
        params={"date": "2026/07/09"},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_invalid_timezone():
    with pytest.raises(ValueError):
        validate_timezone("Not/A/Timezone")


def test_invalid_odds_filter(client):
    resp = client.post(
        "/api/gpt-actions/v1/matches/filter-odds",
        json={"date": "2026-07-09", "filter": {"home_odds_gt": 500}},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_duplicate_idempotency_key(client):
    body = {
        "date": "2026-07-09",
        "timezone": "Europe/Vienna",
        "fixture_ids": [12345],
        "include_all_predictions": True,
    }
    mock_result = {
        "fixture": {"fixture_id": 12345, "home_team": "A", "away_team": "B", "kickoff_utc": "t", "competition": "c"},
        "odds": {"provider": "p", "freshness": "fresh"},
        "wde": {"prediction": "home_win", "confidence": 55},
        "btts": {},
        "over_under_2_5": {},
        "ecse": {"top_scores": [{"rank": 1, "score": "1-0", "probability": 0.1}]},
        "quality": {"status": "OK", "warnings": []},
    }
    with patch("worldcup_predictor.gpt_actions.worker.mcp_runtime.run_fixture_prediction", return_value=mock_result):
        with patch("worldcup_predictor.gpt_actions.worker.filter_matches_by_odds", return_value={"matches": []}):
            first = client.post(
                "/api/gpt-actions/v1/prediction-jobs",
                json=body,
                headers=_auth_headers(**{"Idempotency-Key": "dup-key-1"}),
            )
            assert first.status_code == 202
            job_id = first.json()["job_id"]
            time.sleep(0.5)
            second = client.post(
                "/api/gpt-actions/v1/prediction-jobs",
                json=body,
                headers=_auth_headers(**{"Idempotency-Key": "dup-key-1"}),
            )
    assert second.status_code in (200, 202)
    assert second.json()["job_id"] == job_id


def test_job_state_transition(client):
    body = {"date": "2026-07-09", "fixture_ids": [999], "include_all_predictions": True}
    mock_result = {
        "fixture": {"fixture_id": 999, "home_team": "H", "away_team": "A"},
        "odds": {},
        "wde": {"prediction": "draw", "confidence": 40},
        "btts": {},
        "over_under_2_5": {},
        "ecse": {"top_scores": []},
        "quality": {"status": "PARTIAL", "warnings": ["ecse_snapshot_missing"]},
    }
    with patch("worldcup_predictor.gpt_actions.worker.mcp_runtime.run_fixture_prediction", return_value=mock_result):
        created = client.post("/api/gpt-actions/v1/prediction-jobs", json=body, headers=_auth_headers())
        job_id = created.json()["job_id"]
        deadline = time.time() + 3
        final = None
        while time.time() < deadline:
            resp = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers())
            final = resp.json()
            if final["status"] in ("completed", "partial", "failed"):
                break
            time.sleep(0.2)
    assert final is not None
    assert final["status"] in ("partial", "completed", "failed")


def test_completed_job_response_structure():
    predictions = [
        {
            "fixture_id": 1,
            "match": "A vs B",
            "quality": "OK",
            "wde": {"confidence": 70, "effective_pick": "home_win"},
            "ecse": {"top1": {"rank": 1, "score": "2-1"}},
        }
    ]
    ranked = rank_best_matches(predictions, select_best=1)
    assert len(ranked["best_3"]) == 1
    assert ranked["all_match_ranking"][0]["fixture_id"] == 1


def test_top1_top5_ordering():
    mcp_result = {
        "fixture": {"fixture_id": 1, "home_team": "X", "away_team": "Y"},
        "odds": {"provider": "api", "freshness": "fresh"},
        "wde": {"prediction": "home_win", "confidence": 60},
        "btts": {"prediction": "yes"},
        "over_under_2_5": {"prediction": "over"},
        "ecse": {
            "top_scores": [
                {"rank": 1, "score": "2-1", "probability": 0.12},
                {"rank": 2, "score": "1-0", "probability": 0.10},
                {"rank": 3, "score": "1-1", "probability": 0.09},
                {"rank": 4, "score": "2-0", "probability": 0.08},
                {"rank": 5, "score": "0-0", "probability": 0.07},
            ]
        },
        "quality": {"status": "OK", "warnings": []},
    }
    with patch("worldcup_predictor.gpt_actions.delegation.connect") as mock_connect:
        mock_conn = mock_connect.return_value
        mock_conn.close = lambda: None
        with patch(
                "worldcup_predictor.gpt_actions.delegation._match_odds",
                return_value={"home": 2.5, "draw": 3.2, "away": 2.8, "bookmaker_count": 3},
            ):
                evidence = format_fixture_evidence(mcp_result, timezone="Europe/Vienna")
    assert evidence["ecse"]["top1"]["score"] == "2-1"
    assert evidence["ecse"]["top5"]["score"] == "0-0"


def test_canonical_pipeline_delegation():
    import inspect

    from worldcup_predictor.gpt_actions import delegation

    src = inspect.getsource(delegation.run_predictions_for_fixtures)
    assert "mcp_runtime.run_fixture_prediction" in src


def test_no_mcp_public_exposure():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    text = (root / "deployment" / "nginx" / "gpt-actions-snippet.conf").read_text(encoding="utf-8")
    assert "8765" not in text
    assert "location /mcp" in text


def test_oversized_fixture_list_rejected(client):
    ids = list(range(1, 25))
    resp = client.post(
        "/api/gpt-actions/v1/prediction-jobs",
        json={"date": "2026-07-09", "fixture_ids": ids},
        headers=_auth_headers(),
    )
    assert resp.status_code == 422


def test_failed_job_response(client):
    with patch("worldcup_predictor.gpt_actions.worker.filter_matches_by_odds", return_value={"matches": []}):
        resp = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json={"date": "2026-07-09", "filter": {"home_odds_gt": 99}},
            headers=_auth_headers(),
        )
        job_id = resp.json()["job_id"]
        deadline = time.time() + 3
        while time.time() < deadline:
            poll = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers())
            if poll.json()["status"] == "failed":
                assert poll.json()["error"]
                return
            time.sleep(0.2)
    pytest.fail("expected failed job")
