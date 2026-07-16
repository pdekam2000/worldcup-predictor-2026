"""Owner-only observability for forward shadow collection."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
    COHORT_A_END,
    HEALTH_STATUSES,
    PRIMARY_SELECTION_GATE,
    STRATEGY_VERSION,
)
from worldcup_predictor.research.two_fixture_forward_shadow.ddl import ensure_tfps_schema
from worldcup_predictor.research.two_fixture_forward_shadow.evaluate import completed_count


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def set_obs(conn, key: str, value: Any) -> None:
    ensure_tfps_schema(conn)
    conn.execute(
        """
        INSERT OR REPLACE INTO tfps_observability(key, value_json, updated_at_utc)
        VALUES (?, ?, ?)
        """,
        (key, json.dumps(value, default=str), _utc_now()),
    )
    conn.commit()


def build_status(conn) -> dict[str, Any]:
    ensure_tfps_schema(conn)
    frozen = conn.execute("SELECT COUNT(1) AS c FROM tfps_portfolio_freezes").fetchone()["c"]
    pending = conn.execute(
        """
        SELECT COUNT(1) AS c FROM tfps_portfolio_freezes f
        LEFT JOIN tfps_portfolio_evaluations e ON e.portfolio_id=f.portfolio_id
        WHERE e.portfolio_id IS NULL OR e.result_status IN ('RESULT_PENDING','RESULT_UNAVAILABLE')
        """
    ).fetchone()["c"]
    done = completed_count(conn)
    primary_wins = conn.execute(
        "SELECT COUNT(1) AS c FROM tfps_portfolio_evaluations WHERE result_status='PRIMARY_WIN'"
    ).fetchone()["c"]
    full_loss = conn.execute(
        "SELECT COUNT(1) AS c FROM tfps_portfolio_evaluations WHERE full_loss=1"
    ).fetchone()["c"]
    # Equal gross ROI on completed
    eg = conn.execute(
        """
        SELECT AVG(e.roi) AS avg_roi, SUM(e.net_return) AS net, SUM(f.total_stake) AS stake
        FROM tfps_portfolio_evaluations e
        JOIN tfps_portfolio_freezes f ON f.portfolio_id=e.portfolio_id
        WHERE f.stake_strategy='EQUAL_GROSS_RETURN'
          AND e.result_status NOT IN ('RESULT_PENDING','RESULT_UNAVAILABLE','PORTFOLIO_INVALID')
        """
    ).fetchone()
    mm = conn.execute(
        """
        SELECT AVG(e.roi) AS avg_roi
        FROM tfps_portfolio_evaluations e
        JOIN tfps_portfolio_freezes f ON f.portfolio_id=e.portfolio_id
        WHERE f.stake_strategy='MINIMAX'
          AND e.result_status NOT IN ('RESULT_PENDING','RESULT_UNAVAILABLE','PORTFOLIO_INVALID')
        """
    ).fetchone()
    single_n = conn.execute(
        "SELECT COUNT(1) AS c FROM tfps_portfolio_freezes WHERE bookmaker_mode='SINGLE_BOOKMAKER_EXECUTABLE'"
    ).fetchone()["c"]
    cross_n = conn.execute(
        "SELECT COUNT(1) AS c FROM tfps_portfolio_freezes WHERE bookmaker_mode='CROSS_BOOKMAKER_THEORETICAL'"
    ).fetchone()["c"]
    cs_fixtures = conn.execute(
        "SELECT COUNT(DISTINCT fixture_id) AS c FROM correct_score_odds_lines WHERE prematch_status='prematch'"
    ).fetchone()["c"]

    health = "FORWARD_COLLECTION_HEALTHY"
    if frozen == 0:
        health = "FORWARD_COLLECTION_NO_ELIGIBLE_PAIR"
    elif done == 0 and frozen > 0:
        health = "FORWARD_COLLECTION_PARTIAL"

    cohort = "A" if done < COHORT_A_END else ("B" if done < 500 else "C")
    status = {
        "collector_active": True,
        "timer_enabled": False,
        "health": health,
        "health_allowed": sorted(HEALTH_STATUSES),
        "last_status_at": _utc_now(),
        "strategy_version": STRATEGY_VERSION,
        "primary_selection_gate": PRIMARY_SELECTION_GATE,
        "cohort_active": cohort,
        "frozen_portfolios": int(frozen),
        "pending_portfolios": int(pending),
        "completed_portfolios": int(done),
        "primary_wins": int(primary_wins),
        "full_loss_count": int(full_loss),
        "full_loss_rate": (full_loss / done) if done else None,
        "equal_gross_return_avg_roi": eg["avg_roi"] if eg else None,
        "minimax_avg_roi": mm["avg_roi"] if mm else None,
        "same_bookmaker_freezes": int(single_n),
        "cross_bookmaker_theoretical_freezes": int(cross_n),
        "cs_fixtures_with_prematch_lines": int(cs_fixtures),
        "portfolios_to_100": max(0, 100 - done),
        "portfolios_to_500": max(0, 500 - done),
        "portfolios_to_1000": max(0, 1000 - done),
        "betting_action_possible": False,
        "auto_bet": False,
        "public_exposure": False,
        "unit_of_sample": "ONE_EXECUTABLE_TWO_FIXTURE_PORTFOLIO",
        "note": "Sample size = completed evaluated portfolios, not raw CS odds lines",
    }
    set_obs(conn, "status", status)
    return status
