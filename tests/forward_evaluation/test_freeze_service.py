"""Unit tests for canonical forward evaluation freeze service."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze
from worldcup_predictor.forward_evaluation.hashing import canonical_json, content_hash
from worldcup_predictor.forward_evaluation.repository import ForwardEvalRepository
from tests.forward_evaluation.conftest import seed_tier_a_fixture, seed_tier_b_fixture


@pytest.fixture
def patch_git_sha():
    with patch(
        "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
        return_value={"current_git_sha": "abc123def456", "git_sha_source": "git_head"},
    ):
        yield


def test_valid_wsp_ecse_creates_freeze(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["status"] == "created"
    assert result["created"] is True
    assert result["freeze_id"]


def test_repeated_call_reuses_freeze(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    first = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    second = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert second["status"] == "reused"
    assert second["reused"] is True
    assert second["freeze_id"] == first["freeze_id"]


def test_no_duplicate_row(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    count = eval_db.execute("SELECT COUNT(*) c FROM frozen_predictions WHERE fixture_id=900001").fetchone()["c"]
    assert count == 1


def test_stable_content_hash(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    a = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    eval_db.execute("DELETE FROM frozen_predictions")
    eval_db.commit()
    b = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert a["content_hash"] == b["content_hash"]


def test_stable_source_payload_hash(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    a = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    b = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert a["source_payload_hash"] == b["source_payload_hash"]


def test_wsp_fixture_mismatch_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(
        900001,
        prod_conn=prod_db,
        eval_conn=eval_db,
        worldcup_stored_prediction_id=999999,
    )
    assert result["status"] == "rejected"
    assert result["reason_code"] == "MISSING_WSP"


def test_ecse_fixture_mismatch_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    prod_db.execute("UPDATE ecse_prediction_snapshots SET fixture_id=999999 WHERE id=1")
    prod_db.commit()
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db, ecse_snapshot_id=1)
    assert result["reason_code"] == "FIXTURE_ID_MISMATCH"


def test_kickoff_mismatch_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    prod_db.execute(
        "UPDATE worldcup_stored_predictions SET kickoff_utc='2099-01-01T12:00:00+00:00' WHERE fixture_id=900001"
    )
    prod_db.commit()
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["reason_code"] == "KICKOFF_MISMATCH"


def test_post_kickoff_wsp_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db, post_kickoff_predicted=True, kickoff_days_ahead=0.01)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["reason_code"] in {"POST_KICKOFF_GENERATION", "POST_KICKOFF_CAPTURE"}


def test_post_kickoff_ecse_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db, kickoff_days_ahead=0.01, predicted_days_ahead=-0.5)
    prod_db.execute(
        "UPDATE ecse_prediction_snapshots SET generated_at='2099-01-01T12:00:00+00:00' WHERE fixture_id=900001"
    )
    prod_db.commit()
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["reason_code"] == "POST_KICKOFF_GENERATION"


def test_missing_generated_timestamp_quarantined(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    prod_db.execute("UPDATE ecse_prediction_snapshots SET generated_at='' WHERE fixture_id=900001")
    prod_db.execute("UPDATE worldcup_stored_predictions SET predicted_at='' WHERE fixture_id=900001")
    prod_db.commit()
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["status"] == "quarantined"
    assert result.get("reason_code") == "MISSING_GENERATED_TIMESTAMP"


def test_missing_wde_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db, missing_wde=True)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["reason_code"] == "WDE_PAYLOAD_MISSING"


def test_missing_ecse_top5_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db, missing_ecse_top5=True)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["reason_code"] == "ECSE_TOP5_MISSING"


def test_missing_btts_probability_allowed(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    prod_db.execute(
        "UPDATE worldcup_stored_predictions SET payload_json = json_set(payload_json, '$.extended_markets.btts', json('{\"prediction\":\"yes\"}')) WHERE fixture_id=900001"
    )
    prod_db.commit()
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["status"] in {"created", "quarantined", "reused"}


def test_missing_ou_probability_allowed(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    prod_db.execute(
        "UPDATE worldcup_stored_predictions SET payload_json = json_set(payload_json, '$.extended_markets.over_under_25', json('{\"prediction\":\"over\"}')) WHERE fixture_id=900001"
    )
    prod_db.commit()
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["status"] in {"created", "quarantined", "reused"}


def test_tier_a_scope_preserved(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    row = eval_db.execute("SELECT validation_tier, prediction_scope FROM frozen_predictions WHERE prediction_id=?", (result["freeze_id"],)).fetchone()
    assert row["validation_tier"] == "A"
    assert row["prediction_scope"] == "owner_daily"


def test_tier_b_owner_shadow_preserved(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    result = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": "owner_shadow"},
    )
    row = eval_db.execute(
        "SELECT validation_tier, prediction_scope FROM frozen_predictions WHERE prediction_id=?",
        (result["freeze_id"],),
    ).fetchone()
    assert row["validation_tier"] == "B"
    assert row["prediction_scope"] == "owner_shadow"


def test_tier_b_public_visible_false(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    result = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": "owner_shadow"},
    )
    row = eval_db.execute("SELECT public_visible FROM frozen_predictions WHERE prediction_id=?", (result["freeze_id"],)).fetchone()
    assert row["public_visible"] == 0


def test_invalid_public_tier_b_rejected(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    result = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": "owner_shadow", "public_visible": True},
    )
    assert result["reason_code"] == "INVALID_PUBLIC_VISIBILITY"


def test_different_legitimate_version_preserved(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    first = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    row = prod_db.execute("SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=900001").fetchone()
    payload = json.loads(row["payload_json"])
    payload["probabilities"]["home_win"] = 0.61
    payload["confidence_score"] = 71.0
    prod_db.execute(
        "UPDATE worldcup_stored_predictions SET payload_json=? WHERE fixture_id=900001",
        (json.dumps(payload),),
    )
    prod_db.commit()
    second = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert first["freeze_id"] != second["freeze_id"]
    count = eval_db.execute("SELECT COUNT(*) c FROM frozen_predictions WHERE fixture_id=900001").fetchone()["c"]
    assert count == 2


def test_mutated_payload_same_source_ids_conflicts(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    first = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    eval_db.execute(
        "UPDATE frozen_predictions SET content_hash='deadbeef', payload_hash='deadbeef' WHERE prediction_id=?",
        (first["freeze_id"],),
    )
    eval_db.commit()
    second = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert second["status"] == "conflict"


def test_immutable_payload_cannot_be_updated(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    repo = ForwardEvalRepository(eval_db)
    with pytest.raises(ValueError, match="immutable_payload_update_blocked"):
        repo.update_mutable_fields(result["freeze_id"], {"wde_decision": "away_win"})


def test_evaluation_status_can_be_updated(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    repo = ForwardEvalRepository(eval_db)
    assert repo.update_evaluation_status(result["freeze_id"], "EVALUATED")
    row = eval_db.execute("SELECT evaluation_status FROM frozen_predictions WHERE prediction_id=?", (result["freeze_id"],)).fetchone()
    assert row["evaluation_status"] == "EVALUATED"


@patch("requests.get")
@patch("requests.post")
def test_no_provider_client_invoked(mock_post, mock_get, prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    mock_get.assert_not_called()
    mock_post.assert_not_called()


@patch("worldcup_predictor.mcp_server.runtime.run_fixture_prediction")
def test_no_prediction_engine_invoked(mock_run, prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    mock_run.assert_not_called()


@patch("worldcup_predictor.odds.freshness_metadata.build_fixture_freshness_metadata")
def test_no_odds_refresh_invoked(mock_fresh, prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    mock_fresh.assert_not_called()


def test_json_canonicalization_deterministic():
    a = canonical_json({"b": 2, "a": 1})
    b = canonical_json({"a": 1, "b": 2})
    assert a == b
    assert content_hash({"x": 1, "y": 2}) == content_hash({"y": 2, "x": 1})


def test_source_commit_sha_stored(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    row = eval_db.execute("SELECT source_commit_sha FROM frozen_predictions WHERE prediction_id=?", (result["freeze_id"],)).fetchone()
    assert row["source_commit_sha"] == "abc123def456"


def test_model_versions_stored(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    row = eval_db.execute(
        "SELECT wde_model_version, ecse_model_version FROM frozen_predictions WHERE prediction_id=?",
        (result["freeze_id"],),
    ).fetchone()
    assert row["wde_model_version"] == "WDE-v9"
    assert row["ecse_model_version"] == "ECSE-v3"


def test_migration_preserves_existing_rows(eval_db):
    eval_db.execute(
        """
        INSERT INTO frozen_predictions (
            prediction_id, batch_id, fixture_id, match_name, competition, tier, kickoff,
            generated_at, frozen_at, payload_hash, evaluation_status, ecse_top5_complete
        ) VALUES ('legacy-id', 'LEGACY', 1, 'A vs B', 'world_cup_2026', 'A', '2026-07-01T12:00:00+00:00',
                  '2026-06-30T12:00:00+00:00', '2026-06-30T12:00:00+00:00', 'abc', 'PENDING', 1)
        """
    )
    eval_db.commit()
    from worldcup_predictor.forward_evaluation.db import ensure_schema

    ensure_schema(eval_db)
    row = eval_db.execute("SELECT prediction_id FROM frozen_predictions WHERE prediction_id='legacy-id'").fetchone()
    assert row is not None
