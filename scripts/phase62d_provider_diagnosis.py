#!/usr/bin/env python3
"""Phase 62D — provider limit diagnosis on production SQLite."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "validation" / "phase62d_provider_diagnosis.json"


def main() -> int:
    db = ROOT / "data" / "football_intelligence.db"
    conn = sqlite3.connect(db)
    ck = "world_cup_2026"

    def count(q: str, params=()) -> int:
        return int(conn.execute(q, params).fetchone()[0] or 0)

    wc = count("SELECT COUNT(1) FROM fixtures WHERE competition_key=?", (ck,))
    finished = count(
        "SELECT COUNT(1) FROM fixtures f JOIN fixture_results r ON r.fixture_id=f.fixture_id WHERE f.competition_key=?",
        (ck,),
    )
    goals = count(
        """
        SELECT COUNT(DISTINCT f.fixture_id) FROM fixtures f
        JOIN fixture_goal_events g ON g.fixture_id=f.fixture_id
        WHERE f.competition_key=?
        """,
        (ck,),
    )
    xg = count(
        """
        SELECT COUNT(DISTINCT x.fixture_id) FROM xg_snapshots x
        JOIN fixtures f ON f.fixture_id=x.fixture_id WHERE f.competition_key=?
        """,
        (ck,),
    )
    odds = count(
        """
        SELECT COUNT(DISTINCT o.fixture_id) FROM odds_snapshots o
        JOIN fixtures f ON f.fixture_id=o.fixture_id WHERE f.competition_key=?
        """,
        (ck,),
    )
    lineups = count(
        """
        SELECT COUNT(1) FROM fixture_enrichment e
        JOIN fixtures f ON f.fixture_id=e.fixture_id
        WHERE f.competition_key=? AND e.lineups_json IS NOT NULL AND e.lineups_json NOT IN ('','[]','null')
        """,
        (ck,),
    )
    mapped = count(
        "SELECT COUNT(1) FROM wc_fixture_mapping WHERE sportmonks_fixture_id IS NOT NULL AND blocked=0"
    )
    unmapped = count(
        "SELECT COUNT(1) FROM wc_fixture_mapping WHERE sportmonks_fixture_id IS NULL OR blocked=1"
    )

    sm_dir = ROOT / "data" / "egie" / "world_cup" / "raw" / "sportmonks"
    cache_samples: list[dict] = []
    for p in sorted(sm_dir.glob("*.json"))[:5]:
        try:
            blob = json.loads(p.read_text(encoding="utf-8"))
            data = (blob.get("payload") or {}).get("data") or {}
            cache_samples.append(
                {
                    "file": p.name,
                    "has_lineups": bool(data.get("lineups")),
                    "lineup_count": len(data.get("lineups") or []),
                    "has_xg_fixture": bool(data.get("xGFixture") or data.get("xgfixture")),
                    "league_id": data.get("league_id"),
                    "season_id": data.get("season_id"),
                }
            )
        except (json.JSONDecodeError, OSError):
            pass

    xg_reasons: dict[str, int] = {}
    for row in conn.execute(
        "SELECT payload_json FROM xg_snapshots x JOIN fixtures f ON f.fixture_id=x.fixture_id WHERE f.competition_key=? LIMIT 100",
        (ck,),
    ):
        try:
            p = json.loads(row[0] or "{}")
            reason = p.get("xg_missing_reason") or ("available" if p.get("xg_available") else "unknown")
            xg_reasons[reason] = xg_reasons.get(reason, 0) + 1
        except json.JSONDecodeError:
            xg_reasons["parse_error"] = xg_reasons.get("parse_error", 0) + 1

    seasons = conn.execute(
        "SELECT season, COUNT(1) FROM fixtures WHERE competition_key=? GROUP BY season ORDER BY season",
        (ck,),
    ).fetchall()

    result = {
        "wc_fixtures": wc,
        "finished_fixtures": finished,
        "goal_event_fixtures": goals,
        "xg_snapshots": xg,
        "odds_snapshots": odds,
        "lineup_enrichment_rows": lineups,
        "sportmonks_mapped": mapped,
        "sportmonks_unmapped": unmapped,
        "xg_coverage_pct": round(xg / wc, 4) if wc else 0,
        "lineup_coverage_pct": round(lineups / wc, 4) if wc else 0,
        "odds_coverage_pct": round(odds / wc, 4) if wc else 0,
        "goal_event_coverage_pct": round(goals / finished, 4) if finished else 0,
        "per_season_fixture_counts": {str(s): c for s, c in seasons},
        "xg_missing_reasons_sample": xg_reasons,
        "sportmonks_cache_samples": cache_samples,
        "sportmonks_cache_file_count": len(list(sm_dir.glob("*.json"))) if sm_dir.is_dir() else 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
