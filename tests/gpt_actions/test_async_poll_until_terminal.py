"""Tests for GPT Actions async poll-until-terminal semantics."""

from __future__ import annotations

import time
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from worldcup_predictor.gpt_actions.app import create_app
from worldcup_predictor.gpt_actions.config import GptActionsConfig
from worldcup_predictor.gpt_actions.job_status import (
    COMPLETED_RESULT_MISSING,
    CONTINUATION_CODE,
    build_job_status_fields,
    is_terminal_status,
    should_poll_again,
)
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture


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
        poll_after_seconds=2,
    )


@pytest.fixture
def client(test_config):
    return TestClient(create_app(test_config), raise_server_exceptions=False)


def _auth_headers(**extra):
    return {"Authorization": "Bearer test-gpt-actions-key", **extra}


def _daily_fixture(fixture_id: int = 1494202) -> DailyFixture:
    return DailyFixture(
        fixture_id=fixture_id,
        provider_fixture_id=fixture_id,
        competition_key="allsvenskan",
        home_team="Djurgardens IF",
        away_team="Halmstad",
        kickoff_utc="2026-07-13T17:00:00+00:00",
        status="NS",
        season=2026,
    )


def _full_mock_result(fixture_id: int = 1494202) -> dict:
    return {
        "fixture": {
            "fixture_id": fixture_id,
            "home_team": "Djurgardens IF",
            "away_team": "Halmstad",
            "kickoff_utc": "2026-07-13T17:00:00+00:00",
            "competition": "allsvenskan",
        },
        "odds": {"provider": "api-football", "freshness": "FRESH_ODDS", "bookmaker_count": 12},
        "wde": {
            "prediction": "home_win",
            "decision_pick": "home_win",
            "effective_pick": "home_win",
            "probability_argmax": "home_win",
            "confidence": 61.8,
            "home_probability": 88.1,
            "draw_probability": 8.6,
            "away_probability": 3.3,
            "wde_execution_status": "executed",
            "model_version": "wde-v1",
        },
        "btts": {"prediction": "no", "btts_execution_status": "executed"},
        "over_under_2_5": {"prediction": "over_2_5", "ou_execution_status": "executed"},
        "ecse": {
            "top_scores": [
                {"rank": i, "score": s, "probability": 0.1 - i * 0.01}
                for i, s in enumerate(["3-0", "2-0", "4-0", "1-0", "5-0"], 1)
            ],
        },
        "quality": {"status": "OK", "warnings": []},
    }


def _sync_enqueue(job_id, *, store, config):
    from worldcup_predictor.gpt_actions.worker import execute_prediction_job

    execute_prediction_job(job_id, store=store, config=config)


@contextmanager
def _mock_owner_job(fixture_id: int = 1494202):
    patches = [
        patch("worldcup_predictor.gpt_actions.worker.enqueue_prediction_job", side_effect=_sync_enqueue),
        patch("worldcup_predictor.gpt_actions.worker.connect"),
        patch("worldcup_predictor.gpt_actions.delegation.connect"),
        patch("worldcup_predictor.gpt_actions.worker._fixture_from_db", return_value=_daily_fixture(fixture_id)),
        patch(
            "worldcup_predictor.gpt_actions.worker.controlled_owner_odds_lookup",
            return_value={"odds_found": True},
        ),
        patch(
            "worldcup_predictor.gpt_actions.worker.mcp_runtime.run_fixture_prediction",
            return_value=_full_mock_result(fixture_id),
        ),
        patch("worldcup_predictor.gpt_actions.worker.filter_matches_by_odds", return_value={"matches": []}),
        patch("worldcup_predictor.gpt_actions.worker.freeze_tier_b_shadow_prediction"),
        patch(
            "worldcup_predictor.gpt_actions.delegation._match_odds",
            return_value={"home": 1.5, "draw": 4.0, "away": 5.0, "bookmaker_count": 10},
        ),
    ]
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
        yield


def _owner_body(fixture_id: int = 1494202, **extra) -> dict:
    body = {
        "date": "2026-07-13",
        "fixture_ids": [fixture_id],
        "scope": "owner",
        "prediction_scope": "owner_shadow",
        "include_all_predictions": True,
    }
    body.update(extra)
    return body


def test_terminal_helpers():
    assert should_poll_again("queued") is True
    assert should_poll_again("running") is True
    assert should_poll_again("completed") is False
    assert is_terminal_status("completed") is True
    assert is_terminal_status("running") is False


def test_completed_null_result_rejected():
    fields = build_job_status_fields(
        {
            "job_id": "x",
            "status": "completed",
            "created_at": "t",
            "updated_at": "t",
            "result": None,
            "error": None,
        },
        poll_after_seconds=3,
    )
    assert fields["status"] == "failed"
    assert fields["error"] == COMPLETED_RESULT_MISSING
    assert fields["terminal"] is True
    assert fields["should_poll_again"] is False


def test_create_returns_job_id_and_non_terminal(client):
    with _mock_owner_job():
        resp = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json=_owner_body(),
            headers=_auth_headers(),
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["job_id"]
    assert data["terminal"] is False
    assert data["should_poll_again"] is True
    assert data["poll_after_seconds"] == 2
    assert data["continuation_code"] == CONTINUATION_CODE


def test_running_response_is_non_terminal(client):
    with _mock_owner_job():
        created = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json=_owner_body(include_all_predictions=False),
            headers=_auth_headers(),
        )
    job_id = created.json()["job_id"]
    poll = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers())
    if poll.json()["status"] == "running":
        assert poll.json()["terminal"] is False
        assert poll.json()["should_poll_again"] is True
        assert poll.json()["result"] is None
        assert poll.json()["polling_message"]


def test_poll_until_completed_same_job_id(client):
    with _mock_owner_job():
        created = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json=_owner_body(),
            headers=_auth_headers(),
        )
    job_id = created.json()["job_id"]
    deadline = time.time() + 5
    final = None
    polls = 0
    while time.time() < deadline:
        poll = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers())
        polls += 1
        final = poll.json()
        assert final["job_id"] == job_id
        if final["terminal"]:
            break
        assert final["should_poll_again"] is True
        assert final["result"] is None
        time.sleep(0.15)
    assert final is not None
    assert final["status"] in ("completed", "partial")
    assert final["terminal"] is True
    assert final["should_poll_again"] is False
    assert final["result"] is not None
    assert polls >= 1


def test_completed_result_stable_on_repeat_get(client):
    with _mock_owner_job():
        created = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json=_owner_body(include_all_predictions=False),
            headers=_auth_headers(),
        )
    job_id = created.json()["job_id"]
    deadline = time.time() + 5
    while time.time() < deadline:
        poll = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers())
        if poll.json().get("terminal"):
            break
        time.sleep(0.15)
    first = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers()).json()
    second = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers()).json()
    assert first["result"] == second["result"]
    assert first["status"] == second["status"]


def test_completed_payload_has_required_fields(client):
    with _mock_owner_job():
        created = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json=_owner_body(),
            headers=_auth_headers(),
        )
    job_id = created.json()["job_id"]
    deadline = time.time() + 5
    final = None
    while time.time() < deadline:
        poll = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers())
        if poll.json().get("terminal"):
            final = poll.json()
            break
        time.sleep(0.15)
    assert final and final["result"]
    pred = final["result"]["predictions"][0]
    assert pred["wde"]["wde_execution_status"] == "executed"
    assert pred["wde"]["decision_pick"]
    assert pred["wde"]["probability_argmax"]
    assert pred["btts"]["btts_execution_status"] == "executed"
    assert pred["over_under_2_5"]["ou_execution_status"] == "executed"
    assert pred["ecse"]["top1"]
    assert pred["ecse"]["top5"]
    assert pred["data_quality"] == "OK"
    assert pred["quality"] == "OK"


def test_failed_job_terminal_with_error(client):
    with patch("worldcup_predictor.gpt_actions.worker.filter_matches_by_odds", return_value={"matches": []}):
        created = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json={"date": "2026-07-13", "filter": {"home_odds_gt": 99}},
            headers=_auth_headers(),
        )
    job_id = created.json()["job_id"]
    deadline = time.time() + 5
    while time.time() < deadline:
        poll = client.get(f"/api/gpt-actions/v1/prediction-jobs/{job_id}", headers=_auth_headers())
        if poll.json().get("terminal"):
            final = poll.json()
            assert final["status"] == "failed"
            assert final["error"]
            assert final["should_poll_again"] is False
            assert "API_FOOTBALL" not in str(final)
            return
        time.sleep(0.15)
    pytest.fail("expected failed terminal job")


def test_idempotent_active_job_reuses_same_id(client):
    with _mock_owner_job(1508807):
        first = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json=_owner_body(1508807),
            headers=_auth_headers(**{"Idempotency-Key": "poll-terminal-1"}),
        )
        job_id = first.json()["job_id"]
        second = client.post(
            "/api/gpt-actions/v1/prediction-jobs",
            json=_owner_body(1508807),
            headers=_auth_headers(**{"Idempotency-Key": "poll-terminal-1"}),
        )
    assert second.json()["job_id"] == job_id


def test_openapi_documents_polling():
    from pathlib import Path

    text = Path("docs/gpt_actions/worldcup_predictor_actions.openapi.yaml").read_text(encoding="utf-8")
    assert "should_poll_again" in text
    assert "terminal" in text
    assert "Poll the SAME job_id" in text


def test_owner_instructions_require_terminal_polling():
    from pathlib import Path

    text = Path("docs/gpt_actions/CUSTOM_GPT_OWNER_INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "should_poll_again" in text
    assert "terminal=true" in text
    assert "result=null" in text
