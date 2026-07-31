"""Parallel baseline vs calibrated candidate forward shadow — research-only."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.constants import BASELINE_POLICY
from worldcup_predictor.research.bet_portfolio_manager.threshold_calibration.policy_engine import (
    decide_under_policy,
    group_days,
    league_reliability,
)


SCHEMA = {
    "research_only": True,
    "table": "forward_shadow_policy_comparison",
    "fields": [
        "date",
        "baseline_score",
        "candidate_score",
        "baseline_grade",
        "candidate_grade",
        "baseline_action",
        "candidate_action",
        "baseline_selected_fixtures",
        "candidate_selected_fixtures",
        "baseline_capital",
        "candidate_capital",
        "baseline_risk",
        "candidate_risk",
        "realized_ft_results",
        "baseline_pnl",
        "candidate_pnl",
        "baseline_roi",
        "candidate_roi",
        "drawdown_difference",
        "exposure_difference",
    ],
    "no_real_betting": True,
    "no_production_integration": True,
}


def ensure_shadow_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS forward_shadow_policy_comparison (
                date TEXT PRIMARY KEY,
                baseline_score REAL,
                candidate_score REAL,
                baseline_grade TEXT,
                candidate_grade TEXT,
                baseline_action TEXT,
                candidate_action TEXT,
                baseline_selected_fixtures TEXT,
                candidate_selected_fixtures TEXT,
                baseline_capital REAL,
                candidate_capital REAL,
                baseline_risk REAL,
                candidate_risk REAL,
                realized_ft_results TEXT,
                baseline_pnl REAL,
                candidate_pnl REAL,
                baseline_roi REAL,
                candidate_roi REAL,
                drawdown_difference REAL,
                exposure_difference REAL
            )
            """
        )
        con.commit()
    finally:
        con.close()


def compare_forward_days(
    fixtures: list[dict[str, Any]],
    *,
    baseline_policy: dict[str, Any] | None = None,
    candidate_policy: dict[str, Any],
    db_path: Path | None = None,
    max_days: int = 30,
) -> dict[str, Any]:
    base = baseline_policy or BASELINE_POLICY
    days = group_days(fixtures)
    lr = league_reliability(fixtures)
    keys = sorted(days.keys())[-max_days:]
    rows = []
    eq_b = eq_c = 0.0
    peak_b = peak_c = 0.0
    dd_b = dd_c = 0.0
    for date in keys:
        fx = days[date]
        b = decide_under_policy(fx, policy=base, league_reliability_map=lr)
        c = decide_under_policy(fx, policy=candidate_policy, league_reliability_map=lr)
        eq_b += float(b.get("realized_pnl_evaluation_only") or 0)
        eq_c += float(c.get("realized_pnl_evaluation_only") or 0)
        peak_b = max(peak_b, eq_b)
        peak_c = max(peak_c, eq_c)
        dd_b = max(dd_b, peak_b - eq_b)
        dd_c = max(dd_c, peak_c - eq_c)
        b_exp = float(b.get("exposure_units") or 0)
        c_exp = float(c.get("exposure_units") or 0)
        b_pnl = float(b.get("realized_pnl_evaluation_only") or 0)
        c_pnl = float(c.get("realized_pnl_evaluation_only") or 0)
        ft = [
            {
                "fixture_id": f.get("fixture_id"),
                "actual_score": f.get("actual_score"),
                "hit_insurance": f.get("hit_insurance"),
            }
            for f in fx
        ]
        row = {
            "date": date,
            "baseline_score": b.get("score"),
            "candidate_score": c.get("score"),
            "baseline_grade": b.get("grade"),
            "candidate_grade": c.get("grade"),
            "baseline_action": b.get("action"),
            "candidate_action": c.get("action"),
            "baseline_selected_fixtures": b.get("selected_fixture_ids"),
            "candidate_selected_fixtures": c.get("selected_fixture_ids"),
            "baseline_capital": b_exp,
            "candidate_capital": c_exp,
            "baseline_risk": 1.0 - float((b.get("components") or {}).get("low_residual_risk") or 50) / 100.0,
            "candidate_risk": 1.0 - float((c.get("components") or {}).get("low_residual_risk") or 50) / 100.0,
            "realized_ft_results": ft,
            "baseline_pnl": b_pnl,
            "candidate_pnl": c_pnl,
            "baseline_roi": round(b_pnl / b_exp, 6) if b_exp > 0 else None,
            "candidate_roi": round(c_pnl / c_exp, 6) if c_exp > 0 else None,
            "drawdown_difference": round(dd_c - dd_b, 6),
            "exposure_difference": round(c_exp - b_exp, 6),
        }
        rows.append(row)

    if db_path is not None:
        ensure_shadow_db(db_path)
        con = sqlite3.connect(str(db_path))
        try:
            for r in rows:
                con.execute(
                    """
                    INSERT OR REPLACE INTO forward_shadow_policy_comparison VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        r["date"],
                        r["baseline_score"],
                        r["candidate_score"],
                        r["baseline_grade"],
                        r["candidate_grade"],
                        r["baseline_action"],
                        r["candidate_action"],
                        json.dumps(r["baseline_selected_fixtures"]),
                        json.dumps(r["candidate_selected_fixtures"]),
                        r["baseline_capital"],
                        r["candidate_capital"],
                        r["baseline_risk"],
                        r["candidate_risk"],
                        json.dumps(r["realized_ft_results"]),
                        r["baseline_pnl"],
                        r["candidate_pnl"],
                        r["baseline_roi"],
                        r["candidate_roi"],
                        r["drawdown_difference"],
                        r["exposure_difference"],
                    ),
                )
            con.commit()
        finally:
            con.close()

    return {
        "research_only": True,
        "no_real_betting_execution": True,
        "no_production_integration": True,
        "n_days": len(rows),
        "days": rows,
        "schema": SCHEMA,
        "db_path": str(db_path) if db_path else None,
    }
