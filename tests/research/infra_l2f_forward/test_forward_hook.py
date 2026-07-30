"""Forward-hook unit tests: success/skip/block/fail/retry/idempotency + canonical isolation."""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from worldcup_predictor.research.infra_l2f_forward.forward_hook import maybe_run_l2f_forward_shadow
from worldcup_predictor.research.infra_l2f_forward.job_store import get_job


def _conn(tmp_path):
    c = sqlite3.connect(tmp_path / "hook.db")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE fixtures (
          fixture_id INTEGER PRIMARY KEY,
          home_team TEXT, away_team TEXT, competition_key TEXT,
          kickoff_utc TEXT, status TEXT
        );
        CREATE TABLE ecse_prediction_snapshots (
          id INTEGER PRIMARY KEY,
          fixture_id INTEGER,
          lambda_home REAL,
          lambda_away REAL
        );
        """
    )
    c.execute(
        """
        INSERT INTO fixtures VALUES
        (1001, 'Alpha', 'Beta', 'world_cup_2026', '2099-01-01T12:00:00+00:00', 'NS')
        """
    )
    c.execute(
        "INSERT INTO ecse_prediction_snapshots(id, fixture_id, lambda_home, lambda_away) VALUES (1,1001,1.4,1.1)"
    )
    c.commit()
    return c


def _settings(**kwargs):
    base = {
        "l2f_forward_shadow_mode": "shadow",
        "l2f_forward_shadow_kill_switch": False,
        "l2f_forward_shadow_timeout_sec": 5.0,
        "sqlite_path": "data/football_intelligence.db",
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_kill_switch_skips(tmp_path):
    conn = _conn(tmp_path)
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "created", "freeze_id": "fz1", "prediction_scope": "production"},
        prediction_scope="production",
        settings=_settings(l2f_forward_shadow_kill_switch=True),
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "kill_switch"
    assert out["canonical_unaffected"] is True
    conn.close()


def test_mode_off_skips(tmp_path):
    conn = _conn(tmp_path)
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "created", "freeze_id": "fz1"},
        prediction_scope="production",
        settings=_settings(l2f_forward_shadow_mode="off"),
    )
    assert out["status"] == "skipped"
    assert "mode_off" in out["reason"]
    conn.close()


def test_scope_not_owner_skips(tmp_path):
    conn = _conn(tmp_path)
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "created", "freeze_id": "fz1"},
        prediction_scope="public_research",
        settings=_settings(),
    )
    assert out["status"] == "skipped"
    assert out["reason"] == "scope_not_owner_production"
    conn.close()


def test_freeze_missing_skips(tmp_path):
    conn = _conn(tmp_path)
    # Missing immutable freeze identity is a hard block in Phase 4.
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "rejected", "freeze_id": None},
        prediction_scope="production",
        settings=_settings(),
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "missing_freeze_id"
    # Invalid capture status with freeze id present.
    out2 = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "rejected", "freeze_id": "fz-rej"},
        prediction_scope="production",
        settings=_settings(),
    )
    assert out2["status"] == "blocked"
    assert "freeze_status_rejected" in out2["reason"]
    conn.close()


def test_quarantine_blocks(tmp_path):
    conn = _conn(tmp_path)
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "created", "freeze_id": "fz1", "quarantined": True},
        prediction_scope="production",
        settings=_settings(),
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "freeze_quarantined_or_conflict"
    conn.close()


def test_missing_lambdas_blocks(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("DELETE FROM ecse_prediction_snapshots")
    conn.commit()
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "created", "freeze_id": "fz1"},
        prediction_scope="production",
        settings=_settings(),
    )
    assert out["status"] == "blocked"
    assert out["reason"] == "missing_canonical_lambdas"
    conn.close()


def test_exception_does_not_raise(tmp_path, monkeypatch):
    conn = _conn(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("explode")

    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.forward_hook.HistoricalMatchService",
        boom,
    )
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta={"capture_status": "created", "freeze_id": "fz2"},
        prediction_scope="owner_shadow",
        settings=_settings(),
    )
    assert out["canonical_unaffected"] is True
    assert out["status"] == "failed"
    conn.close()


def test_idempotent_second_call(tmp_path, monkeypatch):
    conn = _conn(tmp_path)

    calls = {"n": 0}

    class FakeEngine:
        def build_match(self, *a, **k):
            raise AssertionError("should not rebuild on idempotent skip")

    def fake_pipeline(**kwargs):
        calls["n"] += 1
        from worldcup_predictor.research.infra_l2f_forward.shadow_orchestrator import (
            ShadowOrchestrationResult,
            StageResult,
        )

        return ShadowOrchestrationResult(
            fixture_id=kwargs["fixture_id"],
            stages=[StageResult("form_snapshot", True), StageResult("totals_snapshot", True), StageResult("lambda_exact_shadow", True)],
            canonical_blocked=False,
        )

    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.forward_hook.HistoricalMatchService",
        lambda **k: object(),
    )
    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.forward_hook.TeamStrengthEngine",
        lambda *_a, **_k: FakeEngine(),
    )
    monkeypatch.setattr(
        "worldcup_predictor.research.infra_l2f_forward.forward_hook.run_shadow_pipeline",
        fake_pipeline,
    )

    meta = {"capture_status": "created", "freeze_id": "fz-idem"}
    a = maybe_run_l2f_forward_shadow(
        conn=conn, fixture_id=1001, freeze_meta=meta, prediction_scope="production", settings=_settings()
    )
    b = maybe_run_l2f_forward_shadow(
        conn=conn, fixture_id=1001, freeze_meta=meta, prediction_scope="production", settings=_settings()
    )
    assert a["status"] == "success"
    assert b["status"] == "skipped"
    assert b["reason"] == "already_success_idempotent"
    assert calls["n"] == 1
    job = get_job(conn, fixture_id=1001, freeze_id="fz-idem", run_id="l2f-forward-v1")
    assert job is not None and job["status"] == "success"
    conn.close()


def test_canonical_output_unchanged_with_shadow_flag(tmp_path):
    """Byte-level: freeze_meta dict returned to caller is not mutated by shadow hook."""
    conn = _conn(tmp_path)
    freeze_meta = {"capture_status": "created", "freeze_id": "fz-c", "prediction_scope": "production"}
    before = dict(freeze_meta)
    out = maybe_run_l2f_forward_shadow(
        conn=conn,
        fixture_id=1001,
        freeze_meta=freeze_meta,
        prediction_scope="production",
        settings=_settings(l2f_forward_shadow_kill_switch=True),
    )
    assert freeze_meta == before
    assert out["canonical_unaffected"] is True
    conn.close()
