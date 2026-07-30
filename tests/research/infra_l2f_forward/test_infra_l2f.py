"""Tests for infra L2-F forward shadow / alternate totals / orchestration."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row
from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas
from worldcup_predictor.research.infra_l2f_forward.alternate_totals_capture_service import (
    capture_alternate_totals,
    lines_from_ecse_odds_row,
)
from worldcup_predictor.research.infra_l2f_forward.shadow_orchestrator import run_shadow_pipeline
from worldcup_predictor.research.lambda_team_strength.team_strength import load_strength_store
from worldcup_predictor.research.football_strength_foundation.historical_match_service import (
    HistoricalMatchService,
)
from worldcup_predictor.research.football_strength_foundation.team_strength_engine import TeamStrengthEngine


def test_lines_from_odds_row_no_synthesis():
    row = {"ou_over_25_closing": 1.9, "ou_under_25_closing": 1.9}
    lines = lines_from_ecse_odds_row(row)
    assert [ln.line for ln in lines] == [2.5]
    assert 3.5 not in [ln.line for ln in lines]
    assert 4.5 not in [ln.line for ln in lines]


def test_capture_records_missing(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    out = capture_alternate_totals(conn, fixture_id=1, odds_row={"ou_over_25_closing": 2.0, "ou_under_25_closing": 1.8})
    assert 2.5 in out["lines_present"]
    n_miss = conn.execute(
        "SELECT COUNT(*) FROM alternate_totals_capture_status WHERE status='MISSING'"
    ).fetchone()[0]
    assert n_miss == 2  # 3.5 and 4.5
    conn.close()


def test_extract_lambdas_unchanged_by_ou45_fields():
    base = {
        "registry_fixture_id": 1,
        "ft_home_closing": 2.1,
        "ft_draw_closing": 3.4,
        "ft_away_closing": 3.5,
        "ou_over_25_closing": 1.95,
        "ou_under_25_closing": 1.85,
        "ou_over_35_closing": 2.6,
        "ou_under_35_closing": 1.48,
    }
    a = extract_lambdas(base)
    b = extract_lambdas({**base, "ou_over_45_closing": 4.5, "ou_under_45_closing": 1.18})
    assert a is not None and b is not None
    assert abs(a["lambda_total"] - b["lambda_total"]) < 1e-12


def test_shadow_pipeline_never_blocks_canonical(tmp_path):
    # minimal in-memory: use real FI store may be heavy; still OK for smoke
    fi = str((__import__("pathlib").Path(__file__).resolve().parents[3] / "data" / "football_intelligence.db"))
    store = load_strength_store(fi, max_rows=5000)
    engine = TeamStrengthEngine(HistoricalMatchService(store=store))
    conn = sqlite3.connect(tmp_path / "e.db")
    res = run_shadow_pipeline(
        conn=conn,
        fixture_id=999001,
        home_team="Hammarby FF",
        away_team="Kalmar FF",
        league="allsvenskan",
        cutoff=datetime(2026, 7, 12),
        engine=engine,
        odds_row=None,
        canonical_lh=1.5,
        canonical_la=1.2,
    )
    assert res.canonical_blocked is False
    assert len(res.stages) == 3
    conn.close()
