"""Tests for prediction-to-freeze bridge."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from worldcup_predictor.forward_evaluation.bridge import (
    ForwardEvalBridgeContext,
    ForwardEvalBridgeResult,
    capture_forward_eval_freeze_from_stored,
    forward_evaluation_metadata_block,
    maybe_capture_after_prediction_persistence,
)
from tests.forward_evaluation.conftest import seed_tier_a_fixture, seed_tier_b_fixture


@pytest.fixture
def patch_git_sha():
    with patch(
        "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
        return_value={"current_git_sha": "bridge123", "git_sha_source": "git_head"},
    ):
        yield


def test_metadata_block_created_status():
    block = forward_evaluation_metadata_block(
        ForwardEvalBridgeResult(
            status="created",
            fixture_id=1,
            freeze_id="abc",
            created=True,
            source_prediction_id=1,
            source_ecse_snapshot_id=1,
        )
    )
    assert block["capture_status"] == "created"
    assert block["evaluation_ready"] == "pending_result"
    assert block["freeze_id"] == "abc"


def test_metadata_block_quarantined_not_ready():
    block = forward_evaluation_metadata_block(
        ForwardEvalBridgeResult(status="quarantined", fixture_id=1, quarantined=True, reason_code="X")
    )
    assert block["evaluation_ready"] is None


def test_capture_skipped_missing_wsp(prod_db, eval_db):
    result = maybe_capture_after_prediction_persistence(
        999999,
        prod_conn=prod_db,
        bridge_context=ForwardEvalBridgeContext(bridge_origin="owner_daily"),
    )
    assert result.status == "skipped"
    assert result.reason_code == "MISSING_WSP"


def test_capture_skipped_missing_ecse(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=920001)
    prod_db.execute("DELETE FROM ecse_prediction_snapshots WHERE fixture_id=920001")
    prod_db.commit()
    result = maybe_capture_after_prediction_persistence(
        920001,
        prod_conn=prod_db,
        bridge_context=ForwardEvalBridgeContext(bridge_origin="owner_daily"),
    )
    assert result.reason_code == "MISSING_ECSE"


def test_capture_after_persistence_creates_freeze(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db, fixture_id=920002)
    result = maybe_capture_after_prediction_persistence(
        920002,
        prod_conn=prod_db,
        bridge_context=ForwardEvalBridgeContext(
            prediction_scope="owner_daily",
            bridge_origin="owner_daily",
            ecse_snapshot_id=1,
        ),
    )
    assert result.status in {"created", "quarantined"}
    assert result.source_prediction_id == 920002
    assert result.source_ecse_snapshot_id == 1


def test_capture_reuses_on_repeat(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db, fixture_id=920003)
    ctx = ForwardEvalBridgeContext(prediction_scope="owner_daily", bridge_origin="owner_daily", ecse_snapshot_id=1)
    first = maybe_capture_after_prediction_persistence(920003, prod_conn=prod_db, bridge_context=ctx)
    second = maybe_capture_after_prediction_persistence(920003, prod_conn=prod_db, bridge_context=ctx)
    assert second.status == "reused"
    assert second.freeze_id == first.freeze_id


def test_tier_b_public_visible_false(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db, fixture_id=920004)
    result = maybe_capture_after_prediction_persistence(
        920004,
        prod_conn=prod_db,
        bridge_context=ForwardEvalBridgeContext(
            prediction_scope="owner_shadow",
            public_visible=False,
            bridge_origin="gpt_actions",
            ecse_snapshot_id=1,
        ),
    )
    assert result.status in {"created", "quarantined", "reused"}


@patch("worldcup_predictor.forward_evaluation.bridge.create_or_reuse_freeze")
def test_facade_delegates_to_freeze_service(mock_freeze, prod_db, eval_db):
    mock_freeze.return_value = {"status": "created", "fixture_id": 1, "freeze_id": "x"}
    out = capture_forward_eval_freeze_from_stored(
        920002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": "owner_daily"},
    )
    assert out["status"] == "created"
    mock_freeze.assert_called_once()


@patch("requests.get")
@patch("requests.post")
def test_no_provider_calls_in_bridge(mock_post, mock_get, prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db, fixture_id=920005)
    maybe_capture_after_prediction_persistence(
        920005,
        prod_conn=prod_db,
        bridge_context=ForwardEvalBridgeContext(bridge_origin="mcp", ecse_snapshot_id=1),
    )
    mock_get.assert_not_called()
    mock_post.assert_not_called()
