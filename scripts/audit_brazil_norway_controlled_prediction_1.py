#!/usr/bin/env python3
"""BRAZIL-NORWAY-CONTROLLED-PREDICTION-1 Part B/C — Baseline and discovery."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import classify_odds_freshness, is_knockout_match, is_low_priority_match

PHASE = "BRAZIL-NORWAY-CONTROLLED-PREDICTION-1"
OUTPUT_MD = ROOT / "BRAZIL_NORWAY_CONTROLLED_PREDICTION_1_BASELINE.md"
OUTPUT_JSON = ROOT / "artifacts" / "brazil_norway_controlled_prediction_1" / "baseline.json"
TARGET_HOME = "Brazil"
TARGET_AWAY = "Norway"


def _counts(conn: sqlite3.Connection) -> dict:
    return {
        "wde_stored": conn.execute("SELECT COUNT(*) FROM worldcup_stored_predictions").fetchone()[0],
        "wde_evaluated": conn.execute("SELECT COUNT(*) FROM worldcup_prediction_evaluations").fetchone()[0],
        "wde_pending": conn.execute(
            """
            SELECT COUNT(*) FROM worldcup_stored_predictions s
            LEFT JOIN worldcup_prediction_evaluations e ON e.fixture_id=s.fixture_id
            WHERE e.fixture_id IS NULL
            """
        ).fetchone()[0],
        "ecse_snapshots": conn.execute("SELECT COUNT(*) FROM ecse_prediction_snapshots").fetchone()[0],
        "ecse_evaluated": conn.execute("SELECT COUNT(*) FROM ecse_prediction_evaluations").fetchone()[0],
        "ecse_pending": conn.execute(
            """
            SELECT COUNT(*) FROM ecse_prediction_snapshots s
            LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id=s.id
            WHERE e.id IS NULL
            """
        ).fetchone()[0],
    }


def main() -> int:
    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    tz = ZoneInfo("Europe/Vienna")

    snapshots = []
    for row in conn.execute(
        """
        SELECT s.id, s.fixture_id, s.generated_at, s.top_1_score, s.is_frozen,
               f.home_team, f.away_team, f.kickoff_utc, f.status, f.round_name,
               e.id AS eval_id
        FROM ecse_prediction_snapshots s
        JOIN fixtures f ON f.fixture_id = s.fixture_id
        LEFT JOIN ecse_prediction_evaluations e ON e.snapshot_id = s.id
        ORDER BY s.id ASC
        """
    ):
        r = dict(row)
        wde = conn.execute(
            "SELECT predicted_at FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
            (r["fixture_id"],),
        ).fetchone()
        odds = _latest_odds(conn, int(r["fixture_id"]))
        cls = classify_odds_freshness(
            odds_snapshot_at=odds["snapshot_at"] if odds else None,
            knockout=is_knockout_match(round_name=r.get("round_name"), status=r.get("status")),
            low_priority=is_low_priority_match(kickoff_utc=r.get("kickoff_utc")),
            odds_source=odds.get("source") if odds else None,
            has_odds=bool(odds),
        )
        snapshots.append(
            {
                "snapshot_id": r["id"],
                "fixture_id": r["fixture_id"],
                "match": f"{r['home_team']} vs {r['away_team']}",
                "kickoff_utc": r["kickoff_utc"],
                "status": r["status"],
                "evaluated": r["eval_id"] is not None,
                "generated_at": r["generated_at"],
                "is_frozen": r["is_frozen"],
                "wde_predicted_at": wde["predicted_at"] if wde else None,
                "odds_freshness": cls.status.value,
                "odds_age_hours": cls.odds_age_hours,
            }
        )

    brazil = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, kickoff_utc, status, round_name, competition_key
        FROM fixtures
        WHERE is_placeholder = 0 AND competition_key = 'world_cup_2026'
          AND home_team = ? AND away_team = ?
          AND UPPER(status) IN ('NS','TBD','TIMED','SCHEDULED','NOT_STARTED','NOT STARTED')
        ORDER BY kickoff_utc ASC LIMIT 1
        """,
        (TARGET_HOME, TARGET_AWAY),
    ).fetchone()

    brazil_info = None
    if brazil:
        b = dict(brazil)
        fid = int(b["fixture_id"])
        has_wde = bool(
            conn.execute(
                "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1", (fid,)
            ).fetchone()
        )
        has_ecse = bool(
            conn.execute(
                "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=? LIMIT 1", (fid,)
            ).fetchone()
        )
        odds = _latest_odds(conn, fid)
        cls = classify_odds_freshness(
            odds_snapshot_at=odds["snapshot_at"] if odds else None,
            knockout=is_knockout_match(round_name=b.get("round_name"), status=b.get("status")),
            low_priority=is_low_priority_match(kickoff_utc=b.get("kickoff_utc")),
            odds_source=odds.get("source") if odds else None,
            has_odds=bool(odds),
        )
        kickoff_vienna = "—"
        if b.get("kickoff_utc"):
            dt = datetime.fromisoformat(str(b["kickoff_utc"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            kickoff_vienna = dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")
        brazil_info = {
            "fixture_id": fid,
            "home_team": b["home_team"],
            "away_team": b["away_team"],
            "kickoff_utc": b["kickoff_utc"],
            "kickoff_vienna": kickoff_vienna,
            "competition": b["competition_key"],
            "round": b["round_name"],
            "status": b["status"],
            "wde_exists": has_wde,
            "ecse_exists": has_ecse,
            "latest_odds_snapshot_at": odds["snapshot_at"] if odds else None,
            "odds_source": odds.get("source") if odds else None,
            "odds_freshness_status": cls.status.value,
            "odds_age_hours": cls.odds_age_hours,
        }

    payload = {
        "phase": PHASE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_counts": _counts(conn),
        "ecse_snapshots": snapshots,
        "brazil_norway": brazil_info,
        "recommendation": (
            "BRAZIL_NORWAY_PREDICTION_ALREADY_EXISTS"
            if brazil_info and brazil_info["wde_exists"]
            else "BRAZIL_NORWAY_FIXTURE_NOT_FOUND"
            if not brazil_info
            else "READY_FOR_ODDS_AND_PREDICTION"
        ),
    }
    conn.close()

    lines = [
        "# BRAZIL-NORWAY-CONTROLLED-PREDICTION-1 — Baseline",
        "",
        f"**Generated:** {payload['generated_at_utc']}",
        "",
        "## Production counters",
        "",
        f"- WDE stored: **{payload['production_counts']['wde_stored']}**",
        f"- WDE evaluated: **{payload['production_counts']['wde_evaluated']}**",
        f"- ECSE snapshots: **{payload['production_counts']['ecse_snapshots']}**",
        f"- ECSE evaluated: **{payload['production_counts']['ecse_evaluated']}**",
        f"- ECSE pending: **{payload['production_counts']['ecse_pending']}**",
        "",
        "## ECSE snapshots (DB truth)",
        "",
        "| snapshot_id | fixture_id | match | kickoff UTC | status | eval | generated_at | freshness |",
        "|------------:|-----------:|-------|-------------|--------|------|--------------|-----------|",
    ]
    for s in snapshots:
        lines.append(
            f"| {s['snapshot_id']} | {s['fixture_id']} | {s['match']} | {s['kickoff_utc']} | "
            f"{s['status']} | {'yes' if s['evaluated'] else 'pending'} | {s['generated_at']} | {s['odds_freshness']} |"
        )
    lines.extend(["", "## Brazil vs Norway discovery", ""])
    if brazil_info:
        for k, v in brazil_info.items():
            lines.append(f"- **{k}:** {v}")
    else:
        lines.append("_Fixture not found._")
    lines.append(f"\n**Recommendation:** `{payload['recommendation']}`\n")

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
