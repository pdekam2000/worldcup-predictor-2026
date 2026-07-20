"""Tests for CANONICAL_RESEARCH_EPHEMERAL isolation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from worldcup_predictor.research.canonical_ephemeral.constants import EXECUTION_MODE
from worldcup_predictor.research.canonical_ephemeral.facade import run_ephemeral_canonical_prediction
from worldcup_predictor.research.canonical_ephemeral.types import ResearchContext
from worldcup_predictor.research.canonical_ephemeral.write_guard import (
    EphemeralWriteBlocked,
    ephemeral_mode_active,
    ephemeral_write_guard,
)
from worldcup_predictor.research.ecse_live.store import insert_snapshot
from worldcup_predictor.research.ecse_timing_experiment.capture import (
    EARLY_FREEZE_SIDE_EFFECT_FIXTURES,
    annotate_early_freeze_side_effects,
)
from worldcup_predictor.research.ecse_timing_experiment.isolation import run_isolation_preflight
from worldcup_predictor.research.ecse_timing_experiment.store import (
    ensure_experiment,
    get_snapshot,
    insert_snapshot_immutable,
)
from worldcup_predictor.research.ecse_timing_experiment.db import connect_timing_db


def _research_ctx(**kwargs) -> ResearchContext:
    base = dict(
        experiment_id="exp_test",
        experiment_date="2026-07-21",
        snapshot_class="EARLY",
        audit_id="audit_test",
        scope="owner",
        caller="canonical_ephemeral_test",
    )
    base.update(kwargs)
    return ResearchContext(**base)


def test_write_guard_blocks_and_clears():
    assert ephemeral_mode_active() is False
    with ephemeral_write_guard():
        assert ephemeral_mode_active() is True
        with pytest.raises(EphemeralWriteBlocked) as ei:
            from worldcup_predictor.research.canonical_ephemeral.write_guard import block_canonical_write

            block_canonical_write(table="frozen_predictions", operation="INSERT", detail="test")
        assert "EPHEMERAL_WRITE_BLOCKED" in str(ei.value)
    assert ephemeral_mode_active() is False


def test_insert_snapshot_blocked_under_ephemeral(tmp_path: Path):
    conn = sqlite3.connect(str(tmp_path / "t.db"))
    conn.row_factory = sqlite3.Row
    from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL

    for ddl in PHASE_ECSE_LIVE_DDL:
        conn.execute(ddl)
    conn.commit()
    payload = {
        "fixture_id": 1,
        "model_version": "test",
        "lambda_home": 1.0,
        "lambda_away": 1.0,
        "top_10_scorelines": [],
        "top_1_score": "1-0",
        "top_3_scores": [],
        "top_5_scores": [],
        "confidence_score": 0.5,
        "data_quality_score": 0.5,
    }
    with ephemeral_write_guard():
        with pytest.raises(EphemeralWriteBlocked):
            insert_snapshot(conn, payload)
    conn.close()


def test_wsp_upsert_blocked_under_ephemeral():
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    repo = FootballIntelligenceRepository.__new__(FootballIntelligenceRepository)
    repo._conn = MagicMock()
    with ephemeral_write_guard():
        with pytest.raises(EphemeralWriteBlocked):
            repo.upsert_worldcup_stored_prediction(fixture_id=1, payload={"x": 1})


def test_freeze_create_blocked_under_ephemeral():
    from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze

    with ephemeral_write_guard():
        with pytest.raises(EphemeralWriteBlocked):
            create_or_reuse_freeze(1, prod_conn=MagicMock(), eval_conn=MagicMock())


def test_ephemeral_facade_rejects_unauthorized_caller():
    with pytest.raises(PermissionError):
        run_ephemeral_canonical_prediction(
            1,
            scope="owner",
            odds_snapshot=None,
            research_context=_research_ctx(caller="public_api"),
        )


def test_ephemeral_facade_no_canonical_writes(tmp_path: Path):
    """Facade must not persist WSP/ECSE/freeze; isolation flags stay false."""
    odds = MagicMock()
    odds.to_dict.return_value = {
        "home_odds": 2.1,
        "draw_odds": 3.2,
        "away_odds": 3.4,
        "bookmaker_count": 5,
        "fetched_at_utc": "2026-07-20T12:00:00+00:00",
        "freshness_class": "ODDS_FRESH",
        "provider": "test",
    }

    fake_result = MagicMock()
    fake_result.success = True
    fake_result.intelligence_report = None
    fake_result.specialist_report = None
    fake_result.prediction = MagicMock()

    payload = {
        "one_x_two": {"selection": "home"},
        "probabilities": {
            "home": 0.45,
            "draw": 0.28,
            "away": 0.27,
            "btts": {"selection": "yes", "probabilities": {"yes": 0.55, "no": 0.45}},
            "over_under_2_5": {
                "selection": "over",
                "probabilities": {"over_2_5": 0.52, "under_2_5": 0.48},
            },
        },
        "confidence": 0.6,
        "no_bet": True,
        "pick_tier": "caution",
        "model_version": "wde-test",
    }

    ecse_pred = {
        "lambda_home": 1.2,
        "lambda_away": 1.0,
        "model_version": "ecse-test",
        "top_5_scores": [
            {"scoreline": "1-0", "probability": 0.12},
            {"scoreline": "1-1", "probability": 0.11},
            {"scoreline": "2-0", "probability": 0.10},
            {"scoreline": "0-0", "probability": 0.09},
            {"scoreline": "2-1", "probability": 0.08},
        ],
        "top_10_scorelines": [],
        "raw_features": {},
    }

    row = {
        "fixture_id": 42,
        "competition_key": "champions_league",
        "home_team": "A",
        "away_team": "B",
        "kickoff_utc": "2026-07-21T17:00:00+00:00",
        "status": "NS",
        "season": 2026,
    }

    prod = MagicMock()
    prod.execute.return_value.fetchone.return_value = row
    repo = MagicMock()
    repo.get_fixture_row.return_value = row
    repo.upsert_worldcup_stored_prediction = MagicMock()

    with patch("worldcup_predictor.research.canonical_ephemeral.facade.bootstrap_gpt_actions_runtime"), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.get_settings",
        return_value=MagicMock(sqlite_path=str(tmp_path / "p.db"), api_football_configured=True),
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.FootballIntelligenceRepository",
        return_value=repo,
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.prepare_daily_fixture_for_wde",
        side_effect=lambda f, **k: f,
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.PredictPipeline"
    ) as PP, patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.build_api_payload",
        return_value=dict(payload),
    ), patch(
        "worldcup_predictor.api.prediction_metadata.stamp_prediction_engine_metadata",
        side_effect=lambda p, **k: p,
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.stamp_provider_readiness",
        side_effect=lambda p, **k: p,
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.stamp_payload_odds_freshness",
        side_effect=lambda p, f: p,
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.build_fixture_freshness_metadata",
        return_value={},
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.odds_readiness_audit",
        return_value={"lambda_inputs_available": True},
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.build_ecse_live_prediction",
        return_value=ecse_pred,
    ), patch(
        "worldcup_predictor.research.canonical_ephemeral.facade.extract_wde_semantics",
        return_value={
            "decision_pick": "home_win",
            "probability_argmax": "home_win",
            "home_prob": 0.45,
            "draw_prob": 0.28,
            "away_prob": 0.27,
            "confidence": 0.6,
        },
    ), patch(
        "worldcup_predictor.research.ecse_live.store.insert_snapshot"
    ) as ins:
        PP.return_value.run.return_value = fake_result
        out = run_ephemeral_canonical_prediction(
            42,
            scope="owner",
            odds_snapshot=odds,
            research_context=_research_ctx(),
            prod_conn=prod,
        )

    assert out.execution_mode == EXECUTION_MODE
    assert out.complete is True
    assert out.wsp_written is False
    assert out.ecse_canonical_written is False
    assert out.freeze_created is False
    assert out.canonical_writes_completed == 0
    assert out.research_only is True
    assert out.canonical is False
    assert out.final_decision_authority is False
    assert len(out.ecse.get("scores") or []) == 5
    repo.upsert_worldcup_stored_prediction.assert_not_called()
    ins.assert_not_called()
    assert out.no_bet is True
    assert out.no_bet_diagnostics.get("no_bet_reason_status") in {
        "NOT_EXPOSED_BY_CANONICAL_PAYLOAD",
        "EXPOSED",
    }

def test_timing_snapshot_records_ephemeral_flags(tmp_path: Path):
    conn = connect_timing_db(tmp_path)
    eid = ensure_experiment(conn, experiment_date="2026-07-21", scope="owner", timezone="Europe/Vienna")
    payload = {
        "execution_mode": EXECUTION_MODE,
        "canonical_writes_attempted": 0,
        "canonical_writes_completed": 0,
        "freeze_created": False,
        "wsp_written": False,
        "ecse_canonical_written": False,
        "ecse": {"scores": ["1-0", "1-1", "2-0", "0-0", "2-1"]},
        "research_only": True,
        "canonical": False,
    }
    r = insert_snapshot_immutable(
        conn,
        experiment_id=eid,
        fixture_id=1,
        snapshot_class="EARLY",
        status="CAPTURED",
        payload=payload,
        freeze_capture=False,
    )
    assert r["inserted"] is True
    snap = get_snapshot(conn, experiment_id=eid, fixture_id=1, snapshot_class="EARLY")
    assert snap["payload"]["execution_mode"] == EXECUTION_MODE
    r2 = insert_snapshot_immutable(
        conn,
        experiment_id=eid,
        fixture_id=1,
        snapshot_class="EARLY",
        status="CAPTURED",
        payload={**payload, "ecse": {"scores": ["9-9"]}},
        freeze_capture=False,
    )
    assert r2["idempotent"] is True
    snap2 = get_snapshot(conn, experiment_id=eid, fixture_id=1, snapshot_class="EARLY")
    assert snap2["payload"]["ecse"]["scores"][0] == "1-0"
    conn.close()


def test_mid_preflight_blocks_without_fixtures(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # timing db path relative to project_root — patch connect to local
    from worldcup_predictor.research.ecse_timing_experiment import isolation as iso

    monkeypatch.setattr(iso, "timing_db_path", lambda: tmp_path / "data/research/ecse_timing_experiment.db")
    monkeypatch.setattr(iso, "connect_timing_db", lambda: connect_timing_db(tmp_path))
    monkeypatch.setattr(
        iso,
        "snapshot_canonical_state",
        lambda fids: {"wsp_count": 0, "ecse_count": 0, "freeze_count": 0, "freeze_hashes": {}},
    )
    out = run_isolation_preflight(
        experiment_id="e",
        experiment_date="2026-07-21",
        snapshot_class="MID",
        fixture_ids=[],
        audit_id="a",
    )
    assert out["ok"] is False
    assert out["status"] == "BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN"


def test_early_freeze_side_effect_annotations_immutable_contract():
    eval_conn = MagicMock()
    eval_conn.execute.return_value.fetchone.return_value = {
        "prediction_id": "freeze-1",
        "content_hash": "abc",
        "frozen_at": "2026-07-20T16:22:23+00:00",
    }
    eval_conn.execute.return_value.fetchall.return_value = []
    # _load_freeze uses two executes — simplify by patching
    with patch(
        "worldcup_predictor.research.ecse_timing_experiment.capture._load_freeze",
        return_value={
            "prediction_id": "freeze-1",
            "content_hash": "abc",
            "frozen_at": "2026-07-20T16:22:23+00:00",
        },
    ):
        anns = annotate_early_freeze_side_effects(eval_conn, "audit_now")
    assert len(anns) == 4
    assert all(a["label"] == "EARLY_FREEZE_SIDE_EFFECT_CREATED" for a in anns)
    assert all(a["must_remain_immutable"] is True for a in anns)
    assert all(a["payload_mutated"] is False for a in anns)
    assert set(EARLY_FREEZE_SIDE_EFFECT_FIXTURES) == {a["fixture_id"] for a in anns}


def test_freeze_service_callable_outside_ephemeral():
    """Normal path must not raise EphemeralWriteBlocked when guard is inactive."""
    import sqlite3

    from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze

    prod = sqlite3.connect(":memory:")
    prod.row_factory = sqlite3.Row
    eval_conn = sqlite3.connect(":memory:")
    eval_conn.row_factory = sqlite3.Row
    assert ephemeral_mode_active() is False
    try:
        create_or_reuse_freeze(999001, prod_conn=prod, eval_conn=eval_conn)
    except EphemeralWriteBlocked:
        raise AssertionError("freeze service blocked outside ephemeral mode")
    except Exception:
        # Schema/fixture missing is fine — proves guard did not fire
        pass
    finally:
        prod.close()
        eval_conn.close()

    from worldcup_predictor.gpt_actions import schemas

    src = Path(schemas.__file__).read_text(encoding="utf-8")
    assert "CANONICAL_RESEARCH_EPHEMERAL" not in src
    assert "ephemeral" not in src.lower()


def test_gpt_actions_worker_has_no_ephemeral_hook():
    from worldcup_predictor.gpt_actions import worker

    src = Path(worker.__file__).read_text(encoding="utf-8")
    assert "CANONICAL_RESEARCH_EPHEMERAL" not in src
    assert "run_ephemeral_canonical_prediction" not in src


def test_capture_module_uses_ephemeral_not_jobs():
    from worldcup_predictor.research.ecse_timing_experiment import capture as cap

    src = Path(cap.__file__).read_text(encoding="utf-8")
    assert "run_ephemeral_canonical_prediction" in src
    assert "enqueue_prediction_job" not in src
    assert "EXECUTION_MODE" in src
    assert "BLOCKED_RESEARCH_ISOLATION_NOT_PROVEN" in src or "run_isolation_preflight" in src
