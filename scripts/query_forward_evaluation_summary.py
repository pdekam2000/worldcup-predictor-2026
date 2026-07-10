#!/usr/bin/env python3
"""Read-only forward evaluation query tool — Tier A + Tier B."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.constants import HIT
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.evaluate import rank_distribution


def _days_clause(days: int | None, alias: str = "me") -> tuple[str, list]:
    if days is None:
        return "", []
    return f" AND {alias}.evaluation_timestamp >= datetime('now', ?)", [f"-{int(days)} days"]


def _summary(days: int | None, *, tier: str | None = None) -> dict:
    conn = connect_eval_db()
    try:
        params: list = []
        where = ""
        if tier:
            where += " WHERE COALESCE(validation_tier, tier) = ?"
            params.append(tier)
        rows = conn.execute(
            f"""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN evaluation_status='PENDING' THEN 1 ELSE 0 END) AS pending,
                   SUM(CASE WHEN evaluation_status='EVALUATED' THEN 1 ELSE 0 END) AS evaluated
            FROM frozen_predictions{where}
            """,
            params,
        ).fetchone()
        return dict(rows) if rows else {}
    finally:
        conn.close()


def _compare_tiers(days: int | None) -> dict:
    conn = connect_eval_db()
    try:
        dc, dp = _days_clause(days, "me")
        rows = conn.execute(
            f"""
            SELECT COALESCE(fp.validation_tier, fp.tier) AS tier,
                   SUM(CASE WHEN me.ecse_top1_hit='{HIT}' THEN 1 ELSE 0 END) AS top1_hits,
                   SUM(CASE WHEN me.ecse_top3_hit='{HIT}' THEN 1 ELSE 0 END) AS top3_hits,
                   SUM(CASE WHEN me.ecse_top5_hit='{HIT}' THEN 1 ELSE 0 END) AS top5_hits,
                   SUM(CASE WHEN me.wde_hit='{HIT}' THEN 1 ELSE 0 END) AS wde_hits,
                   COUNT(*) AS n
            FROM frozen_predictions fp
            JOIN market_evaluations me ON me.prediction_id = fp.prediction_id
            WHERE COALESCE(fp.validation_tier, fp.tier) IN ('A', 'B'){dc}
            GROUP BY COALESCE(fp.validation_tier, fp.tier)
            """,
            dp,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _by_competition(competition: str, days: int | None, *, tier: str | None = None) -> list[dict]:
    conn = connect_eval_db()
    try:
        params: list = [competition]
        where = "WHERE fp.competition = ?"
        if tier:
            where += " AND COALESCE(fp.validation_tier, fp.tier) = ?"
            params.append(tier)
        if days is not None:
            where += " AND me.evaluation_timestamp >= datetime('now', ?)"
            params.append(f"-{int(days)} days")
        rows = conn.execute(
            f"""
            SELECT fp.competition, fp.competition_family,
                   SUM(CASE WHEN me.ecse_top1_hit='{HIT}' THEN 1 ELSE 0 END) AS top1_hits,
                   SUM(CASE WHEN me.ecse_top3_hit='{HIT}' THEN 1 ELSE 0 END) AS top3_hits,
                   SUM(CASE WHEN me.ecse_top5_hit='{HIT}' THEN 1 ELSE 0 END) AS top5_hits,
                   COUNT(*) AS n
            FROM frozen_predictions fp
            JOIN market_evaluations me ON me.prediction_id = fp.prediction_id
            {where}
            GROUP BY fp.competition, fp.competition_family
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _by_competition_family(family: str, days: int | None) -> list[dict]:
    conn = connect_eval_db()
    try:
        params: list = [family]
        where = "WHERE fp.competition_family = ?"
        if days is not None:
            where += " AND me.evaluation_timestamp >= datetime('now', ?)"
            params.append(f"-{int(days)} days")
        rows = conn.execute(
            f"""
            SELECT fp.competition_family, COUNT(*) AS n,
                   SUM(CASE WHEN me.ecse_top3_hit='{HIT}' THEN 1 ELSE 0 END) AS top3_hits
            FROM frozen_predictions fp
            JOIN market_evaluations me ON me.prediction_id = fp.prediction_id
            {where}
            GROUP BY fp.competition_family
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _conflict_only(days: int | None) -> list[dict]:
    conn = connect_eval_db()
    try:
        params: list = []
        where = "WHERE pc.conflict_class != 'aligned'"
        if days is not None:
            where += " AND me.evaluation_timestamp >= datetime('now', ?)"
            params.append(f"-{int(days)} days")
        rows = conn.execute(
            f"""
            SELECT fp.fixture_id, fp.match_name, fp.competition,
                   COALESCE(fp.validation_tier, fp.tier) AS tier,
                   pc.conflict_class, me.ecse_top1_hit, me.actual_score_rank
            FROM prediction_context pc
            JOIN frozen_predictions fp ON fp.prediction_id = pc.prediction_id
            JOIN market_evaluations me ON me.prediction_id = pc.prediction_id
            {where}
            ORDER BY me.evaluation_timestamp DESC
            LIMIT 100
            """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Query forward evaluation DB (read-only)")
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--competition", default=None)
    parser.add_argument("--competition-family", default=None)
    parser.add_argument("--tier", default=None, choices=["A", "B"])
    parser.add_argument("--compare-tiers", action="store_true")
    parser.add_argument("--entropy-bucket", default=None)
    parser.add_argument("--conflict-only", action="store_true")
    parser.add_argument("--rank-distribution", action="store_true")
    parser.add_argument("--top3-performance", action="store_true")
    parser.add_argument("--top5-performance", action="store_true")
    args = parser.parse_args()

    out: dict = {"read_only": True}
    if args.compare_tiers:
        out["tier_comparison"] = _compare_tiers(args.days)
    if args.rank_distribution:
        conn = connect_eval_db()
        try:
            out["rank_distribution"] = rank_distribution(conn, days=args.days)
        finally:
            conn.close()
    if args.competition:
        out["by_competition"] = _by_competition(args.competition, args.days, tier=args.tier)
    if args.competition_family:
        out["by_competition_family"] = _by_competition_family(args.competition_family, args.days)
    if args.conflict_only:
        out["conflict_rows"] = _conflict_only(args.days)
    if args.top3_performance or args.top5_performance:
        conn = connect_eval_db()
        try:
            col = "ecse_top3_hit" if args.top3_performance else "ecse_top5_hit"
            params: list = []
            where = ""
            if args.days is not None:
                where = "WHERE evaluation_timestamp >= datetime('now', ?)"
                params.append(f"-{int(args.days)} days")
            rows = conn.execute(
                f"SELECT {col} AS hit, COUNT(*) AS c FROM market_evaluations {where} GROUP BY {col}",
                params,
            ).fetchall()
            out[col] = [dict(r) for r in rows]
        finally:
            conn.close()
    out["summary"] = _summary(args.days, tier=args.tier)
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
