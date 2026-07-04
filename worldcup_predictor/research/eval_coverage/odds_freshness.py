"""Odds freshness audit for evaluated ECSE fixtures."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.research.ecse_rerank.features import is_knockout_fixture, odds_freshness_meta, parse_top10
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_exists

PHASE = "EVAL-COVERAGE-1"


def run_odds_freshness_audit(db_path: str | None = None) -> dict[str, Any]:
    conn = connect_readonly(db_path)
    if not table_exists(conn, "ecse_prediction_snapshots"):
        conn.close()
        return {"phase": PHASE, "fixtures": [], "summary": {}}

    has_odds = table_exists(conn, "odds_snapshots")
    query = """
        SELECT ec.fixture_id, ec.generated_at, ec.top_10_scorelines_json,
               f.home_team, f.away_team, f.kickoff_utc, f.status, f.round_name,
               fr.home_goals, fr.away_goals
        FROM ecse_prediction_snapshots ec
        JOIN fixtures f ON f.fixture_id = ec.fixture_id
        JOIN fixture_results fr ON fr.fixture_id = ec.fixture_id
        WHERE f.competition_key = 'world_cup_2026'
          AND fr.home_goals IS NOT NULL
          AND UPPER(f.status) IN ('FT', 'AET', 'PEN')
    """
    rows = conn.execute(query).fetchall()
    fixtures: list[dict[str, Any]] = []
    counts: dict[str, int] = {
        "FRESH_ODDS": 0,
        "STALE_ODDS": 0,
        "ODDS_FRESHNESS_UNKNOWN": 0,
        "REQUIRES_FRESH_ODDS": 0,
    }
    stale_top5_miss = 0
    stale_top5_hit = 0
    fresh_top5_miss = 0
    fresh_top5_hit = 0

    for row in rows:
        r = dict(row)
        fid = int(r["fixture_id"])
        fixture_row = {
            "fixture_id": fid,
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "kickoff_utc": r["kickoff_utc"],
            "status": r["status"],
            "round_name": r.get("round_name"),
        }
        knockout = is_knockout_fixture(fixture_row)
        odds_snap_at = None
        odds_source = None
        if has_odds:
            o = conn.execute(
                "SELECT snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
                (fid,),
            ).fetchone()
            if o:
                odds_snap_at = o["snapshot_at"]
                try:
                    payload = json.loads(o["payload_json"])
                    odds_source = payload.get("source_provider") or payload.get("source")
                except (json.JSONDecodeError, TypeError):
                    odds_source = "odds_snapshots"

        freshness = odds_freshness_meta(
            odds_snapshot_at=odds_snap_at,
            prediction_generated_at=r.get("generated_at"),
            knockout=knockout,
            odds_source=odds_source,
        )
        flag = freshness.get("freshness_flag") or "ODDS_FRESHNESS_UNKNOWN"
        counts[flag] = counts.get(flag, 0) + 1

        actual = f"{int(r['home_goals'])}-{int(r['away_goals'])}"
        top10 = parse_top10(r.get("top_10_scorelines_json"))
        top5 = [x["scoreline"] for x in sorted(top10, key=lambda x: x.get("rank", 99))[:5]]
        in_top5 = actual in top5
        if flag == "STALE_ODDS":
            if in_top5:
                stale_top5_hit += 1
            else:
                stale_top5_miss += 1
        elif flag == "FRESH_ODDS":
            if in_top5:
                fresh_top5_hit += 1
            else:
                fresh_top5_miss += 1

        fixtures.append(
            {
                "fixture_id": fid,
                "match": f"{r['home_team']} vs {r['away_team']}",
                "knockout": knockout,
                "actual_90min": actual,
                "in_top5": in_top5,
                "odds_snapshot_at": freshness.get("odds_snapshot_at"),
                "prediction_generated_at": freshness.get("prediction_generated_at"),
                "odds_age_hours": freshness.get("odds_age_hours"),
                "freshness_flag": flag,
                "stale_odds": freshness.get("stale_odds"),
            }
        )

    conn.close()
    stale_n = counts.get("STALE_ODDS", 0)
    stale_top5_rate = round(100.0 * stale_top5_hit / stale_n, 1) if stale_n else None
    return {
        "phase": PHASE,
        "fixture_count": len(fixtures),
        "counts": counts,
        "stale_top5_hit_rate_pct": stale_top5_rate,
        "stale_top5_hits": stale_top5_hit,
        "stale_top5_misses": stale_top5_miss,
        "fresh_top5_hits": fresh_top5_hit,
        "fresh_top5_misses": fresh_top5_miss,
        "fixtures": fixtures,
    }


def render_odds_freshness_markdown(payload: dict[str, Any]) -> str:
    c = payload.get("counts", {})
    lines = [
        "# EVAL-COVERAGE-1 — Odds Freshness Summary",
        "",
        f"Evaluated ECSE fixtures with 90' results: **{payload.get('fixture_count', 0)}**",
        "",
        "## Freshness Counts",
        "",
        "| Status | Count |",
        "|--------|------:|",
    ]
    for key in ("FRESH_ODDS", "STALE_ODDS", "ODDS_FRESHNESS_UNKNOWN", "REQUIRES_FRESH_ODDS"):
        lines.append(f"| {key} | {c.get(key, 0)} |")

    stale_n = c.get("STALE_ODDS", 0)
    unknown_n = c.get("ODDS_FRESHNESS_UNKNOWN", 0) + c.get("REQUIRES_FRESH_ODDS", 0)
    lines.extend(
        [
            "",
            "## Questions",
            "",
            f"1. **How many evaluated matches used stale odds?** **{stale_n}** / {payload.get('fixture_count', 0)}",
            f"2. **How many used unknown/missing odds metadata?** **{unknown_n}**",
            f"3. **Top5 hit rate on stale odds:** {payload.get('stale_top5_hit_rate_pct', 'N/A')}% "
            f"({payload.get('stale_top5_hits', 0)} hits / {stale_n} stale)",
            f"4. **Top5 on fresh odds:** {payload.get('fresh_top5_hits', 0)} hits / "
            f"{c.get('FRESH_ODDS', 0)} fresh (insufficient segment if n=0)",
            "",
            "## Recommendation",
            "",
        ]
    )
    if stale_n == payload.get("fixture_count") and payload.get("fixture_count", 0) > 0:
        lines.append(
            "**ODDS-FRESHNESS-1 should run before any model promotion.** "
            "All evaluated fixtures currently use stale odds; WDE alignment metrics are unreliable."
        )
    elif stale_n > 0:
        lines.append(
            "Mixed freshness — segment stale vs fresh before trusting S5 promotion metrics. "
            "Consider **ODDS-FRESHNESS-1** before promotion."
        )
    else:
        lines.append("Freshness acceptable for current sample; continue collecting evaluations.")
    lines.append("")
    return "\n".join(lines)
