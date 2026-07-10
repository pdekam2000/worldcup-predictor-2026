"""Unified weekly forward evaluation report — Tier A + Tier B."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.forward_evaluation.constants import HIT, REPORTS_DIR
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.evaluate import rank_distribution


def _rate(hits: int, total: int) -> str:
    if total <= 0:
        return "n/a"
    return f"{100.0 * hits / total:.1f}%"


def _market_accuracy(eval_conn, column: str, days: int, *, tier: str | None = None) -> tuple[int, int]:
    params: list = [f"-{int(days)} days"]
    tier_clause = ""
    if tier:
        tier_clause = " AND fp.validation_tier = ?"
        params.append(tier)
    rows = eval_conn.execute(
        f"""
        SELECT me.{column} AS v
        FROM market_evaluations me
        JOIN frozen_predictions fp ON fp.prediction_id = me.prediction_id
        WHERE me.evaluation_timestamp >= datetime('now', ?){tier_clause}
        """,
        params,
    ).fetchall()
    total = sum(1 for r in rows if r["v"] in (HIT, "MISS"))
    hits = sum(1 for r in rows if r["v"] == HIT)
    return hits, total


def _tier_counts(eval_conn, days: int) -> dict[str, int]:
    rows = eval_conn.execute(
        """
        SELECT COALESCE(validation_tier, tier) AS t, COUNT(*) AS c
        FROM frozen_predictions
        WHERE frozen_at >= datetime('now', ?)
        GROUP BY COALESCE(validation_tier, tier)
        """,
        (f"-{int(days)} days",),
    ).fetchall()
    return {str(r["t"]): int(r["c"]) for r in rows}


def generate_weekly_report(*, end_date: date | None = None, days: int = 7) -> Path:
    end = end_date or date.today()
    start = end - timedelta(days=days)
    eval_conn = connect_eval_db()
    try:
        total_frozen = eval_conn.execute("SELECT COUNT(*) AS c FROM frozen_predictions").fetchone()["c"]
        finished = eval_conn.execute(
            "SELECT COUNT(*) AS c FROM frozen_predictions WHERE evaluation_status='EVALUATED'"
        ).fetchone()["c"]
        pending = eval_conn.execute(
            "SELECT COUNT(*) AS c FROM frozen_predictions WHERE evaluation_status='PENDING'"
        ).fetchone()["c"]
        ranks = rank_distribution(eval_conn, days=days)
        tier_counts = _tier_counts(eval_conn, days)

        wde_h, wde_t = _market_accuracy(eval_conn, "wde_hit", days)
        t1_h, t1_t = _market_accuracy(eval_conn, "ecse_top1_hit", days)
        t3_h, t3_t = _market_accuracy(eval_conn, "ecse_top3_hit", days)
        t5_h, t5_t = _market_accuracy(eval_conn, "ecse_top5_hit", days)

        wde_a, tot_a = _market_accuracy(eval_conn, "wde_hit", days, tier="A")
        wde_b, tot_b = _market_accuracy(eval_conn, "wde_hit", days, tier="B")
        t3_a, tot3_a = _market_accuracy(eval_conn, "ecse_top3_hit", days, tier="A")
        t3_b, tot3_b = _market_accuracy(eval_conn, "ecse_top3_hit", days, tier="B")
        t5_a, tot5_a = _market_accuracy(eval_conn, "ecse_top5_hit", days, tier="A")
        t5_b, tot5_b = _market_accuracy(eval_conn, "ecse_top5_hit", days, tier="B")

        comp_rows = eval_conn.execute(
            """
            SELECT fp.competition, fp.competition_family,
                   SUM(CASE WHEN me.ecse_top3_hit='HIT' THEN 1 ELSE 0 END) AS top3_hits,
                   COUNT(*) AS n
            FROM market_evaluations me
            JOIN frozen_predictions fp ON fp.prediction_id = me.prediction_id
            WHERE me.evaluation_timestamp >= datetime('now', ?)
            GROUP BY fp.competition, fp.competition_family
            ORDER BY top3_hits DESC, n DESC
            LIMIT 10
            """,
            (f"-{int(days)} days",),
        ).fetchall()

        lines = [
            f"# Weekly Forward Evaluation Report ({start.isoformat()} to {end.isoformat()})",
            "",
            "## OVERALL",
            f"- Total frozen predictions: {total_frozen}",
            f"- Finished evaluated (all time): {finished}",
            f"- Pending: {pending}",
            f"- WDE accuracy: {_rate(wde_h, wde_t)} ({wde_h}/{wde_t})",
            f"- ECSE Top1: {_rate(t1_h, t1_t)} ({t1_h}/{t1_t})",
            f"- ECSE Top3: {_rate(t3_h, t3_t)} ({t3_h}/{t3_t})",
            f"- ECSE Top5: {_rate(t5_h, t5_t)} ({t5_h}/{t5_t})",
            "",
            "## TRUSTED / TIER A",
            f"- Frozen (period): {tier_counts.get('A', 0)}",
            f"- WDE: {_rate(wde_a, tot_a)} ({wde_a}/{tot_a})",
            f"- Top3: {_rate(t3_a, tot3_a)} ({t3_a}/{tot3_a})",
            f"- Top5: {_rate(t5_a, tot5_a)} ({t5_a}/{tot5_a})",
            "",
            "## TEST PHASE / TIER B",
            f"- Frozen (period): {tier_counts.get('B', 0)}",
            f"- WDE: {_rate(wde_b, tot_b)} ({wde_b}/{tot_b})",
            f"- Top3: {_rate(t3_b, tot3_b)} ({t3_b}/{tot3_b})",
            f"- Top5: {_rate(t5_b, tot5_b)} ({t5_b}/{tot5_b})",
            "",
            "## A VS B COMPARISON",
            f"- Tier A Top3: {_rate(t3_a, tot3_a)} vs Tier B Top3: {_rate(t3_b, tot3_b)}",
            f"- Tier A Top5: {_rate(t5_a, tot5_a)} vs Tier B Top5: {_rate(t5_b, tot5_b)}",
            "",
            "## EXACT SCORE RANK DISTRIBUTION",
            f"- Rank1: {ranks.get('1', 0)}",
            f"- Rank2: {ranks.get('2', 0)}",
            f"- Rank3: {ranks.get('3', 0)}",
            f"- Rank4: {ranks.get('4', 0)}",
            f"- Rank5: {ranks.get('5', 0)}",
            f"- OUTSIDE_TOP5: {ranks.get('OUTSIDE_TOP5', 0)}",
            "",
            "## COMPETITION PERFORMANCE",
        ]
        for row in comp_rows:
            lines.append(f"- {row['competition']} ({row['competition_family']}): Top3 {row['top3_hits']}/{row['n']}")

        lines.extend(
            [
                "",
                "## ENTROPY / CONFLICT / ODDS / DATA QUALITY",
                "- See prediction_context table for bucketed analysis dimensions.",
                "",
                "**OBSERVATIONS ONLY — NO AUTOMATIC MODEL MODIFICATION**",
                "",
                "_Read-only evidence report. No model recommendations. No weight updates. No promotion decisions._",
            ]
        )
        out = (project_root() / REPORTS_DIR / f"WEEKLY_FORWARD_EVALUATION_REPORT_{end.strftime('%Y_%m_%d')}.md").resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out
    finally:
        eval_conn.close()
