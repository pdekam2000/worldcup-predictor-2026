"""Totals market persistence + multi-line inversion (shadow / research)."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_lambda_extraction import (
    devig_two_way,
    implied_raw,
    solve_lambda_total_from_over,
)
from worldcup_predictor.research.football_strength_foundation.constants import TOTALS_SNAPSHOT_TABLE

TOTALS_DDL = f"""
CREATE TABLE IF NOT EXISTS {TOTALS_SNAPSHOT_TABLE} (
    snapshot_id TEXT PRIMARY KEY,
    fixture_id INTEGER,
    registry_fixture_id INTEGER,
    line REAL NOT NULL,
    over_odds REAL,
    under_odds REAL,
    implied_over REAL,
    implied_under REAL,
    devig_over REAL,
    provider TEXT,
    bookmaker TEXT,
    bookmaker_count INTEGER,
    consensus TEXT,
    odds_timestamp TEXT,
    odds_age_minutes REAL,
    freshness TEXT,
    source_hash TEXT,
    created_at_utc TEXT NOT NULL
)
"""


@dataclass
class TotalsLine:
    line: float
    over_odds: float | None
    under_odds: float | None
    provider: str | None = None
    bookmaker_count: int | None = None
    timestamp: str | None = None
    freshness: str | None = None

    @property
    def implied_over(self) -> float | None:
        return implied_raw(self.over_odds)

    @property
    def implied_under(self) -> float | None:
        return implied_raw(self.under_odds)

    @property
    def devig_over(self) -> float | None:
        return devig_two_way(self.over_odds, self.under_odds)


def ensure_totals_schema(conn: sqlite3.Connection) -> None:
    conn.execute(TOTALS_DDL)
    from worldcup_predictor.research.football_strength_foundation.schema_upgrade import (
        upgrade_shadow_tables,
    )

    upgrade_shadow_tables(conn)
    conn.commit()


def persist_totals_lines(
    conn: sqlite3.Connection,
    *,
    fixture_id: int | None,
    lines: list[TotalsLine],
    registry_fixture_id: int | None = None,
) -> int:
    ensure_totals_schema(conn)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    n = 0
    for ln in lines:
        if ln.over_odds is None and ln.under_odds is None:
            continue
        payload = {
            "fixture_id": fixture_id,
            "line": ln.line,
            "over": ln.over_odds,
            "under": ln.under_odds,
            "provider": ln.provider,
        }
        h = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        sid = f"tot-{fixture_id or registry_fixture_id}-{ln.line}-{h[:10]}"
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {TOTALS_SNAPSHOT_TABLE} (
                snapshot_id, fixture_id, registry_fixture_id, line, over_odds, under_odds,
                implied_over, implied_under, devig_over, provider, bookmaker, bookmaker_count,
                consensus, odds_timestamp, odds_age_minutes, freshness, source_hash, created_at_utc
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                sid,
                fixture_id,
                registry_fixture_id,
                float(ln.line),
                ln.over_odds,
                ln.under_odds,
                ln.implied_over,
                ln.implied_under,
                ln.devig_over,
                ln.provider,
                None,
                ln.bookmaker_count,
                None,
                ln.timestamp,
                None,
                ln.freshness,
                h,
                now,
            ),
        )
        n += 1
    conn.commit()
    return n


def check_monotonic_overs(p25: float | None, p35: float | None, p45: float | None) -> dict[str, Any]:
    vals = [(2.5, p25), (3.5, p35), (4.5, p45)]
    present = [(L, p) for L, p in vals if p is not None]
    ok = True
    for i in range(len(present) - 1):
        if present[i][1] + 1e-9 < present[i + 1][1]:
            ok = False
    return {"consistent": ok, "lines": present}


def invert_multi_line(lines: list[TotalsLine]) -> dict[str, Any]:
    """Estimate total λ from available O/U lines; never invent missing lines."""
    estimates: list[tuple[float, float, float]] = []  # lam, weight, line
    probs: dict[float, float | None] = {2.5: None, 3.5: None, 4.5: None}
    weights = {2.5: 0.45, 3.5: 0.35, 4.5: 0.20}
    for ln in lines:
        p = ln.devig_over
        probs[ln.line] = p
        if p is None:
            continue
        lam = solve_lambda_total_from_over(p, ln.line)
        if lam is None:
            continue
        estimates.append((lam, weights.get(ln.line, 0.25), ln.line))
    mono = check_monotonic_overs(probs.get(2.5), probs.get(3.5), probs.get(4.5))
    if not estimates:
        return {
            "lambda_total": None,
            "method": "none",
            "lines_used": [],
            "monotonic": mono,
            "available_lines": [ln.line for ln in lines if ln.over_odds or ln.under_odds],
        }
    wsum = sum(w for _, w, _ in estimates)
    lam = sum(l * w for l, w, _ in estimates) / wsum
    only25 = [e for e in estimates if e[2] == 2.5]
    return {
        "lambda_total": lam,
        "lambda_total_25_only": only25[0][0] if only25 else None,
        "method": "multi_line_weighted" if len(estimates) > 1 else "single_line",
        "lines_used": [e[2] for e in estimates],
        "monotonic": mono,
        "n_lines": len(estimates),
        "probs": probs,
    }


def audit_totals_pipeline_markdown() -> str:
    return """# Totals market pipeline audit

## Canonical ECSE path
`extract_lambdas` uses O/U 1.5 / 2.5 / 3.5 closing odds. **O/U 4.5 is selected in training SQL
but unused in the extractor.**

## Freeze persistence
`frozen_predictions` stores H/D/A odds and `ou25_prediction` label; **does not persist**
O/U 3.5 / 4.5 decimal lines on freeze columns. Complete payloads often null.

## Historical availability

### `historical_csv_odds_prematch_clean` (to 2026-06-28)
| selection | approx n |
|-----------|----------|
| over_25 | ~114k |
| under_25 | ~82k |
| over_35 | ~9.6k (sparse) |
| under_35 | ~110k |
| over_45 | ~1.6k (very sparse) |
| under_45 | ~99k |

### `external_match_odds_staging`
Present: `ft_goals_over_2_5`, `ft_goals_under_2_5`, `ft_goals_under_3_5`, `ft_goals_over_1_5`.
**Absent:** `ft_goals_over_3_5`, any `*_4_5` markets.

### Eval cohort (2026-07 forward freezes)
No staging rows for several eval kickoff dates (e.g. 2026-07-12) → **0 multi-line joins**
on the 168-fixture set without inventing odds.

## Classification
- O/U 2.5: requested & used in λ when present in ECSE odds features
- O/U 3.5: partially in training CSV; weak/absent in staging over-side; freeze not persisted
- O/U 4.5: training field unused by extractor; staging unavailable; freeze not connected
- Eval gap: post-June-2026 fixtures lack historical totals CSV coverage

## Remediation (additive, shadow)
`totals_market_shadow_snapshots` stores future/research lines without mutating freezes.
Future prediction jobs should persist 2.5/3.5/4.5 when providers return them.
Never substitute 2.5 for missing 4.5.
"""
