"""Optional owner-only daily pipeline enrichment for Correct Score odds.

Does NOT:
- block canonical prediction
- modify ECSE/WDE
- create prediction jobs
- evaluate matches
- promote portfolio
"""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.correct_score_odds.ingest import ingest_from_odds_snapshots
from worldcup_predictor.research.correct_score_odds.statuses import (
    CS_ODDS_AVAILABLE,
    CS_ODDS_PARTIAL,
    CS_ODDS_UNAVAILABLE,
)
from worldcup_predictor.research.correct_score_odds.store import best_odds_map, fixture_status


def enrich_correct_score_odds(
    conn,
    fixture_ids: list[int],
    *,
    enabled: bool = True,
) -> dict[str, Any]:
    """Cache-first CS extraction for daily fixtures; never raises into prediction path."""
    if not enabled:
        return {
            "enabled": False,
            "status": CS_ODDS_UNAVAILABLE,
            "fixtures": {},
            "prediction_jobs_created": 0,
            "freezes_modified": 0,
            "blocked_prediction": False,
        }
    try:
        extract = ingest_from_odds_snapshots(conn, fixture_ids=fixture_ids)
        per: dict[str, Any] = {}
        for fid in fixture_ids:
            m = best_odds_map(conn, int(fid))
            n = len(m)
            if n >= 10:
                st = CS_ODDS_AVAILABLE
            elif n > 0:
                st = CS_ODDS_PARTIAL
            else:
                st = CS_ODDS_UNAVAILABLE
            per[str(fid)] = {
                "status": st,
                "n_selections": n,
                "fixture_status_top5_unknown": fixture_status(conn, int(fid), []),
            }
        avail = sum(1 for v in per.values() if v["status"] == CS_ODDS_AVAILABLE)
        partial = sum(1 for v in per.values() if v["status"] == CS_ODDS_PARTIAL)
        overall = CS_ODDS_AVAILABLE if avail else (CS_ODDS_PARTIAL if partial else CS_ODDS_UNAVAILABLE)
        return {
            "enabled": True,
            "status": overall,
            "fixtures": per,
            "extract": {
                "lines_inserted": extract.get("lines_inserted"),
                "api_calls": extract.get("api_calls", 0),
            },
            "prediction_jobs_created": 0,
            "freezes_modified": 0,
            "blocked_prediction": False,
            "marks_unavailable_clearly": True,
        }
    except Exception as exc:
        return {
            "enabled": True,
            "status": CS_ODDS_UNAVAILABLE,
            "error": str(exc)[:300],
            "prediction_jobs_created": 0,
            "freezes_modified": 0,
            "blocked_prediction": False,
        }
