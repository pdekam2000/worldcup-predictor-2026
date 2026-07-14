"""Integration tests for forward evaluation freeze service."""

from __future__ import annotations

from unittest.mock import patch

from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze
from worldcup_predictor.forward_evaluation.repository import ForwardEvalRepository
from tests.forward_evaluation.conftest import seed_tier_a_fixture


@patch(
    "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
    return_value={"current_git_sha": "integration123", "git_sha_source": "git_head"},
)
def test_full_integration_flow(mock_sha, prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=910001)
    repo = ForwardEvalRepository(eval_db)

    created = create_or_reuse_freeze(910001, prod_conn=prod_db, eval_conn=eval_db)
    assert created["status"] == "created"
    assert created["source_prediction_id"] == 910001
    assert created["source_ecse_snapshot_id"] == 1

    row = repo.fetch_by_id(created["freeze_id"])
    assert row is not None
    assert row["worldcup_stored_prediction_id"] == 910001
    assert row["ecse_snapshot_id"] == 1
    assert row["wde_decision"] == "home_win"
    assert row["ft_marginal_direction"] == "home_win"
    assert row["immutable"] == 1

    ranks = eval_db.execute(
        "SELECT rank, score FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
        (created["freeze_id"],),
    ).fetchall()
    assert len(ranks) == 5

    reused = create_or_reuse_freeze(910001, prod_conn=prod_db, eval_conn=eval_db)
    assert reused["status"] == "reused"
    assert reused["freeze_id"] == created["freeze_id"]

    canonical = repo.fetch_canonical_freeze(910001, prediction_scope="owner_daily")
    assert canonical["prediction_id"] == created["freeze_id"]


@patch(
    "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
    return_value={"current_git_sha": "integration123", "git_sha_source": "git_head"},
)
def test_conflict_and_serialization(mock_sha, prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=910002)
    repo = ForwardEvalRepository(eval_db)

    first = create_or_reuse_freeze(910002, prod_conn=prod_db, eval_conn=eval_db)
    eval_db.execute(
        "UPDATE frozen_predictions SET content_hash='tampered', payload_hash='tampered' WHERE prediction_id=?",
        (first["freeze_id"],),
    )
    eval_db.commit()

    conflict = create_or_reuse_freeze(910002, prod_conn=prod_db, eval_conn=eval_db)
    assert conflict["status"] == "conflict"
    assert conflict["reason_code"] == "SOURCE_PAYLOAD_CONFLICT"

    q = eval_db.execute(
        "SELECT reason FROM freeze_quarantine WHERE fixture_id=910002 AND reason='SOURCE_PAYLOAD_CONFLICT'"
    ).fetchone()
    assert q is not None

    row = repo.fetch_by_id(first["freeze_id"])
    assert row["wde_decision"] == "home_win"
    assert row["complete_payload_json"]
    payload = row["complete_payload_json"]
    assert "wde" in payload
