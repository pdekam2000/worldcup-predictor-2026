"""Forward-only Correct Score odds collection plan (stops at kickoff)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from worldcup_predictor.research.correct_score_odds.ddl import ensure_correct_score_odds_schema

WINDOWS = (
    ("first_available", None),  # as soon as quoted
    ("h24", timedelta(hours=24)),
    ("h6", timedelta(hours=6)),
    ("h1", timedelta(hours=1)),
    ("final_prematch", timedelta(minutes=15)),
)


def _parse_kickoff(s: str) -> datetime | None:
    try:
        raw = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw[:25] if "T" in raw else raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def build_forward_plan(
    conn,
    fixtures: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Plan collection windows for upcoming fixtures.
    Never schedules after kickoff.
    """
    ensure_correct_score_odds_schema(conn)
    now = datetime.now(timezone.utc)
    planned = 0
    skipped_past = 0
    for fx in fixtures:
        fid = int(fx["fixture_id"])
        ko = _parse_kickoff(str(fx.get("kickoff_utc") or ""))
        if not ko or ko <= now:
            skipped_past += 1
            continue
        for label, delta in WINDOWS:
            if delta is None:
                target = now
            else:
                target = ko - delta
            if target >= ko:
                continue
            if target < now and label != "first_available":
                # window already passed — mark missed, do not collect post-hoc as prematch
                status = "missed_window"
                target_s = target.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                status = "planned"
                target_s = max(target, now).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                """
                INSERT OR REPLACE INTO correct_score_forward_collection_plan (
                    fixture_id, kickoff_utc, window_label, target_collect_utc, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    fid,
                    ko.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    label,
                    target_s,
                    status,
                ),
            )
            planned += 1
    conn.commit()
    return {
        "planned_rows": planned,
        "skipped_past_kickoff": skipped_past,
        "windows": [w[0] for w in WINDOWS],
        "rule": "never_collect_after_kickoff",
        "historical_roi_claim": False,
        "target_portfolios_min": 100,
        "target_portfolios_preferred": 500,
        "note": (
            "Forward shadow collection enables later ROI with executable prematch odds; "
            "do not claim historical ROI from forward-only data."
        ),
    }


def due_collections(conn, *, now: datetime | None = None, limit: int = 20) -> list[dict[str, Any]]:
    ensure_correct_score_odds_schema(conn)
    now = now or datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        """
        SELECT fixture_id, kickoff_utc, window_label, target_collect_utc, status
        FROM correct_score_forward_collection_plan
        WHERE status = 'planned'
          AND target_collect_utc <= ?
          AND kickoff_utc > ?
        ORDER BY target_collect_utc ASC
        LIMIT ?
        """,
        (now_s, now_s, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_collected(conn, fixture_id: int, window_label: str, run_id: str) -> None:
    conn.execute(
        """
        UPDATE correct_score_forward_collection_plan
        SET status='collected', collected_at_utc=?, ingestion_run_id=?
        WHERE fixture_id=? AND window_label=?
        """,
        (
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            run_id,
            int(fixture_id),
            window_label,
        ),
    )
    conn.commit()


def plan_to_dict(conn) -> dict[str, Any]:
    ensure_correct_score_odds_schema(conn)
    rows = [dict(r) for r in conn.execute("SELECT * FROM correct_score_forward_collection_plan").fetchall()]
    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {
        "n_rows": len(rows),
        "by_status": by_status,
        "sample": rows[:50],
        "stops_at_kickoff": True,
        "json": json.dumps({"by_status": by_status, "n": len(rows)}),
    }
