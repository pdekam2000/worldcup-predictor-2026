"""Phase 2D — result sync and forward market evaluation tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from worldcup_predictor.forward_evaluation.constants import (
    HIT,
    MISS,
    NOT_EVALUATED_UNAVAILABLE,
)
from worldcup_predictor.forward_evaluation.evaluate import evaluate_frozen_prediction
from worldcup_predictor.forward_evaluation.evaluation_service import evaluate_frozen_prediction as evaluate_fixture
from worldcup_predictor.forward_evaluation.freeze_integrity import verify_freeze_integrity
from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze
from worldcup_predictor.forward_evaluation.result_record import RESULT_QUALITY_CONFLICT
from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture
from worldcup_predictor.forward_evaluation.results import sync_actual_result
from tests.forward_evaluation.conftest import seed_fixture_result, seed_tier_a_fixture, seed_tier_b_fixture


@pytest.fixture
def patch_git_sha():
    with patch(
        "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
        return_value={"current_git_sha": "abc123", "git_sha_source": "test"},
    ):
        yield


def _freeze(
    prod_db,
    eval_db,
    fixture_id,
    *,
    scope="production",
    tier="A",
    public=True,
    seed_fixture=True,
):
    if seed_fixture:
        if tier == "B" or scope == "owner_shadow":
            seed_tier_b_fixture(prod_db, fixture_id=fixture_id)
        else:
            seed_tier_a_fixture(
                prod_db, fixture_id=fixture_id, kickoff_days_ahead=2.0, predicted_days_ahead=1.0
            )
        # Keep fixture / WSP / ECSE kickoffs identical (ISO UTC). Do not use SQLite
        # datetime('now',...) on fixtures alone — that causes KICKOFF_MISMATCH rejects
        # and intermittent missing freeze_id (see flaky_test_root_cause.md).
        from datetime import datetime, timedelta, timezone

        kickoff = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        predicted = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        prod_db.execute(
            "UPDATE fixtures SET kickoff_utc=?, status='NS' WHERE fixture_id=?",
            (kickoff, fixture_id),
        )
        prod_db.execute(
            "UPDATE worldcup_stored_predictions SET kickoff_utc=?, predicted_at=?, updated_at=? WHERE fixture_id=?",
            (kickoff, predicted, predicted, fixture_id),
        )
        prod_db.execute(
            "UPDATE ecse_prediction_snapshots SET kickoff_utc=?, generated_at=? WHERE fixture_id=?",
            (kickoff, predicted, fixture_id),
        )
        prod_db.commit()
    ctx = {
        "prediction_scope": scope,
        "validation_tier": tier,
        "public_visible": public,
    }
    fr = create_or_reuse_freeze(fixture_id, prod_conn=prod_db, eval_conn=eval_db, source_context=ctx)
    assert fr.get("freeze_id"), (
        f"freeze missing freeze_id for fixture={fixture_id}: "
        f"status={fr.get('status')} reason={fr.get('reason_code')} payload={fr}"
    )
    # After successful prematch freeze, mark fixture finished for result-sync helpers.
    prod_db.execute(
        "UPDATE fixtures SET kickoff_utc=datetime('now','-2 days'), status='FT' WHERE fixture_id=?",
        (fixture_id,),
    )
    prod_db.commit()
    return fr


def _prepare_finished_fixture(prod_db, eval_db, fixture_id, *, home=2, away=1, scope="production", tier="A", public=True):
    fr = _freeze(prod_db, eval_db, fixture_id, scope=scope, tier=tier, public=public)
    seed_fixture_result(prod_db, fixture_id=fixture_id, home_goals=home, away_goals=away)
    return fr


def test_confirmed_result_sync_inserts(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900010, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    seed_fixture_result(prod_db, fixture_id=900010, home_goals=2, away_goals=1)
    out = sync_result_for_fixture(900010, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    assert out["result_available"] is True
    assert out["inserted"] is True
    row = eval_db.execute("SELECT * FROM actual_results WHERE fixture_id=900010").fetchone()
    assert row is not None
    assert row["actual_score"] == "2-1"


def test_repeated_result_sync_idempotent(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900011, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    seed_fixture_result(prod_db, fixture_id=900011, home_goals=1, away_goals=1)
    a = sync_result_for_fixture(900011, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    b = sync_result_for_fixture(900011, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    assert a["inserted"] is True
    assert b["reused"] is True
    count = eval_db.execute("SELECT COUNT(*) c FROM actual_results WHERE fixture_id=900011").fetchone()["c"]
    assert count == 1


def test_postponed_fixture_blocks(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900012, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    prod_db.execute("UPDATE fixtures SET status='PST' WHERE fixture_id=900012")
    prod_db.commit()
    out = sync_result_for_fixture(900012, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    assert out["result_available"] is False


def test_valid_freeze_evaluates(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900020, home=2, away=0)
    sync_actual_result(eval_db, prod_db, 900020)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["evaluated"] is True
    row = eval_db.execute(
        "SELECT wde_hit FROM market_evaluations WHERE prediction_id=?",
        (fr["freeze_id"],),
    ).fetchone()
    assert row is not None


def test_missing_freeze_blocks(prod_db, eval_db):
    out = evaluate_fixture(999999, prod_conn=prod_db, eval_conn=eval_db, skip_result_sync=True)
    assert out["evaluated"] is False
    assert out["reason"] == "FREEZE_MISSING"


def test_wde_hit_and_miss(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900021, home=2, away=0)
    sync_actual_result(eval_db, prod_db, 900021)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["wde_hit"] in (HIT, MISS)


def test_unavailable_btts_not_wrong(prod_db, eval_db, patch_git_sha):
    fr = _freeze(prod_db, eval_db, 900022, scope="owner_shadow", tier="B", public=False)
    eval_db.execute(
        "UPDATE frozen_predictions SET btts_execution_status='UNAVAILABLE', ou_execution_status='UNAVAILABLE' WHERE prediction_id=?",
        (fr["freeze_id"],),
    )
    eval_db.commit()
    seed_fixture_result(prod_db, fixture_id=900022, home_goals=1, away_goals=1)
    sync_actual_result(eval_db, prod_db, 900022)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["btts_hit"] == NOT_EVALUATED_UNAVAILABLE
    assert out["ou25_hit"] == NOT_EVALUATED_UNAVAILABLE


def test_ecse_top_hits(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900023, home=1, away=0)
    sync_actual_result(eval_db, prod_db, 900023)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["ecse_top1_hit"] in (HIT, MISS)


def test_evaluation_idempotent(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900024, home=1, away=0)
    sync_actual_result(eval_db, prod_db, 900024)
    a = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    b = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert a["evaluated"] is True
    assert b["evaluated"] is False
    assert b["reason"] == "already_evaluated"


def test_tier_b_owner_only(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(
        prod_db, eval_db, 900025, home=0, away=0, scope="owner_shadow", tier="B", public=False
    )
    sync_actual_result(eval_db, prod_db, 900025)
    out = evaluate_fixture(900025, prod_conn=prod_db, eval_conn=eval_db, skip_result_sync=True)
    assert out.get("eligibility_class") == "OWNER_ONLY" or out.get("public_visible") == 0


def test_freeze_integrity_post_kickoff_blocks(prod_db, eval_db, patch_git_sha):
    fr = _freeze(prod_db, eval_db, 900026, seed_fixture=True)
    eval_db.execute(
        """
        UPDATE frozen_predictions
        SET kickoff=datetime('now','-2 days'), frozen_at=datetime('now','+1 day')
        WHERE prediction_id=?
        """,
        (fr["freeze_id"],),
    )
    eval_db.commit()
    integrity = verify_freeze_integrity(eval_db, prod_db, prediction_id=fr["freeze_id"])
    assert integrity["ok"] is False


def test_dry_run_no_writes(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900027, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    seed_fixture_result(prod_db, fixture_id=900027, home_goals=1, away_goals=0)
    out = sync_result_for_fixture(
        900027, prod_conn=prod_db, eval_conn=eval_db, dry_run=True, allow_provider_fetch=False
    )
    assert out["status"] == "dry_run"
    assert eval_db.execute("SELECT 1 FROM actual_results WHERE fixture_id=900027").fetchone() is None


def test_conflicting_regulation_score_blocks(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900030, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    seed_fixture_result(prod_db, fixture_id=900030, home_goals=2, away_goals=1)
    prod_db.execute(
        """
        UPDATE fixture_results
        SET regulation_home_goals=3, regulation_away_goals=0,
            match_outcome_type='FT', final_stage='FT'
        WHERE fixture_id=900030
        """
    )
    prod_db.commit()
    out = sync_result_for_fixture(900030, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    assert out["conflict"] is True
    assert out["safe_to_store"] is False
    assert out["result_quality_status"] == RESULT_QUALITY_CONFLICT


def test_et_pen_uses_regulation_score(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900032, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    seed_fixture_result(prod_db, fixture_id=900032, home_goals=1, away_goals=1, status="PEN")
    prod_db.execute(
        """
        UPDATE fixture_results
        SET regulation_home_goals=1, regulation_away_goals=1,
            match_outcome_type='PEN', final_stage='PEN'
        WHERE fixture_id=900032
        """
    )
    prod_db.commit()
    out = sync_result_for_fixture(900032, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    assert out["regulation_score"] == "1-1"
    assert out["result_available"] is True


def test_missing_regulation_score_blocks(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900031, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    seed_fixture_result(prod_db, fixture_id=900031, home_goals=1, away_goals=0)
    prod_db.execute(
        """
        UPDATE fixture_results
        SET regulation_home_goals=NULL, regulation_away_goals=NULL,
            home_goals=NULL, away_goals=NULL, final_score=NULL
        WHERE fixture_id=900031
        """
    )
    prod_db.commit()
    out = sync_result_for_fixture(900031, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    assert out["result_available"] is False


@pytest.mark.parametrize(
    "home,away,pred,expected",
    [
        (2, 1, "yes", HIT),
        (2, 0, "yes", MISS),
        (0, 0, "no", HIT),
    ],
)
def test_btts_evaluation(prod_db, eval_db, patch_git_sha, home, away, pred, expected):
    fid = 900040 + home * 10 + away
    fr = _prepare_finished_fixture(prod_db, eval_db, fid, home=home, away=away)
    eval_db.execute(
        "UPDATE frozen_predictions SET btts_prediction=? WHERE prediction_id=?",
        (pred, fr["freeze_id"]),
    )
    eval_db.commit()
    sync_actual_result(eval_db, prod_db, fid)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["btts_hit"] == expected


@pytest.mark.parametrize(
    "home,away,pred,expected",
    [
        (2, 1, "over", HIT),
        (1, 0, "under", HIT),
        (1, 1, "over", MISS),
    ],
)
def test_ou_evaluation(prod_db, eval_db, patch_git_sha, home, away, pred, expected):
    fid = 900050 + home * 10 + away
    fr = _prepare_finished_fixture(prod_db, eval_db, fid, home=home, away=away)
    eval_db.execute(
        "UPDATE frozen_predictions SET ou25_prediction=? WHERE prediction_id=?",
        (pred, fr["freeze_id"]),
    )
    eval_db.commit()
    sync_actual_result(eval_db, prod_db, fid)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["ou25_hit"] == expected


def test_ft_marginal_evaluated_separately(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900060, home=1, away=1)
    sync_actual_result(eval_db, prod_db, 900060)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["ft_marginal_hit"] in (HIT, MISS)
    assert out["wde_hit"] in (HIT, MISS)


def test_ecse_outside_top5(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900061, home=9, away=9)
    sync_actual_result(eval_db, prod_db, 900061)
    out = evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    assert out["actual_score_rank"] == "OUTSIDE_TOP5"
    assert out["ecse_top5_hit"] == MISS


def test_result_provenance_stored(prod_db, eval_db):
    seed_tier_a_fixture(prod_db, fixture_id=900062, kickoff_days_ahead=-2.0, predicted_days_ahead=-3.0)
    seed_fixture_result(prod_db, fixture_id=900062, home_goals=1, away_goals=0)
    sync_result_for_fixture(900062, prod_conn=prod_db, eval_conn=eval_db, allow_provider_fetch=False)
    row = eval_db.execute("SELECT provider, result_content_hash FROM actual_results WHERE fixture_id=900062").fetchone()
    assert row["provider"] == "test"
    assert row["result_content_hash"]


def test_evaluation_provenance_stored(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900063, home=1, away=0)
    sync_actual_result(eval_db, prod_db, 900063)
    evaluate_frozen_prediction(eval_db, prediction_id=fr["freeze_id"], prod_conn=prod_db)
    row = eval_db.execute(
        "SELECT evaluation_version, evaluator_source, content_hash FROM market_evaluations WHERE prediction_id=?",
        (fr["freeze_id"],),
    ).fetchone()
    assert row["evaluation_version"] == "FORWARD-EVAL-v1"
    assert row["evaluator_source"] == "forward_evaluation.evaluate"
    assert row["content_hash"]


def test_no_prediction_regeneration_on_evaluate(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900064, home=2, away=1)
    sync_actual_result(eval_db, prod_db, 900064)
    with patch("worldcup_predictor.forward_evaluation.freeze_service.create_or_reuse_freeze") as freeze_mock:
        with patch("worldcup_predictor.forward_evaluation.orchestrator.run_forward_evaluation_automation_cycle") as orch_mock:
            evaluate_fixture(900064, prod_conn=prod_db, eval_conn=eval_db, skip_result_sync=True)
            freeze_mock.assert_not_called()
            orch_mock.assert_not_called()


def test_tier_a_public_eligible(prod_db, eval_db, patch_git_sha):
    fr = _prepare_finished_fixture(prod_db, eval_db, 900065, home=1, away=0)
    sync_actual_result(eval_db, prod_db, 900065)
    out = evaluate_fixture(900065, prod_conn=prod_db, eval_conn=eval_db, skip_result_sync=True)
    assert out.get("eligibility_class") == "PUBLIC_ELIGIBLE"
    assert out.get("public_visible") == 1
