"""Phase 4 unit tests: classifications, follow-up, readiness, preregistration."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from worldcup_predictor.research.infra_l2f_forward.forward_hook import (
    CLASS_ALREADY_SUCCESS,
    CLASS_BLOCKED_MISSING_FREEZE,
    CLASS_SKIPPED_NOT_OWNER,
    CLASS_SKIPPED_POSTKICKOFF,
    CLASS_SUCCESS,
    classify_outcome,
    maybe_run_l2f_forward_shadow,
    resolve_cohort_type,
)
from worldcup_predictor.research.infra_l2f_forward.true_forward_followup import (
    PENDING_NOT_STARTED,
    PENDING_GRACE,
    classify_pre_sync,
    map_sync_to_followup_class,
)
from worldcup_predictor.research.infra_l2f_forward.preregistration import (
    content_hash,
    build_preregistration_document,
    write_preregistration,
)
from worldcup_predictor.research.infra_l2f_forward.readiness import (
    FORBIDDEN_PROMOTED,
    STATUS_INSUFFICIENT,
    evaluate_readiness,
)
from worldcup_predictor.research.infra_l2f_forward.job_store import ensure_job_schema
from worldcup_predictor.research.infra_l2f_forward.historical_replay import ensure_replay_schema
from types import SimpleNamespace


def test_resolve_cohort_never_true_forward_on_backfill():
    assert resolve_cohort_type(backfill=True, freeze_meta={"cohort_type": "true_forward"}) == "historical_replay"
    assert resolve_cohort_type(backfill=True, freeze_meta={"cohort_type": "historical_replay_result_recovered"}) == (
        "historical_replay_result_recovered"
    )
    assert resolve_cohort_type(backfill=False, freeze_meta={}) == "true_forward"


def test_classify_outcomes():
    assert classify_outcome(status="success", reason=None, cohort_type="true_forward") == CLASS_SUCCESS
    assert (
        classify_outcome(status="skipped", reason="already_success_idempotent", cohort_type="true_forward")
        == CLASS_ALREADY_SUCCESS
    )
    assert (
        classify_outcome(status="skipped", reason="scope_not_owner_production", cohort_type="true_forward")
        == CLASS_SKIPPED_NOT_OWNER
    )
    assert (
        classify_outcome(status="blocked", reason="post_kickoff", cohort_type="true_forward")
        == CLASS_SKIPPED_POSTKICKOFF
    )
    assert (
        classify_outcome(status="blocked", reason="missing_freeze_id", cohort_type="true_forward")
        == CLASS_BLOCKED_MISSING_FREEZE
    )


def test_followup_pre_sync_classes():
    future = (datetime.now(timezone.utc) + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    assert classify_pre_sync(kickoff_utc=future, fixture_status="NS") == PENDING_NOT_STARTED
    past = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    assert classify_pre_sync(kickoff_utc=past, fixture_status="NS", grace_hours=2.5) in {
        PENDING_GRACE,
        "pending_in_progress",
    }


def test_followup_conflict_mapping():
    assert map_sync_to_followup_class({"conflict": True, "reason": "x"}, had_prod_result=False) == "conflicting_result"
    assert (
        map_sync_to_followup_class(
            {"result_available": True, "synced": True, "status": "synced"}, had_prod_result=True
        )
        == "result_recovered_db"
    )


def test_preregistration_immutable(tmp_path):
    r1 = write_preregistration(tmp_path / "p", git_commit="abc")
    r2 = write_preregistration(tmp_path / "p", git_commit="abc")
    assert Path(r1["path"]).exists() and Path(r2["path"]).exists()
    assert r1["path"] != r2["path"]
    assert r1["content_hash"] == r2["content_hash"]
    doc = build_preregistration_document(git_commit="abc")
    # amending creates different hash only if content changes
    doc2 = json.loads(json.dumps(doc))
    doc2["models"]["exact_v2"]["primary_metric"] = "changed"
    assert content_hash(doc) != content_hash(doc2)


def test_readiness_never_promoted(tmp_path):
    fi = sqlite3.connect(tmp_path / "fi.db")
    ensure_job_schema(fi)
    ensure_replay_schema(fi)
    rep = evaluate_readiness(fi, None)
    assert rep["exact_v2"]["status"] == STATUS_INSUFFICIENT
    assert rep["lambda_v2"]["status"] == STATUS_INSUFFICIENT
    assert rep["detector_et_gte_3_0"]["status"] == STATUS_INSUFFICIENT
    assert rep["promotion_occurred"] is False
    assert rep["exact_v2"]["status"] != FORBIDDEN_PROMOTED
    assert rep["lambda_v2"]["status"] != FORBIDDEN_PROMOTED
    assert rep["detector_et_gte_3_0"]["status"] != FORBIDDEN_PROMOTED


def test_hook_blocks_missing_freeze_and_postkickoff(tmp_path):
    c = sqlite3.connect(tmp_path / "h.db")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE fixtures (
          fixture_id INTEGER PRIMARY KEY,
          home_team TEXT, away_team TEXT, competition_key TEXT,
          kickoff_utc TEXT, status TEXT
        );
        CREATE TABLE ecse_prediction_snapshots (
          id INTEGER PRIMARY KEY, fixture_id INTEGER, lambda_home REAL, lambda_away REAL
        );
        """
    )
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    c.execute(
        "INSERT INTO fixtures VALUES (1,'A','B','liga',?, 'NS')",
        (past,),
    )
    c.execute("INSERT INTO ecse_prediction_snapshots VALUES (1,1,1.2,1.1)")
    c.commit()
    settings = SimpleNamespace(
        l2f_forward_shadow_mode="shadow",
        l2f_forward_shadow_kill_switch=False,
        l2f_forward_shadow_timeout_sec=5.0,
        sqlite_path=str(tmp_path / "h.db"),
    )
    missing = maybe_run_l2f_forward_shadow(
        conn=c,
        fixture_id=1,
        freeze_meta={"capture_status": "created", "prediction_scope": "production"},
        prediction_scope="production",
        settings=settings,
    )
    assert missing["classification"] == CLASS_BLOCKED_MISSING_FREEZE

    post = maybe_run_l2f_forward_shadow(
        conn=c,
        fixture_id=1,
        freeze_meta={"capture_status": "created", "freeze_id": "fz", "prediction_scope": "production"},
        prediction_scope="production",
        settings=settings,
        backfill=False,
    )
    assert post["classification"] == CLASS_SKIPPED_POSTKICKOFF
    assert post["canonical_unaffected"] is True
