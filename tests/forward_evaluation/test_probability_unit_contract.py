"""Invariant tests for probability unit contract and freeze persistence metadata."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze
from worldcup_predictor.forward_evaluation.probability_units import (
    PROBABILITY_UNIT_FRACTION,
    ProbabilityUnitError,
    assert_fraction,
    to_fraction,
    to_percent,
    top_mass,
    validate_probability_payload,
)
from tests.forward_evaluation.conftest import seed_tier_a_fixture


def test_to_fraction_accepts_fraction_and_percent():
    assert to_fraction(0.45) == 0.45
    assert to_fraction(45.0) == 0.45
    assert to_percent(0.45) == 45.0


def test_to_fraction_rejects_invalid():
    with pytest.raises(ProbabilityUnitError):
        to_fraction(-0.1, allow_none=False)
    with pytest.raises(ProbabilityUnitError):
        to_fraction(150)


def test_assert_fraction_bounds():
    assert assert_fraction(0.0) == 0.0
    assert assert_fraction(1.0) == 1.0


def test_top_mass_sums_canonical_fractions():
    rows = [{"probability": 0.2}, {"probability": 20.0}, {"probability": 0.1}]
    assert top_mass(rows, 3) == pytest.approx(0.5)


def test_validate_payload_flags_bad_values():
    issues = validate_probability_payload({"home_probability": -1})
    assert issues


@pytest.fixture
def patch_git_sha():
    with patch(
        "worldcup_predictor.forward_evaluation.freeze_service.resolve_current_git_sha",
        return_value={"current_git_sha": "abc123def456", "git_sha_source": "git_head"},
    ):
        yield


def test_new_freeze_persists_fraction_units_and_masses(prod_db, eval_db, patch_git_sha):
    seed_tier_a_fixture(prod_db)
    result = create_or_reuse_freeze(900001, prod_conn=prod_db, eval_conn=eval_db)
    assert result["status"] == "created"
    row = eval_db.execute(
        "SELECT * FROM frozen_predictions WHERE prediction_id=?",
        (result["freeze_id"],),
    ).fetchone()
    assert row["probability_unit"] == PROBABILITY_UNIT_FRACTION
    assert row["feature_schema_version"]
    assert 0.0 <= float(row["home_probability"]) <= 1.0
    assert row["home_probability_pct"] is not None
    assert float(row["home_probability_pct"]) == pytest.approx(float(row["home_probability"]) * 100.0, rel=1e-6)
    assert row["top5_mass"] is not None
    assert row["entropy"] is not None

    ranks = eval_db.execute(
        "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
        (result["freeze_id"],),
    ).fetchall()
    assert len(ranks) >= 5
    assert all(r["probability"] is not None for r in ranks[:5])
    assert all(0.0 <= float(r["probability"]) <= 1.0 for r in ranks[:5])
    mass = sum(float(r["probability"]) for r in ranks[:5])
    assert float(row["top5_mass"]) == pytest.approx(mass, rel=1e-5)

    payload = json.loads(row["complete_payload_json"])
    assert payload.get("probability_unit") == PROBABILITY_UNIT_FRACTION
    assert "evidence" in payload
