"""Invariants for lambda team-strength research (shadow-only)."""

from __future__ import annotations

from worldcup_predictor.research.ecse_lambda_extraction import LAMBDA_CEIL, LAMBDA_FLOOR, extract_lambdas
from worldcup_predictor.research.lambda_team_strength.metrics import clip_lambda, normalize_team
from worldcup_predictor.research.lambda_team_strength.team_strength import team_flags


def test_extract_lambdas_clips_and_sums():
    row = {
        "registry_fixture_id": 1,
        "ft_home_closing": 2.0,
        "ft_draw_closing": 3.4,
        "ft_away_closing": 3.8,
        "ou_over_25_closing": 1.9,
        "ou_under_25_closing": 1.9,
        "btts_yes_closing": 1.8,
        "btts_no_closing": 2.0,
        "team_home_over_05_closing": 1.4,
        "team_home_under_05_closing": 2.8,
        "team_away_over_05_closing": 1.6,
        "team_away_under_05_closing": 2.3,
    }
    out = extract_lambdas(row)
    assert out is not None
    assert LAMBDA_FLOOR <= out["lambda_home"] <= LAMBDA_CEIL
    assert LAMBDA_FLOOR <= out["lambda_away"] <= LAMBDA_CEIL
    assert abs(out["lambda_total"] - (out["lambda_home"] + out["lambda_away"])) < 1e-6


def test_ou45_not_required_for_extraction():
    """O/U 4.5 is loaded in SQL inventory but unused by extract_lambdas."""
    row = {
        "registry_fixture_id": 2,
        "ft_home_closing": 1.8,
        "ft_away_closing": 4.2,
        "ft_draw_closing": 3.5,
        "ou_over_25_closing": 2.1,
        "ou_under_25_closing": 1.7,
        "ou_over_45_closing": 5.0,
        "ou_under_45_closing": 1.15,
    }
    out = extract_lambdas(row)
    assert out is not None
    # Presence of 4.5 must not be necessary; same path works without it
    row2 = dict(row)
    del row2["ou_over_45_closing"]
    del row2["ou_under_45_closing"]
    out2 = extract_lambdas(row2)
    assert out2 is not None
    assert abs(out["lambda_total"] - out2["lambda_total"]) < 1e-9


def test_clip_and_normalize():
    assert clip_lambda(0.01) == LAMBDA_FLOOR
    assert clip_lambda(9.0) == LAMBDA_CEIL
    assert normalize_team("IFK Göteborg") == "ifk goteborg" or "goteborg" in normalize_team("IFK Göteborg")
    assert "malmo" in normalize_team("Malmö FF") or normalize_team("Malmö FF") == "malmo"
    assert team_flags("Arsenal U21")["reserve_or_youth"] is True
