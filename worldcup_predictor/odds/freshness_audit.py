"""Read-only odds freshness system audit."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.odds.freshness_policy import (
    PHASE,
    FreshnessStatus,
    classify_odds_freshness,
    is_knockout_match,
    is_low_priority_match,
    parse_timestamp,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_exists

FINISHED = ("FT", "AET", "PEN")
UPCOMING = ("NS", "TBD", "TIMED", "SCHEDULED")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def _latest_odds(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    if not table_exists(conn, "odds_snapshots"):
        return None
    row = conn.execute(
        "SELECT snapshot_at, payload_json, competition_key FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
        (fixture_id,),
    ).fetchone()
    if not row:
        return None
    source = None
    try:
        payload = json.loads(row["payload_json"])
        source = payload.get("source_provider") or payload.get("source")
    except (json.JSONDecodeError, TypeError):
        source = "odds_snapshots"
    return {
        "snapshot_at": row["snapshot_at"],
        "source": source,
        "competition_key": row["competition_key"],
    }


def run_odds_freshness_audit(db_path: str | None = None) -> dict[str, Any]:
    conn = connect_readonly(db_path)
    now = datetime.now(timezone.utc)

    odds_rows = _scalar(conn, "SELECT COUNT(*) FROM odds_snapshots") if table_exists(conn, "odds_snapshots") else 0
    odds_fixtures = (
        _scalar(conn, "SELECT COUNT(DISTINCT fixture_id) FROM odds_snapshots")
        if table_exists(conn, "odds_snapshots")
        else 0
    )

    newest = oldest = None
    source_counts: dict[str, int] = {}
    if table_exists(conn, "odds_snapshots"):
        newest = conn.execute("SELECT MAX(snapshot_at) FROM odds_snapshots").fetchone()[0]
        oldest = conn.execute("SELECT MIN(snapshot_at) FROM odds_snapshots").fetchone()[0]
        for row in conn.execute("SELECT payload_json FROM odds_snapshots"):
            try:
                p = json.loads(row[0])
                src = str(p.get("source_provider") or p.get("source") or "unknown")
            except (json.JSONDecodeError, TypeError):
                src = "unknown"
            source_counts[src] = source_counts.get(src, 0) + 1

    wc_fixtures = conn.execute(
        """SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.status, f.round_name,
                  f.competition_key, ec.generated_at AS ecse_at, sp.predicted_at AS wde_at
           FROM fixtures f
           LEFT JOIN ecse_prediction_snapshots ec ON ec.fixture_id = f.fixture_id
           LEFT JOIN worldcup_stored_predictions sp ON sp.fixture_id = f.fixture_id
           WHERE f.competition_key = 'world_cup_2026' AND f.is_placeholder = 0"""
    ).fetchall() if table_exists(conn, "fixtures") else []

    seg_counts = {s.value: 0 for s in FreshnessStatus}
    missing_odds = stale_odds = fresh_odds = 0
    fixture_details: list[dict[str, Any]] = []

    for row in wc_fixtures:
        r = dict(row)
        fid = int(r["fixture_id"])
        status = str(r.get("status") or "NS").upper()
        if status in FINISHED:
            bucket = "finished"
        elif status in UPCOMING or status in {"NS", "TBD"}:
            bucket = "upcoming"
        else:
            bucket = "other"

        odds = _latest_odds(conn, fid)
        knockout = is_knockout_match(round_name=r.get("round_name"), status=r.get("status"))
        low_pri = is_low_priority_match(kickoff_utc=r.get("kickoff_utc"), reference=now)
        ref_at = r.get("ecse_at") or r.get("wde_at") or now.isoformat()

        cls = classify_odds_freshness(
            odds_snapshot_at=odds["snapshot_at"] if odds else None,
            reference_at=ref_at,
            knockout=knockout,
            low_priority=low_pri,
            odds_source=odds.get("source") if odds else None,
            has_odds=bool(odds),
        )
        seg_counts[cls.status.value] = seg_counts.get(cls.status.value, 0) + 1
        if cls.status == FreshnessStatus.ODDS_MISSING:
            missing_odds += 1
        elif cls.status == FreshnessStatus.STALE_ODDS:
            stale_odds += 1
        elif cls.status == FreshnessStatus.FRESH_ODDS:
            fresh_odds += 1

        if bucket in ("upcoming", "finished") and cls.status != FreshnessStatus.FRESH_ODDS:
            fixture_details.append(
                {
                    "fixture_id": fid,
                    "match": f"{r['home_team']} vs {r['away_team']}",
                    "bucket": bucket,
                    "freshness": cls.status.value,
                    "odds_age_hours": cls.odds_age_hours,
                    "knockout": knockout,
                }
            )

    ecse_snap = _scalar(conn, "SELECT COUNT(*) FROM ecse_prediction_snapshots") if table_exists(conn, "ecse_prediction_snapshots") else 0
    wde_stored = _scalar(conn, "SELECT COUNT(*) FROM worldcup_stored_predictions") if table_exists(conn, "worldcup_stored_predictions") else 0

    conn.close()

    return {
        "phase": PHASE,
        "audited_at": _utc_now(),
        "odds_tables": {
            "odds_snapshots_rows": odds_rows,
            "odds_snapshots_fixtures": odds_fixtures,
            "newest_snapshot_at": newest,
            "oldest_snapshot_at": oldest,
            "source_coverage": source_counts,
        },
        "wc_fixture_freshness": seg_counts,
        "matches_missing_odds": missing_odds,
        "matches_stale_odds": stale_odds,
        "matches_fresh_odds": fresh_odds,
        "ecse_snapshots": ecse_snap,
        "wde_stored_predictions": wde_stored,
        "ecse_wde_fields_affected": [
            "lambda_home/lambda_away (ECSE — odds-implied goals)",
            "top_10_scorelines_json ranking (ECSE)",
            "one_x_two / over_under / btts (WDE)",
            "End Result Top3/Top5 candidate ordering",
        ],
        "quota_risk": {
            "note": "Uncontrolled refresh avoided; use --max-provider-calls and cache-first import.",
            "recommended_max_per_run": 20,
        },
        "non_fresh_fixtures_sample": fixture_details[:30],
        "integration_points": {
            "odds_fetch": [
                "owner_daily/odds_import.py",
                "owner_daily/provider_fetch.py",
                "clients/api_football.py",
                "providers/oddalerts_provider.py",
                "providers/sportmonks_provider.py",
            ],
            "odds_storage": ["odds_snapshots table"],
            "ecse_feed": "build_ecse_live_prediction / lambda from odds_snapshots",
            "wde_feed": "PredictPipeline / odds_snapshots + api cache",
            "freshness_flag_existing": "research/ecse_rerank/features.odds_freshness_meta",
            "ui_display": "research/ecse_match_display._load_odds_freshness_for_fixture",
        },
    }


def render_audit_markdown(payload: dict[str, Any]) -> str:
    t = payload.get("odds_tables", {})
    lines = [
        "# ODDS-FRESHNESS-1 — System Audit",
        "",
        f"Audited: **{payload.get('audited_at')}**",
        "",
        "## Odds Tables",
        "",
        "| Table | Rows | Distinct fixtures | Newest | Oldest |",
        "|-------|-----:|------------------:|--------|--------|",
        f"| odds_snapshots | {t.get('odds_snapshots_rows', 0)} | {t.get('odds_snapshots_fixtures', 0)} | {t.get('newest_snapshot_at') or '—'} | {t.get('oldest_snapshot_at') or '—'} |",
        "",
        "## Source Coverage",
        "",
    ]
    for src, cnt in sorted((t.get("source_coverage") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"- **{src}**: {cnt} snapshots")
    lines.extend(
        [
            "",
            "## WC Fixture Freshness Segments",
            "",
            "| Status | Count |",
            "|--------|------:|",
        ]
    )
    for k, v in sorted((payload.get("wc_fixture_freshness") or {}).items()):
        lines.append(f"| {k} | {v} |")
    lines.extend(
        [
            "",
            f"- Missing odds: **{payload.get('matches_missing_odds', 0)}**",
            f"- Stale odds: **{payload.get('matches_stale_odds', 0)}**",
            f"- Fresh odds: **{payload.get('matches_fresh_odds', 0)}**",
            "",
            "## ECSE/WDE Impact Fields",
            "",
        ]
    )
    for f in payload.get("ecse_wde_fields_affected") or []:
        lines.append(f"- {f}")
    lines.extend(
        [
            "",
            f"- ECSE snapshots: **{payload.get('ecse_snapshots', 0)}**",
            f"- WDE stored predictions: **{payload.get('wde_stored_predictions', 0)}**",
            "",
            "## Quota Risk",
            "",
            f"{(payload.get('quota_risk') or {}).get('note')}",
            f"Recommended max provider calls per run: **{(payload.get('quota_risk') or {}).get('recommended_max_per_run', 20)}**",
            "",
            "## Integration Points",
            "",
        ]
    )
    ip = payload.get("integration_points") or {}
    lines.append(f"- Odds fetch: {', '.join(ip.get('odds_fetch') or [])}")
    lines.append(f"- Storage: {ip.get('odds_storage')}")
    lines.append(f"- ECSE feed: {ip.get('ecse_feed')}")
    lines.append(f"- WDE feed: {ip.get('wde_feed')}")
    lines.append("")
    return "\n".join(lines)
