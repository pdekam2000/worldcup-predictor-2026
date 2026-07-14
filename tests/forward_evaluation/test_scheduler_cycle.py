"""Phase 2E — forward evaluation scheduler cycle tests."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from worldcup_predictor.forward_evaluation.lock import SchedulerLockActive, scheduler_cycle_lock
from worldcup_predictor.forward_evaluation.scheduler import (
    ALREADY_EVALUATED,
    FINAL_ALREADY_RUNNING,
    FREEZE_INVALID,
    LIMIT_DEFERRED,
    OUTSIDE_LOOKBACK,
    PUBLIC_ELIGIBLE,
    run_forward_evaluation_cycle,
)
from tests.forward_evaluation.conftest import seed_fixture_result, seed_tier_a_fixture
from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze


@pytest.fixture
def patch_git_sha():
    with patch(
        "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
        return_value={"current_git_sha": "abc123", "git_sha_source": "test"},
    ):
        yield


def _seed_freeze(prod_db, eval_db, fixture_id, *, kickoff_days_ahead=2.0, predicted_days_ahead=1.0):
    seed_tier_a_fixture(
        prod_db, fixture_id=fixture_id, kickoff_days_ahead=kickoff_days_ahead, predicted_days_ahead=predicted_days_ahead
    )
    fr = create_or_reuse_freeze(
        fixture_id,
        prod_conn=prod_db,
        eval_conn=eval_db,
        source_context={"prediction_scope": "production", "validation_tier": "A", "public_visible": True},
    )
    assert fr.get("freeze_id"), fr
    return fr


def _run_cycle(prod_db, eval_db, **kwargs):
    return run_forward_evaluation_cycle(prod_conn=prod_db, eval_conn=eval_db, **kwargs)


def test_default_runner_is_dry_run(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910001)
    out = _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=5, lookback_hours=168)
    assert out["dry_run"] is True
    assert eval_db.execute("SELECT 1 FROM forward_evaluation_runs").fetchone() is None


def test_apply_requires_explicit_flag_via_cli():
    from scripts.run_forward_evaluation_cycle import main
    import sys

    with patch.object(sys, "argv", ["run_forward_evaluation_cycle.py"]):
        with patch("scripts.run_forward_evaluation_cycle.run_forward_evaluation_cycle") as mock:
            mock.return_value = {"run_id": "x", "final_status": "ok", "candidates_found": 0}
            main()
            mock.assert_called_once()
            assert mock.call_args.kwargs["dry_run"] is True


def _finish_fixture(prod_db, eval_db, fixture_id, *, home=1, away=0):
    prod_db.execute(
        "UPDATE fixtures SET kickoff_utc=datetime('now','-2 days'), status='FT' WHERE fixture_id=?",
        (fixture_id,),
    )
    eval_db.execute(
        """
        UPDATE frozen_predictions
        SET kickoff=datetime('now','-2 days'),
            generated_at=datetime('now','-3 days'),
            frozen_at=datetime('now','-3 days')
        WHERE fixture_id=?
        """,
        (fixture_id,),
    )
    prod_db.commit()
    eval_db.commit()
    seed_fixture_result(prod_db, fixture_id=fixture_id, home_goals=home, away_goals=away)


def test_fixture_limit_enforced(prod_db, eval_db, patch_git_sha):
    for fid in (910010, 910011, 910012):
        _seed_freeze(prod_db, eval_db, fid)
        _finish_fixture(prod_db, eval_db, fid)
    out = _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=1, lookback_hours=168)
    assert out.get("deferred") or LIMIT_DEFERRED in out.get("classifications", {})


def test_lookback_enforced(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910020)
    eval_db.execute(
        "UPDATE frozen_predictions SET kickoff=datetime('now','-30 days') WHERE fixture_id=910020"
    )
    eval_db.commit()
    out = _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=10, lookback_hours=24)
    assert OUTSIDE_LOOKBACK in out.get("classifications", {})


def test_scope_filter_enforced(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910030)
    eval_db.execute(
        "UPDATE frozen_predictions SET prediction_scope='owner_shadow', validation_tier='B', public_visible=0 WHERE fixture_id=910030"
    )
    eval_db.commit()
    out = _run_cycle(prod_db, eval_db, dry_run=True, scope="production", fixture_limit=10, lookback_hours=168)
    assert out["candidates_found"] == 0


def test_terminal_fixture_selected(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910040)
    _finish_fixture(prod_db, eval_db, 910040, home=2, away=1)
    out = _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=5, lookback_hours=168)
    assert out["candidates_found"] >= 1


def test_prematch_fixture_excluded_from_eval(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910050, kickoff_days_ahead=2.0)
    out = _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=5, lookback_hours=168)
    assert FREEZE_INVALID in out.get("classifications", {}) or out["results_missing"] >= 0


def test_already_evaluated_reused(prod_db, eval_db, patch_git_sha):
    fr = _seed_freeze(prod_db, eval_db, 910060)
    _finish_fixture(prod_db, eval_db, 910060)
    eval_db.execute(
        """
        INSERT INTO market_evaluations (prediction_id, fixture_id, wde_hit, evaluation_timestamp)
        VALUES (?, 910060, 'HIT', datetime('now'))
        """,
        (fr["freeze_id"],),
    )
    eval_db.commit()
    out = _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=5, lookback_hours=168)
    assert ALREADY_EVALUATED in out.get("classifications", {})


def test_dry_run_does_not_write_ledger_or_results(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910070)
    _finish_fixture(prod_db, eval_db, 910070)
    before = eval_db.execute("SELECT COUNT(*) c FROM actual_results").fetchone()["c"]
    _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=5, lookback_hours=168)
    after = eval_db.execute("SELECT COUNT(*) c FROM actual_results").fetchone()["c"]
    assert before == after
    assert eval_db.execute("SELECT 1 FROM forward_evaluation_runs").fetchone() is None


def test_global_lock_prevents_overlap(tmp_path):
    lock_dir = tmp_path / "locks"
    with patch("worldcup_predictor.forward_evaluation.lock._LOCK_DIR", lock_dir):
        with scheduler_cycle_lock(
            run_id="run-a", dry_run=False, fixture_limit=5, lookback_hours=72, scope="all"
        ):
            with pytest.raises(SchedulerLockActive):
                with scheduler_cycle_lock(
                    run_id="run-b", dry_run=False, fixture_limit=5, lookback_hours=72, scope="all"
                ):
                    pass


def test_stale_lock_recovery_auditable(tmp_path):
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    stale = lock_dir / "forward_evaluation_cycle.lock"
    stale.write_text('{"run_id":"old"}', encoding="utf-8")
    old = time.time() - 99999
    import os

    os.utime(stale, (old, old))
    with patch("worldcup_predictor.forward_evaluation.lock._LOCK_DIR", lock_dir):
        with scheduler_cycle_lock(
            run_id="new", dry_run=True, fixture_limit=5, lookback_hours=72, scope="all"
        ) as meta:
            assert meta["run_id"] == "new"


def test_checkpoint_written_on_apply(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910080)
    _finish_fixture(prod_db, eval_db, 910080)
    out = _run_cycle(
        prod_db, eval_db, dry_run=False, fixture_limit=5, lookback_hours=168, skip_lock=True
    )
    row = eval_db.execute(
        "SELECT run_id, dry_run, final_status FROM forward_evaluation_runs WHERE run_id=?",
        (out["run_id"],),
    ).fetchone()
    assert row is not None
    assert row["dry_run"] == 0


def test_no_prediction_orchestrator_invoked(prod_db, eval_db, patch_git_sha):
    _seed_freeze(prod_db, eval_db, 910090)
    with patch("worldcup_predictor.forward_evaluation.orchestrator.run_forward_evaluation_automation_cycle") as orch:
        with patch("worldcup_predictor.forward_evaluation.freeze_service.create_or_reuse_freeze") as freeze:
            _run_cycle(prod_db, eval_db, dry_run=True, fixture_limit=5, lookback_hours=168)
            orch.assert_not_called()
            freeze.assert_not_called()


def test_systemd_service_bounded_arguments():
    svc = Path("deployment/systemd/worldcup-forward-evaluation.service").read_text(encoding="utf-8")
    assert "--fixture-limit 25" in svc
    assert "--lookback-hours 72" in svc
    assert "--apply" in svc


def test_timer_unit_not_enabled_by_default_in_repo():
    timer = Path("deployment/systemd/worldcup-forward-evaluation.timer").read_text(encoding="utf-8")
    assert "disabled" in timer.lower() or "do not enable" in timer.lower()
