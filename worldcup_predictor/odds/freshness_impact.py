"""Impact analysis — metrics by odds freshness segment (read-only)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from worldcup_predictor.odds.freshness_policy import FreshnessStatus, classify_odds_freshness, is_knockout_match
from worldcup_predictor.research.ecse_rerank.features import extract_wde_markets, is_btts, is_clean_sheet, parse_top10, winner_side
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_exists


def _norm_btts(val: str | None) -> str | None:
    if not val:
        return None
    v = str(val).lower().replace("btts_", "")
    return v if v in ("yes", "no") else None


def _norm_ou(val: str | None) -> str | None:
    if not val:
        return None
    v = str(val).lower()
    if "over" in v:
        return "over"
    if "under" in v:
        return "under"
    return v


def _segment_metrics() -> dict[str, Any]:
    return {
        "n": 0,
        "top1_hits": 0,
        "top3_hits": 0,
        "top5_hits": 0,
        "wde_1x2_hits": 0,
        "wde_ou_hits": 0,
        "wde_btts_hits": 0,
        "goal_error_sum": 0.0,
        "clean_sheet_top1": 0,
        "btts_consistent": 0,
        "ou_consistent": 0,
    }


def run_freshness_impact_analysis(db_path: str | None = None) -> dict[str, Any]:
    conn = connect_readonly(db_path)
    if not table_exists(conn, "ecse_prediction_snapshots"):
        conn.close()
        return {"phase": "ODDS-FRESHNESS-1", "segments": {}, "fixture_count": 0}

    has_wde = table_exists(conn, "worldcup_stored_predictions")
    has_odds = table_exists(conn, "odds_snapshots")

    query = """
        SELECT ec.fixture_id, ec.generated_at, ec.top_1_score, ec.top_10_scorelines_json,
               f.home_team, f.away_team, f.round_name, f.status,
               fr.home_goals, fr.away_goals
    """
    if has_wde:
        query += ", sp.payload_json"
    else:
        query += ", NULL AS payload_json"
    query += """
        FROM ecse_prediction_snapshots ec
        JOIN fixtures f ON f.fixture_id = ec.fixture_id
        JOIN fixture_results fr ON fr.fixture_id = ec.fixture_id
    """
    if has_wde:
        query += " LEFT JOIN worldcup_stored_predictions sp ON sp.fixture_id = ec.fixture_id"
    query += """
        WHERE fr.home_goals IS NOT NULL
          AND UPPER(f.status) IN ('FT', 'AET', 'PEN')
    """

    segments: dict[str, dict[str, Any]] = {
        FreshnessStatus.FRESH_ODDS.value: _segment_metrics(),
        FreshnessStatus.STALE_ODDS.value: _segment_metrics(),
        FreshnessStatus.ODDS_FRESHNESS_UNKNOWN.value: _segment_metrics(),
        FreshnessStatus.ODDS_MISSING.value: _segment_metrics(),
    }

    rows = conn.execute(query).fetchall()
    for row in rows:
        r = dict(row)
        fid = int(r["fixture_id"])
        actual = f"{int(r['home_goals'])}-{int(r['away_goals'])}"
        top10 = parse_top10(r.get("top_10_scorelines_json"))
        sorted10 = sorted(top10, key=lambda x: x.get("rank", 99))
        top1 = sorted10[0]["scoreline"] if sorted10 else r.get("top_1_score")
        top3 = [x["scoreline"] for x in sorted10[:3]]
        top5 = [x["scoreline"] for x in sorted10[:5]]

        odds_snap_at = odds_source = None
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

        knockout = is_knockout_match(round_name=r.get("round_name"), status=r.get("status"))
        cls = classify_odds_freshness(
            odds_snapshot_at=odds_snap_at,
            reference_at=r.get("generated_at"),
            knockout=knockout,
            odds_source=odds_source,
            has_odds=bool(odds_snap_at),
        )
        seg_key = cls.status.value
        if seg_key not in segments:
            seg_key = FreshnessStatus.ODDS_FRESHNESS_UNKNOWN.value
        seg = segments[seg_key]
        seg["n"] += 1
        if actual == top1:
            seg["top1_hits"] += 1
        if actual in top3:
            seg["top3_hits"] += 1
        if actual in top5:
            seg["top5_hits"] += 1
        if top1 and is_clean_sheet(top1):
            seg["clean_sheet_top1"] += 1

        wde = extract_wde_markets(json.loads(r["payload_json"]) if r.get("payload_json") else None)
        pick = winner_side(actual)
        if wde.get("pick_1x2") and pick:
            if wde["pick_1x2"] == pick:
                seg["wde_1x2_hits"] += 1
        tg = int(r["home_goals"]) + int(r["away_goals"])
        ou_pick = _norm_ou(wde.get("pick_ou25"))
        if ou_pick == "over" and tg > 2:
            seg["wde_ou_hits"] += 1
            seg["ou_consistent"] += 1
        elif ou_pick == "under" and tg <= 2:
            seg["wde_ou_hits"] += 1
            seg["ou_consistent"] += 1
        btts_pick = _norm_btts(wde.get("pick_btts"))
        actual_btts = is_btts(actual)
        if btts_pick == "yes" and actual_btts:
            seg["wde_btts_hits"] += 1
            seg["btts_consistent"] += 1
        elif btts_pick == "no" and not actual_btts:
            seg["wde_btts_hits"] += 1
            seg["btts_consistent"] += 1

        if top1:
            p = top1.split("-")
            if len(p) == 2:
                seg["goal_error_sum"] += abs(int(p[0]) + int(p[1]) - tg)

    conn.close()

    summary: dict[str, Any] = {}
    for key, seg in segments.items():
        n = seg["n"]
        if n == 0:
            summary[key] = {"n": 0}
            continue
        summary[key] = {
            "n": n,
            "top1_pct": round(100 * seg["top1_hits"] / n, 1),
            "top3_pct": round(100 * seg["top3_hits"] / n, 1),
            "top5_pct": round(100 * seg["top5_hits"] / n, 1),
            "wde_1x2_pct": round(100 * seg["wde_1x2_hits"] / n, 1) if seg["wde_1x2_hits"] else None,
            "wde_ou_pct": round(100 * seg["wde_ou_hits"] / n, 1) if seg["wde_ou_hits"] else None,
            "wde_btts_pct": round(100 * seg["wde_btts_hits"] / n, 1) if seg["wde_btts_hits"] else None,
            "avg_goal_error": round(seg["goal_error_sum"] / n, 2),
            "clean_sheet_top1_pct": round(100 * seg["clean_sheet_top1"] / n, 1),
            "btts_consistency_pct": round(100 * seg["btts_consistent"] / n, 1),
            "ou_consistency_pct": round(100 * seg["ou_consistent"] / n, 1),
        }

    return {
        "phase": "ODDS-FRESHNESS-1",
        "fixture_count": len(rows),
        "segments": summary,
        "raw_segments": segments,
    }


def render_impact_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# ODDS-FRESHNESS-1 — Impact Analysis",
        "",
        f"Evaluated ECSE fixtures: **{payload.get('fixture_count', 0)}**",
        "",
        "## Metrics by Freshness Segment",
        "",
        "| Segment | n | Top1 | Top3 | Top5 | CS Top1 | BTTS consist | O/U consist | Avg goal err |",
        "|---------|--:|-----:|-----:|-----:|--------:|-------------:|------------:|-------------:|",
    ]
    for key, seg in (payload.get("segments") or {}).items():
        if not seg.get("n"):
            lines.append(f"| {key} | 0 | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {key} | {seg['n']} | {seg.get('top1_pct')}% | {seg.get('top3_pct')}% | {seg.get('top5_pct')}% | "
            f"{seg.get('clean_sheet_top1_pct')}% | {seg.get('btts_consistency_pct')}% | "
            f"{seg.get('ou_consistency_pct')}% | {seg.get('avg_goal_error')} |"
        )

    stale = (payload.get("segments") or {}).get(FreshnessStatus.STALE_ODDS.value, {})
    fresh = (payload.get("segments") or {}).get(FreshnessStatus.FRESH_ODDS.value, {})

    lines.extend(["", "## Key Questions", ""])
    if stale.get("n") and fresh.get("n"):
        lines.append(
            f"1. **Stale vs fresh Top3:** stale {stale.get('top3_pct')}% vs fresh {fresh.get('top3_pct')}% "
            f"(n={stale.get('n')} vs {fresh.get('n')})"
        )
    elif stale.get("n"):
        lines.append(
            f"1. **All evaluated fixtures stale (n={stale.get('n')})** — Top3 {stale.get('top3_pct')}%, "
            f"Top5 {stale.get('top5_pct')}%. Cannot compare fresh segment."
        )
    else:
        lines.append("1. **Insufficient evaluated sample for stale vs fresh comparison.**")

    if stale.get("n"):
        lines.append(
            f"2. **Clean-sheet Top1 on stale odds:** {stale.get('clean_sheet_top1_pct')}% "
            f"— elevated clean-sheet bias possible when odds age > threshold."
        )
    lines.append(
        f"3. **O/U & BTTS on stale:** O/U consistency {stale.get('ou_consistency_pct', 'N/A')}%, "
        f"BTTS {stale.get('btts_consistency_pct', 'N/A')}% (stale segment)."
    )
    lines.extend(
        [
            "",
            "4. **Knockout recommendation:** Require fresh odds (≤6h) before knockout End Result predictions "
            "when `requires_fresh_odds=true`. Do not block automatically unless `--strict-fresh-odds` enabled.",
            "",
        ]
    )
    return "\n".join(lines)
