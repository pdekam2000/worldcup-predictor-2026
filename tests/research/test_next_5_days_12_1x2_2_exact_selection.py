"""Smoke tests for next-5-days 12×1X2 + 2 low-goal selection helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path("scripts/run_next_5_days_12_1x2_2_exact_selection.py")
    spec = importlib.util.spec_from_file_location("n5_sel", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_default_dates():
    m = _load()
    assert m.DEFAULT_DATES == ["2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]


def test_norm_and_market_dir():
    m = _load()
    assert m.norm_dir("away_win") == "away"
    assert m.market_dir({"home": 2.1, "draw": 3.4, "away": 3.5}) == "home"


def test_consensus_top5_deterministic():
    m = _load()
    can = [{"score": "1-0", "probability": 0.2}, {"score": "0-0", "probability": 0.15}, {"score": "2-0", "probability": 0.12}, {"score": "1-1", "probability": 0.1}, {"score": "0-1", "probability": 0.08}]
    ex = [{"score": "1-0", "probability": 0.18}, {"score": "2-0", "probability": 0.14}, {"score": "0-0", "probability": 0.13}, {"score": "1-1", "probability": 0.11}, {"score": "3-0", "probability": 0.09}]
    cons = m.build_consensus_top5(can, ex, ["1-0", "0-0"], ["1-0", "1-1"])
    assert len(cons) == 5
    assert cons[0]["rank"] == 1
    assert cons[0]["consensus_score"] == "1-0"
    assert "canonical" in cons[0]["models_containing"]


def test_agreement_requires_core_trio():
    m = _load()
    assert m.classify_1x2_agreement({"wde": "home", "ecse": "away", "exact_v2": "home"}, market="home", forensic_severe=False, fresh=True, no_bet=False) == "DIRECTION_CONFLICT"
    assert m.classify_1x2_agreement({"wde": "home", "ecse": "home", "exact_v2": "home", "lambda_v2": "home", "dna": "home", "twins": "home"}, market="home", forensic_severe=False, fresh=True, no_bet=False) == "UNANIMOUS_DIRECTION"
