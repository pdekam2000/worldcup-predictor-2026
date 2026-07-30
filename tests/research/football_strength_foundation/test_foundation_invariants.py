"""Tests for football strength foundation / Lambda V2 (shadow)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from worldcup_predictor.research.football_strength_foundation.leakage_assertions import (
    raise_if_leaks,
    validate_history_row,
)
from worldcup_predictor.research.football_strength_foundation.totals_market import (
    TotalsLine,
    check_monotonic_overs,
    invert_multi_line,
)
from worldcup_predictor.research.football_strength_foundation.score_v2 import dist_poisson, exact_metrics
from worldcup_predictor.research.lambda_team_strength.metrics import shrink_to_prior


def test_leakage_rejects_future_kickoff():
    cutoff = datetime(2026, 7, 1)
    viol = validate_history_row(
        hist_kickoff=datetime(2026, 7, 2),
        cutoff=cutoff,
        hist_fixture_id=1,
        target_fixture_id=2,
    )
    assert any(v.code == "KICKOFF_NOT_BEFORE_CUTOFF" for v in viol)
    with pytest.raises(ValueError, match="LEAKAGE"):
        raise_if_leaks(viol)


def test_leakage_rejects_same_fixture():
    cutoff = datetime(2026, 7, 1)
    viol = validate_history_row(
        hist_kickoff=datetime(2026, 6, 1),
        cutoff=cutoff,
        hist_fixture_id=99,
        target_fixture_id=99,
    )
    assert any(v.code == "SAME_FIXTURE_CONTAMINATION" for v in viol)


def test_monotonic_and_no_invented_lines():
    lines = [
        TotalsLine(2.5, 1.9, 1.9),
        TotalsLine(3.5, 2.4, 1.55),
    ]
    inv = invert_multi_line(lines)
    assert inv["lambda_total"] is not None
    assert 4.5 not in inv["lines_used"]
    mono = check_monotonic_overs(0.55, 0.35, 0.15)
    assert mono["consistent"] is True
    bad = check_monotonic_overs(0.40, 0.50, 0.20)
    assert bad["consistent"] is False


def test_shrinkage_moves_toward_prior_with_small_n():
    est = shrink_to_prior(3.0, 1.3, n=2, prior_strength=8.0)
    assert 1.3 < est < 3.0


def test_score_metrics_deterministic():
    d1 = dist_poisson(1.4, 1.1)
    d2 = dist_poisson(1.4, 1.1)
    assert [e["scoreline"] for e in d1[:5]] == [e["scoreline"] for e in d2[:5]]
    m = exact_metrics(d1, 1, 1)
    assert "top5" in m and "log_loss" in m
