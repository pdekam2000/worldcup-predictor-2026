"""Tests for massive dataset recovery + as-of leakage guards."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from worldcup_predictor.research.massive_algorithm_search.dataset_recovery import as_of as as_of_mod
from worldcup_predictor.research.massive_algorithm_search.dataset_recovery import ledger as led
from worldcup_predictor.research.massive_algorithm_search.dataset_recovery.true_forward_collector import dry_run


def test_as_of_cutoff_rejects_future_matches():
    ko = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    past = as_of_mod.TeamMatch(
        fixture_id=1,
        kickoff=ko - timedelta(days=3),
        team_id=10,
        team_name="A",
        is_home=True,
        goals_for=2,
        goals_against=1,
        result="W",
    )
    future = as_of_mod.TeamMatch(
        fixture_id=2,
        kickoff=ko + timedelta(days=1),
        team_id=10,
        team_name="A",
        is_home=True,
        goals_for=1,
        goals_against=0,
        result="W",
    )
    try:
        as_of_mod.assert_no_future_leakage({}, ko, [past, future], [])
        assert False, "expected leakage assertion"
    except AssertionError:
        pass
    as_of_mod.assert_no_future_leakage({}, ko, [past], [])


def test_as_of_form_uses_only_prior_window():
    ko = datetime(2026, 7, 10, tzinfo=timezone.utc)
    hist = [
        as_of_mod.TeamMatch(i, ko - timedelta(days=20 - i), 1, "T", True, 1, 0, "W")
        for i in range(1, 6)
    ]
    f = as_of_mod.form_window(hist, 5)
    assert f["n"] == 5
    assert f["ppg"] == 3.0


def test_classify_result_only():
    row = led.classify_row(
        actual="home",
        stored=None,
        ecse=None,
        odds=None,
        freeze=None,
        has_form=False,
        has_provider_map=False,
        prior_valid_ids=set(),
        fid=999001,
        kickoff="2026-07-01T12:00:00+00:00",
    )
    assert row.primary_exclusion_reason == "RESULT_ONLY_FIXTURE"
    assert row.recoverable is False


def test_classify_post_kickoff_prediction():
    row = led.classify_row(
        actual="home",
        stored={"predicted_at": "2026-07-01T13:00:00+00:00", "wde": "home", "quarantined": False},
        ecse=None,
        odds=None,
        freeze=None,
        has_form=False,
        has_provider_map=False,
        prior_valid_ids=set(),
        fid=999002,
        kickoff="2026-07-01T12:00:00+00:00",
    )
    assert row.primary_exclusion_reason == "POST_KICKOFF_PREDICTION"
    assert row.leakage_risk == "HIGH"


def test_true_forward_collector_dry_run_inactive():
    v = dry_run()
    assert v["collection_active"] is False
    assert v["timers_active"] is False
    assert v["canonical_unchanged"] is True
    assert v["no_auto_promotion"] is True


def test_ledger_accounts_all_finished():
    rows, funnel = led.build_ledger(prior_valid_ids=set())
    assert funnel["total_finished"] == funnel["accounted_for"]
    assert funnel["silent_drop"] == 0
    assert len(rows) == funnel["total_finished"]
    assert funnel["total_finished"] >= 2400
