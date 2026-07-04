#!/usr/bin/env python3
"""CONTROLLED-KNOCKOUT-PREDICTIONS-2 Part A — Discover target fixtures from production DB."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_audit import _latest_odds
from worldcup_predictor.odds.freshness_policy import classify_odds_freshness, is_knockout_match, is_low_priority_match
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_exists

PHASE = "CONTROLLED-KNOCKOUT-PREDICTIONS-2"
TARGETS = [
    ("Canada", "Morocco"),
    ("Paraguay", "France"),
    ("Brazil", "Norway"),
]
OUTPUT_MD = ROOT / "CONTROLLED_KNOCKOUT_PREDICTIONS_2_DISCOVERY.md"
OUTPUT_JSON = ROOT / "artifacts" / "controlled_knockout_predictions_2" / "discovery.json"


def _match_key(home: str | None, away: str | None) -> tuple[str, str]:
    return (str(home or "").strip(), str(away or "").strip())


def discover_targets(*, db_path: str, tz_name: str) -> dict:
    conn = connect_readonly(db_path)
    tz = ZoneInfo(tz_name)
    found: list[dict] = []
    missing: list[tuple[str, str]] = []

    for home, away in TARGETS:
        row = conn.execute(
            """
            SELECT fixture_id, home_team, away_team, kickoff_utc, status, round_name, competition_key
            FROM fixtures
            WHERE is_placeholder = 0
              AND competition_key = 'world_cup_2026'
              AND home_team = ? AND away_team = ?
              AND UPPER(status) IN ('NS','TBD','TIMED','SCHEDULED','NOT_STARTED','NOT STARTED')
            ORDER BY kickoff_utc ASC
            LIMIT 1
            """,
            (home, away),
        ).fetchone()
        if not row:
            missing.append((home, away))
            continue

        r = dict(row)
        fid = int(r["fixture_id"])
        has_wde = False
        if table_exists(conn, "worldcup_stored_predictions"):
            has_wde = bool(
                conn.execute(
                    "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
                    (fid,),
                ).fetchone()
            )
        has_ecse = False
        if table_exists(conn, "ecse_prediction_snapshots"):
            has_ecse = bool(
                conn.execute(
                    "SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=? LIMIT 1",
                    (fid,),
                ).fetchone()
            )

        odds = _latest_odds(conn, fid)
        knockout = is_knockout_match(round_name=r.get("round_name"), status=r.get("status"))
        low_pri = is_low_priority_match(kickoff_utc=r.get("kickoff_utc"))
        cls = classify_odds_freshness(
            odds_snapshot_at=odds["snapshot_at"] if odds else None,
            knockout=knockout,
            low_priority=low_pri,
            odds_source=odds.get("source") if odds else None,
            has_odds=bool(odds),
        )

        kickoff_vienna = "—"
        if r.get("kickoff_utc"):
            try:
                dt = datetime.fromisoformat(str(r["kickoff_utc"]).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                kickoff_vienna = dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")
            except ValueError:
                kickoff_vienna = str(r["kickoff_utc"])

        found.append(
            {
                "fixture_id": fid,
                "match": f"{r['home_team']} vs {r['away_team']}",
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "kickoff_utc": r.get("kickoff_utc"),
                "kickoff_vienna": kickoff_vienna,
                "round": r.get("round_name") or "—",
                "status": r.get("status"),
                "wde_stored": has_wde,
                "ecse_snapshot": has_ecse,
                "latest_odds_snapshot_at": odds["snapshot_at"] if odds else None,
                "odds_source": odds.get("source") if odds else None,
                "odds_freshness_status": cls.status.value,
                "odds_age_hours": cls.odds_age_hours,
                "requires_fresh_odds": cls.requires_fresh_odds,
            }
        )

    colombia = conn.execute(
        """
        SELECT fixture_id, home_team, away_team, status
        FROM fixtures WHERE fixture_id = 1567310 LIMIT 1
        """
    ).fetchone()
    conn.close()

    return {
        "phase": PHASE,
        "discovered_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "targets": found,
        "missing_targets": [{"home": h, "away": a} for h, a in missing],
        "colombia_fixture": dict(colombia) if colombia else None,
        "recommendation": "ALL_TARGETS_FOUND" if not missing else "MISSING_TARGETS",
    }


def render_md(payload: dict) -> str:
    lines = [
        "# CONTROLLED-KNOCKOUT-PREDICTIONS-2 — Discovery",
        "",
        f"**Generated:** {payload['discovered_at_utc']}",
        "",
        "## Target fixtures (production DB)",
        "",
        "| Match | fixture_id | kickoff UTC | kickoff Vienna | round | status | WDE | ECSE | odds_at | freshness | age_h |",
        "|-------|-----------:|-------------|---------------|-------|--------|-----|------|---------|-----------|------:|",
    ]
    for t in payload["targets"]:
        lines.append(
            f"| {t['match']} | {t['fixture_id']} | {t['kickoff_utc']} | {t['kickoff_vienna']} | "
            f"{t['round']} | {t['status']} | {'yes' if t['wde_stored'] else 'no'} | "
            f"{'yes' if t['ecse_snapshot'] else 'no'} | {t['latest_odds_snapshot_at'] or '—'} | "
            f"{t['odds_freshness_status']} | {t['odds_age_hours'] if t['odds_age_hours'] is not None else '—'} |"
        )
    if payload["missing_targets"]:
        lines.extend(["", "## Missing targets", ""])
        for m in payload["missing_targets"]:
            lines.append(f"- {m['home']} vs {m['away']}")
    lines.extend(["", "## Colombia reference (do not mutate)", ""])
    c = payload.get("colombia_fixture")
    if c:
        lines.append(f"- fixture_id **1567310** — {c['home_team']} vs {c['away_team']} — status {c['status']}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--db-path", default=None)
    args = parser.parse_args()
    settings = get_settings()
    payload = discover_targets(db_path=args.db_path or settings.sqlite_path, tz_name=args.timezone)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(render_md(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["recommendation"] == "ALL_TARGETS_FOUND" else 1


if __name__ == "__main__":
    raise SystemExit(main())
