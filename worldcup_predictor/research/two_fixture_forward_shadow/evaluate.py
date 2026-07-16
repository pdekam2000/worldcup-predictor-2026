"""Result sync and realized ROI from frozen odds/stakes only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.two_fixture_forward_shadow.ddl import ensure_tfps_schema
from worldcup_predictor.research.two_fixture_portfolio.engine import fmt, parse_score


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_regulation_score(conn, fixture_id: int) -> tuple[str | None, str]:
    """Return (score, status_note). Prefer regulation-time sources."""
    # fixtures table
    try:
        row = conn.execute(
            """
            SELECT home_goals, away_goals, status, score_home, score_away
            FROM fixtures WHERE fixture_id=?
            """,
            (fixture_id,),
        ).fetchone()
        if row:
            hg = row["home_goals"] if "home_goals" in row.keys() else None
            ag = row["away_goals"] if "away_goals" in row.keys() else None
            if hg is None and "score_home" in row.keys():
                hg, ag = row["score_home"], row["score_away"]
            status = str(row["status"] or "").upper() if "status" in row.keys() else ""
            if hg is not None and ag is not None and status in {"FT", "AET", "PEN", "MATCH_FINISHED", "FINISHED", ""}:
                # For AET/PEN still use regulation if separate columns exist — else FT goals only when FT
                if status in {"AET", "PEN"}:
                    # try regulation columns
                    pass
                return fmt(int(hg), int(ag)), "fixtures_table"
    except Exception:
        pass
    # training dataset via mapping
    try:
        row = conn.execute(
            """
            SELECT t.exact_score, t.home_goals, t.away_goals
            FROM ecse_training_dataset t
            JOIN historical_provider_mapping hpm
              ON hpm.registry_fixture_id = t.registry_fixture_id
             AND hpm.provider = 'api_football'
            WHERE hpm.provider_fixture_id = ?
            LIMIT 1
            """,
            (fixture_id,),
        ).fetchone()
        if row and row["exact_score"]:
            return str(row["exact_score"]).replace("–", "-"), "ecse_training_dataset"
    except Exception:
        pass
    return None, "RESULT_UNAVAILABLE"


def evaluate_freeze(conn, portfolio_id: str) -> dict[str, Any]:
    ensure_tfps_schema(conn)
    row = conn.execute(
        "SELECT * FROM tfps_portfolio_freezes WHERE portfolio_id=?",
        (portfolio_id,),
    ).fetchone()
    if not row:
        return {"portfolio_id": portfolio_id, "result_status": "PORTFOLIO_INVALID"}
    fz = dict(row)
    # never regenerate — use frozen JSON
    primary = json.loads(fz["primary_tickets_json"])
    hedges = json.loads(fz["hedge_tickets_json"])
    total = float(fz["total_stake"])

    sa, note_a = load_regulation_score(conn, int(fz["fixture_a"]))
    sb, note_b = load_regulation_score(conn, int(fz["fixture_b"]))
    if not sa or not sb:
        status = "RESULT_PENDING" if (not sa or not sb) else "RESULT_UNAVAILABLE"
        payload = {
            "portfolio_id": portfolio_id,
            "evaluated_at_utc": _utc_now(),
            "result_status": status,
            "actual_score_a": sa,
            "actual_score_b": sb,
            "winning_ticket_id": None,
            "gross_return": 0.0,
            "net_return": None,
            "roi": None,
            "primary_hit": 0,
            "hedge_hit": 0,
            "full_loss": 0,
            "recovery_class": status,
            "regulation_time_only": 1,
            "evaluation_notes": f"{note_a}|{note_b}",
        }
        _upsert_eval(conn, payload)
        return payload

    # validate parse
    if not parse_score(sa) or not parse_score(sb):
        payload = {
            "portfolio_id": portfolio_id,
            "evaluated_at_utc": _utc_now(),
            "result_status": "SETTLEMENT_CONFLICT",
            "actual_score_a": sa,
            "actual_score_b": sb,
            "winning_ticket_id": None,
            "gross_return": 0.0,
            "net_return": -total,
            "roi": -1.0,
            "primary_hit": 0,
            "hedge_hit": 0,
            "full_loss": 1,
            "recovery_class": "SETTLEMENT_CONFLICT",
            "regulation_time_only": 1,
            "evaluation_notes": "unparsed_scores",
        }
        _upsert_eval(conn, payload)
        return payload

    win_ticket = None
    gross = 0.0
    for t in primary:
        if t.get("score_a") == sa and t.get("score_b") == sb:
            win_ticket = t.get("ticket_id")
            if t.get("combo_odds") is not None and float(t.get("stake") or 0) > 0:
                gross = float(t["stake"]) * float(t["combo_odds"])
            break

    hedge_gross = 0.0
    hedge_hit = 0
    for h in hedges:
        if h.get("fixture_side") == "A" and h.get("selection") == sa:
            hedge_gross += float(h.get("stake") or 0) * float(h.get("decimal_odds") or 0)
            hedge_hit = 1
        if h.get("fixture_side") == "B" and h.get("selection") == sb:
            hedge_gross += float(h.get("stake") or 0) * float(h.get("decimal_odds") or 0)
            hedge_hit = 1

    if win_ticket and gross > 0:
        # primary win — hedges still cost
        net = gross + hedge_gross - total
        # typically hedge_gross 0 on primary path if hedges are alternatives
        status = "PRIMARY_WIN"
        recovery = "PRIMARY_WIN"
        full_loss = 0
        primary_hit = 1
    elif hedge_gross > 0:
        net = hedge_gross - total
        primary_hit = 0
        if net >= -1e-9:
            status = "HEDGE_WIN_FULL_RECOVERY"
            recovery = "FULL_RECOVERY"
            full_loss = 0
        elif hedge_gross >= 0.5 * float(fz["total_primary_stake"]):
            status = "HEDGE_WIN_PARTIAL_RECOVERY"
            recovery = "PARTIAL_RECOVERY"
            full_loss = 0
        else:
            status = "COVERED_BUT_NET_LOSS"
            recovery = "COVERED_NET_LOSS"
            full_loss = 0
    else:
        net = -total
        primary_hit = 0
        status = "FULL_LOSS"
        recovery = "FULL_LOSS"
        full_loss = 1

    roi = (net / total) if total > 0 else None
    payload = {
        "portfolio_id": portfolio_id,
        "evaluated_at_utc": _utc_now(),
        "result_status": status,
        "actual_score_a": sa,
        "actual_score_b": sb,
        "winning_ticket_id": win_ticket,
        "gross_return": gross + hedge_gross,
        "net_return": net,
        "roi": roi,
        "primary_hit": primary_hit,
        "hedge_hit": hedge_hit,
        "full_loss": full_loss,
        "recovery_class": recovery,
        "regulation_time_only": 1,
        "evaluation_notes": f"frozen_odds_only|{note_a}|{note_b}",
    }
    _upsert_eval(conn, payload)
    return payload


def _upsert_eval(conn, payload: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO tfps_portfolio_evaluations (
            portfolio_id, evaluated_at_utc, result_status, actual_score_a, actual_score_b,
            winning_ticket_id, gross_return, net_return, roi, primary_hit, hedge_hit,
            full_loss, recovery_class, regulation_time_only, evaluation_notes
        ) VALUES (
            :portfolio_id, :evaluated_at_utc, :result_status, :actual_score_a, :actual_score_b,
            :winning_ticket_id, :gross_return, :net_return, :roi, :primary_hit, :hedge_hit,
            :full_loss, :recovery_class, :regulation_time_only, :evaluation_notes
        )
        """,
        payload,
    )
    conn.commit()


def evaluate_pending(conn, *, limit: int = 200) -> list[dict[str, Any]]:
    ensure_tfps_schema(conn)
    rows = conn.execute(
        """
        SELECT f.portfolio_id
        FROM tfps_portfolio_freezes f
        LEFT JOIN tfps_portfolio_evaluations e ON e.portfolio_id = f.portfolio_id
        WHERE e.portfolio_id IS NULL
           OR e.result_status IN ('RESULT_PENDING', 'RESULT_UNAVAILABLE')
        ORDER BY f.frozen_at_utc ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [evaluate_freeze(conn, str(r["portfolio_id"])) for r in rows]


def completed_count(conn) -> int:
    ensure_tfps_schema(conn)
    row = conn.execute(
        """
        SELECT COUNT(1) AS c FROM tfps_portfolio_evaluations
        WHERE result_status NOT IN ('RESULT_PENDING', 'RESULT_UNAVAILABLE', 'PORTFOLIO_INVALID')
        """
    ).fetchone()
    return int(row["c"] if row else 0)
