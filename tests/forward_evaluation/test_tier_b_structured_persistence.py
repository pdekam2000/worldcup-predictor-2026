"""Tier B structured forward-evaluation persistence tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from worldcup_predictor.forward_evaluation.bridge import maybe_capture_after_prediction_persistence
from worldcup_predictor.forward_evaluation.bridge import ForwardEvalBridgeContext
from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze
from worldcup_predictor.forward_evaluation.tier_b_persistence import (
    TIER_B_SCOPE,
    finalize_tier_b_structured_persistence,
    read_tier_b_structured_record,
    resolve_tier_b_bridge_context,
    stamp_structured_scope,
    verify_tier_b_record,
    TierBPersistenceContext,
)
from tests.forward_evaluation.conftest import seed_tier_a_fixture, seed_tier_b_fixture


@pytest.fixture
def patch_git_sha():
    with patch(
        "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
        return_value={"current_git_sha": "abc123def456", "git_sha_source": "git_head"},
    ):
        yield


def _freeze_tier_b(prod_db, eval_db, patch_git_sha, fixture_id: int = 900002):
    create_or_reuse_freeze(
        fixture_id,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "validation_tier": "B", "public_visible": False},
    )


def test_tier_b_wsp_and_ecse_exist(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    wsp = prod_db.execute("SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=900002").fetchone()
    ecse = prod_db.execute("SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=900002").fetchone()
    assert wsp and ecse


def test_tier_b_freeze_persists(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    result = _freeze_tier_b(prod_db, eval_db, patch_git_sha)
    row = eval_db.execute(
        "SELECT prediction_scope, public_visible, validation_tier FROM frozen_predictions WHERE fixture_id=900002"
    ).fetchone()
    assert row["prediction_scope"] == "owner_shadow"
    assert int(row["public_visible"]) == 0
    assert row["validation_tier"] == "B"


def test_tier_b_rankings_persist(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    fr = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    ranks = eval_db.execute(
        "SELECT COUNT(*) c FROM exact_score_rankings WHERE prediction_id=?",
        (fr["freeze_id"],),
    ).fetchone()["c"]
    assert ranks == 5


def test_stamp_structured_scope(prod_db):
    seed_tier_b_fixture(prod_db)
    stamp_structured_scope(
        prod_db,
        900002,
        prediction_scope=TIER_B_SCOPE,
        validation_tier="B",
        source_runtime="mcp",
    )
    row = prod_db.execute(
        "SELECT prediction_scope, validation_tier, source_runtime FROM worldcup_stored_predictions WHERE fixture_id=900002"
    ).fetchone()
    assert row["prediction_scope"] == TIER_B_SCOPE
    assert row["validation_tier"] == "B"
    assert row["source_runtime"] == "mcp"


def test_resolve_tier_b_bridge_context_defaults(prod_db):
    ctx = resolve_tier_b_bridge_context("allsvenskan", bridge_origin="mcp")
    assert ctx.prediction_scope == TIER_B_SCOPE
    assert ctx.validation_tier == "B"
    assert ctx.public_visible is False


def test_resolve_tier_a_bridge_context(prod_db):
    ctx = resolve_tier_b_bridge_context("world_cup_2026", bridge_origin="mcp")
    assert ctx.prediction_scope == "production"
    assert ctx.validation_tier == "A"


def test_finalize_structured_persistence(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    fr = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    meta = finalize_tier_b_structured_persistence(
        900002,
        prod_conn=prod_db,
        persistence_ctx=TierBPersistenceContext(
            fixture_id=900002,
            source_runtime="gpt_actions",
        ),
        forward_evaluation={"freeze_id": fr["freeze_id"], "content_hash": fr["content_hash"]},
    )
    assert meta["status"] == "complete"
    assert meta["verification_pass"] is True
    assert meta["prediction_scope"] == TIER_B_SCOPE
    assert meta["public_visible"] is False


def test_read_structured_record_fields(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    stamp_structured_scope(prod_db, 900002, prediction_scope=TIER_B_SCOPE, validation_tier="B", source_runtime="mcp")
    record = read_tier_b_structured_record(900002, prod_conn=prod_db, eval_conn=eval_db)
    assert record
    assert record["wde_decision"]
    assert record["ft_marginal_direction"]
    assert record["probability_home"] is not None
    assert record["probability_draw"] is not None
    assert record["probability_away"] is not None
    assert record["btts_selection"]
    assert record["ou_2_5_selection"]
    assert record["ecse_top1"]
    assert record["ecse_top5"]
    assert record["top3_mass"] is not None
    assert record["top5_mass"] is not None
    assert record["odds_freshness_status"]
    assert record["data_quality"] is not None
    assert len(record["exact_score_rankings"]) == 5


def test_idempotent_freeze_reuse(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    a = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    b = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    assert b["status"] == "reused"
    assert a["freeze_id"] == b["freeze_id"]
    count = eval_db.execute("SELECT COUNT(*) c FROM frozen_predictions WHERE fixture_id=900002").fetchone()["c"]
    assert count == 1


def test_no_duplicate_rankings(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    fr = eval_db.execute("SELECT prediction_id FROM frozen_predictions WHERE fixture_id=900002").fetchone()
    count = eval_db.execute(
        "SELECT COUNT(*) c FROM exact_score_rankings WHERE prediction_id=?",
        (fr["prediction_id"],),
    ).fetchone()["c"]
    assert count == 5


def test_stable_content_hash(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    a = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    b = create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    assert a["content_hash"] == b["content_hash"]


def test_tier_a_unchanged(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(
        900001,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": "production", "validation_tier": "A", "public_visible": True},
    )
    row = eval_db.execute(
        "SELECT validation_tier, prediction_scope FROM frozen_predictions WHERE prediction_id=?",
        (result["freeze_id"],),
    ).fetchone()
    assert row["validation_tier"] == "A"
    assert row["prediction_scope"] == "production"


def test_bridge_owner_shadow_scope(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    bridge = maybe_capture_after_prediction_persistence(
        900002,
        prod_conn=prod_db,
        bridge_context=ForwardEvalBridgeContext(
            prediction_scope=TIER_B_SCOPE,
            validation_tier="B",
            public_visible=False,
            bridge_origin="mcp",
        ),
        quality_status="OK",
        ecse_snapshot_id=1,
    )
    assert bridge.status in ("created", "reused")
    assert bridge.prediction_scope == TIER_B_SCOPE


def test_verify_record_fails_without_freeze(prod_db, eval_db):
    seed_tier_b_fixture(prod_db)
    record = read_tier_b_structured_record(900002, prod_conn=prod_db, eval_conn=eval_db)
    ok, issues = verify_tier_b_record(record)
    assert ok is False
    assert any("freeze" in i or "content_hash" in i for i in issues)


def test_partial_component_unavailable(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    prod_db.execute(
        """
        UPDATE worldcup_stored_predictions
        SET payload_json = json_set(payload_json, '$.extended_markets', json('{}'))
        WHERE fixture_id = 900002
        """
    )
    prod_db.commit()
    create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    record = read_tier_b_structured_record(900002, prod_conn=prod_db, eval_conn=eval_db)
    assert record["btts_execution_status"] == "UNAVAILABLE"
    assert record["ou_execution_status"] == "UNAVAILABLE"


def test_public_visible_false_enforced(prod_db, eval_db, patch_git_sha):
    seed_tier_b_fixture(prod_db)
    create_or_reuse_freeze(
        900002,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": TIER_B_SCOPE, "public_visible": False},
    )
    record = read_tier_b_structured_record(900002, prod_conn=prod_db, eval_conn=eval_db)
    ok, _ = verify_tier_b_record(record)
    assert record["public_visible"] is False
