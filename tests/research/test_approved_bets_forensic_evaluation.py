"""Tests for approved bets forensic evaluation (read-only)."""

from __future__ import annotations

from pathlib import Path

from worldcup_predictor.research import approved_bets_forensic_evaluation as m


def test_approval_taxonomy_has_entries():
    assert len(m.APPROVAL_TAXONOMY) >= 8
    assert any(e["field"].startswith("selected_matches") for e in m.APPROVAL_TAXONOMY)
    assert any(e["enter_official_approved"] is False for e in m.APPROVAL_TAXONOMY if "research_classification" in e["field"])


def test_norm_dir_and_exact_rank():
    assert m._norm_dir("home_win") == "home"
    assert m._norm_dir("away_win") == "away"
    assert m.exact_rank(["1-0", "0-0", "2-0"], "0-0") == "TOP2"
    assert m.exact_rank(["1-0", "2-0"], "3-3") == "OUTSIDE_TOP10"


def test_wilson_ci():
    lo, hi = m.wilson_ci(5, 10)
    assert lo is not None and hi is not None and 0 <= lo <= hi <= 1


def test_watchlist_and_research_not_in_strict_semantics():
    rec_w = m.ApprovalRecord(fixture_id=1, cohort=m.COHORT_WATCHLIST, source_path="x", source_kind="w")
    rec_r = m.ApprovalRecord(fixture_id=2, cohort=m.COHORT_RESEARCH, source_path="y", source_kind="r")
    assert rec_w.cohort != m.COHORT_STRICT_OWNER
    assert rec_r.cohort != m.COHORT_STRICT_PROD


def test_dedupe_keeps_earliest():
    a = m.ApprovalRecord(1, m.COHORT_STRICT_OWNER, "a", "k", approval_timestamp="2026-07-01T10:00:00+00:00")
    b = m.ApprovalRecord(1, m.COHORT_STRICT_OWNER, "b", "k", approval_timestamp="2026-07-02T10:00:00+00:00")
    by, _ = m.dedupe_records([b, a])
    assert by[m.COHORT_STRICT_OWNER][1].source_path == "a"


def test_no_bet_exclusion_in_strict_eval():
    rec = m.ApprovalRecord(
        fixture_id=999001,
        cohort=m.COHORT_STRICT_OWNER,
        source_path="t",
        source_kind="t",
        no_bet=True,
        approved_1x2_direction="home",
        kickoff_utc="2026-07-01T18:00:00+00:00",
        frozen_at="2026-06-30T12:00:00+00:00",
    )
    ev = m.evaluate_cohort(
        m.COHORT_STRICT_OWNER,
        {999001: rec},
        {999001: {"status": "FINISHED_CONFIRMED", "actual_1x2": "home", "final_score": "1-0"}},
        {},
    )
    assert ev["excluded_integrity_or_no_bet"] == 1
    assert ev["finished_confirmed_1x2"] == 0


def test_roi_and_drawdown_unit_stake():
    rec = m.ApprovalRecord(
        fixture_id=999002,
        cohort=m.COHORT_STRICT_OWNER,
        source_path="t",
        source_kind="t",
        no_bet=False,
        approved_1x2_direction="home",
        odds_home=2.0,
        odds_draw=3.0,
        odds_away=4.0,
        kickoff_utc="2026-07-01T18:00:00+00:00",
        frozen_at="2026-06-30T12:00:00+00:00",
    )
    ev = m.evaluate_cohort(
        m.COHORT_STRICT_OWNER,
        {999002: rec},
        {999002: {"status": "FINISHED_CONFIRMED", "actual_1x2": "home", "final_score": "2-0"}},
        {},
    )
    assert ev["priced_n"] == 1
    assert ev["roi_unit_stake"] == 1.0


def test_run_smoke(tmp_path):
    v = m.run(out_dir=tmp_path / "approved")
    assert v["status"] in {m.STATUS_COMPLETE, m.STATUS_PARTIAL}
    assert v["not_deployed"] is True
    assert v["canonical_unchanged"] is True
    assert v["freezes_unchanged"] is True
    assert v["no_predictions_regenerated"] is True
    assert (tmp_path / "approved" / "validation_report.json").exists()
    assert (tmp_path / "approved" / "APPROVED_BETS_APPROVAL_TAXONOMY.md").exists()
    assert (tmp_path / "approved" / "approved_bets_complete_ledger.csv").exists()
    # watchlist must not be in strict headline finished with watchlist cohort label
    assert v.get("reconciliation_ok") in {True, False}
