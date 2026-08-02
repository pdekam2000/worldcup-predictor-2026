"""Tests for Prediction Engine 75% Phase 4 locked holdout evaluation."""

from __future__ import annotations

import hashlib
import json

from worldcup_predictor.research.prediction_engine_75 import phase4 as m


def test_phase1_holdout_ids_preserved():
    assert len(m.PHASE1_HOLDOUT_IDS) == 11
    h = hashlib.sha256(",".join(str(x) for x in m.PHASE1_HOLDOUT_IDS).encode()).hexdigest()
    assert h == m.PHASE1_LOCK_HASH


def test_lock_manifest_hashes_stable():
    a = m.build_locked_manifest([1, 2, 3], [4, 5], source_commit="abc")
    b = m.build_locked_manifest([1, 2, 3], [4, 5], source_commit="abc")
    # creation_timestamp differs — compare configuration hashes per candidate
    ha = {c["candidate_id"]: c["configuration_hash"] for c in a["locked_candidates"]}
    hb = {c["candidate_id"]: c["configuration_hash"] for c in b["locked_candidates"]}
    assert ha == hb
    assert set(ha) == set(m.LOCKED_NAMES)


def test_holdout_train_val_separation():
    integrity = m.verify_holdout_integrity(
        rows=[],
        holdout_ids=list(m.PHASE1_HOLDOUT_IDS),
        train_ids={999},
        val_ids={1000},
        lock_meta={"raw": {"lock_hash": m.PHASE1_LOCK_HASH}},
    )
    # missing rows from corpus => fail
    assert integrity["passed"] is False
    assert any(f["issue"] == "holdout_fixtures_missing_from_corpus" for f in integrity["findings"])


def test_verdict_never_promotable_and_small_n():
    res = {"selected_fixtures": 11, "accuracy": 0.9, "lock_status": None}
    v = m.verdict_for(res, wde_acc=0.5)
    assert v == "HOLDOUT_SUPPORTED"
    # still research-only flag in evaluate_candidate
    from worldcup_predictor.research.prediction_engine_75 import phase2 as p2

    r = p2.RowV2(
        fixture_id=1,
        kickoff_utc="2026-07-01T12:00:00+00:00",
        predicted_at="2026-07-01T08:00:00+00:00",
        frozen_at="2026-07-01T08:00:00+00:00",
        freeze_id="f",
        freeze_hash=None,
        cohort=p2.COHORT_PREMATCH,
        source="t",
        league="L",
        match="a",
        wde_decision="home",
        ft_marginal="home",
        home_p=0.5,
        draw_p=0.3,
        away_p=0.2,
        confidence=60,
        no_bet=False,
        actual_1x2="home",
        final_score="1-0",
    )
    ev = m.evaluate_candidate("x", [r], [("home", r)])
    assert ev["warning"] == m.SMALL_WARNING
    assert ev["promotable"] is False


def test_true_forward_cohort_and_schema():
    schema = m.true_forward_schema()
    assert "cohort_type=true_forward" in schema["prediction_record"]
    assert "prediction records must not be overwritten after kickoff" in schema["immutability"]


def test_model_readiness_no_fabrication():
    ready = m.model_readiness()
    assert ready["Exact_V2"]["status"] == "MISSING_DEPENDENCY"
    assert ready["DNA_V2"]["status"] == "MISSING_DEPENDENCY"
    assert ready["Canonical_WDE"]["status"] == "READY"


def test_phase4_smoke(tmp_path):
    v = m.run_phase4(out_dir=tmp_path / "p4")
    assert v["status"] in {
        m.STATUS_READY,
        m.STATUS_HOLDOUT_FAIL,
        m.STATUS_LOCK_FAIL,
        m.STATUS_TF_BLOCKED,
        m.STATUS_FAILED,
    }
    assert v["not_deployed"] is True
    assert v["canonical_unchanged"] is True
    assert v["wde_unchanged"] is True
    assert v["ecse_unchanged"] is True
    assert v["no_auto_promotion"] is True
    assert v.get("no_retuning_after_holdout") is True or v["status"] != m.STATUS_READY
    assert v["target_75_claimed"] is False
    if v["status"] == m.STATUS_READY:
        assert v["holdout_n"] == 11
        assert v["small_sample_warning"] == m.SMALL_WARNING
        assert v["timers_enabled"] is False
        assert (tmp_path / "p4" / "locked_candidate_manifest.sha256").exists()
        opening = json.loads((tmp_path / "p4" / "sealed_holdout_opening_ledger.json").read_text(encoding="utf-8"))
        assert opening["retuning_allowed_after_open"] is False
        assert opening["opened_exactly_once"] is True
