"""Capture real O/U 2.5 / 3.5 / 4.5 lines into shadow totals table — never invent."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_lambda_extraction import devig_two_way, implied_raw
from worldcup_predictor.research.football_strength_foundation.constants import TOTALS_SNAPSHOT_TABLE
from worldcup_predictor.research.football_strength_foundation.totals_market import (
    TotalsLine,
    ensure_totals_schema,
    persist_totals_lines,
)

REQUIRED_LINES = (2.5, 3.5, 4.5)

MISSING_DDL = f"""
CREATE TABLE IF NOT EXISTS alternate_totals_capture_status (
    status_id TEXT PRIMARY KEY,
    fixture_id INTEGER NOT NULL,
    line REAL NOT NULL,
    status TEXT NOT NULL,
    reason TEXT,
    provider TEXT,
    odds_timestamp TEXT,
    freshness TEXT,
    source_hash TEXT,
    created_at_utc TEXT NOT NULL,
    UNIQUE(fixture_id, line, source_hash)
)
"""


def ensure_capture_schema(conn: sqlite3.Connection) -> None:
    ensure_totals_schema(conn)
    conn.execute(MISSING_DDL)
    from worldcup_predictor.research.football_strength_foundation.schema_upgrade import (
        upgrade_shadow_tables,
    )

    upgrade_shadow_tables(conn)
    conn.commit()


def lines_from_ecse_odds_row(odds_row: dict[str, Any] | None) -> list[TotalsLine]:
    """Extract available totals from an ECSE-shaped odds row. Missing lines omitted."""
    if not odds_row:
        return []
    mapping = {
        2.5: ("ou_over_25_closing", "ou_under_25_closing"),
        3.5: ("ou_over_35_closing", "ou_under_35_closing"),
        4.5: ("ou_over_45_closing", "ou_under_45_closing"),
    }
    out: list[TotalsLine] = []
    provider = str(odds_row.get("_provider") or odds_row.get("provider") or "ecse_odds_row")
    freshness = str(odds_row.get("_freshness") or odds_row.get("odds_freshness") or "")
    ts = odds_row.get("_odds_timestamp") or odds_row.get("odds_timestamp")
    books = odds_row.get("_odds_line_count") or odds_row.get("bookmaker_count")
    for line, (ok, uk) in mapping.items():
        over = odds_row.get(ok)
        under = odds_row.get(uk)
        if over is None and under is None:
            continue
        try:
            over_f = float(over) if over is not None else None
            under_f = float(under) if under is not None else None
        except (TypeError, ValueError):
            continue
        out.append(
            TotalsLine(
                line=line,
                over_odds=over_f,
                under_odds=under_f,
                provider=provider,
                bookmaker_count=int(books) if books not in (None, "") else None,
                timestamp=str(ts) if ts else None,
                freshness=freshness or None,
            )
        )
    return out


def capture_alternate_totals(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    odds_row: dict[str, Any] | None,
    max_age_minutes: float | None = 180.0,
) -> dict[str, Any]:
    """
    Persist available lines and explicit MISSING status for absent required lines.
    Never synthesizes / interpolates.
    """
    ensure_capture_schema(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    present = lines_from_ecse_odds_row(odds_row)
    present_lines = {ln.line for ln in present}

    # Freshness gate: if age known and stale, mark STALE_SKIP instead of storing as usable
    age = None
    if odds_row and odds_row.get("_odds_age_minutes") is not None:
        try:
            age = float(odds_row["_odds_age_minutes"])
        except (TypeError, ValueError):
            age = None
    stale = age is not None and max_age_minutes is not None and age > max_age_minutes

    stored = 0
    missing = 0
    if present and not stale:
        stored = persist_totals_lines(conn, fixture_id=fixture_id, lines=present)

    for line in REQUIRED_LINES:
        if line in present_lines and not stale:
            status = "PRESENT"
            reason = None
        elif line in present_lines and stale:
            status = "STALE_SKIP"
            reason = f"odds_age_minutes={age} > max={max_age_minutes}"
            missing += 1
        else:
            status = "MISSING"
            reason = "provider_or_snapshot_did_not_return_line"
            missing += 1
        payload = {"fixture_id": fixture_id, "line": line, "status": status, "reason": reason}
        h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        sid = f"ats-{fixture_id}-{line}-{h[:10]}"
        conn.execute(
            """
            INSERT OR IGNORE INTO alternate_totals_capture_status (
                status_id, fixture_id, line, status, reason, provider, odds_timestamp,
                freshness, source_hash, created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                sid,
                int(fixture_id),
                float(line),
                status,
                reason,
                (odds_row or {}).get("_provider"),
                (odds_row or {}).get("_odds_timestamp"),
                (odds_row or {}).get("_freshness"),
                h,
                now,
            ),
        )
    conn.commit()
    return {
        "fixture_id": fixture_id,
        "lines_present": sorted(present_lines),
        "stored": stored,
        "missing_or_stale": missing,
        "stale": stale,
        "canonical_lambda_changed": False,
    }


def provider_audit_markdown() -> str:
    return """# Alternate totals provider audit

## API-Football
- Endpoint: odds by fixture (bookmakers → bets)
- Lines: O/U 2.5 commonly; 3.5 often; 4.5 intermittent by league/book
- Mapping: `api_football_odds_to_ecse_row` now captures 2.5/3.5/**4.5**
- Timestamps: fetch time; freshness via odds age gates
- Rate limit: quota-sensitive — capture only on existing prematch fetch

## OddAlerts / CSV history
- Markets include over_under over_25/35/45 in historical clean table
- Live OddAlerts history mapper now includes 4.5 when market string contains 4.5
- Historical CSV ends ~2026-06-28 — forward July freezes had 0 joins

## Sportmonks
- Enrichment path exists; totals coverage league-dependent
- Do not invent lines when absent

## Staging external odds
- Has ft_goals_over_2_5 / under_2_5 / under_3_5 / over_1_5
- **Missing** over_3_5 and any 4.5 — provider/export gap

## Root cause of missing O/U 3.5/4.5 on eval freezes
1. Freeze schema does not persist alternate totals columns
2. `build_odds_feature_row` previously omitted 4.5 (now fixed additively)
3. `extract_lambdas` still ignores 4.5 (canonical unchanged)
4. Eval kickoffs lack staging/CSV multi-line rows

## Future expected coverage
After this capture path: whenever providers return 3.5/4.5 on live prematch fetches,
shadow table `totals_market_shadow_snapshots` + `alternate_totals_capture_status` record
PRESENT or explicit MISSING — never synthesized.
"""
