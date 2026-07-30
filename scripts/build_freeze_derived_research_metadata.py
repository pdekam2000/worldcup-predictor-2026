#!/usr/bin/env python3
"""Build derived research metadata for historical freezes WITHOUT mutating freeze rows.

Writes only to freeze_derived_research_metadata (research table).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.forward_evaluation.context import entropy_from_scores
from worldcup_predictor.forward_evaluation.db import connect_eval_db, ensure_schema
from worldcup_predictor.forward_evaluation.probability_units import to_fraction, top_mass


def main() -> None:
    ev = connect_eval_db(ROOT)
    ensure_schema(ev)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    n_ins = 0
    for row in ev.execute("SELECT * FROM frozen_predictions"):
        fr = dict(row)
        pid = fr["prediction_id"]
        payload = {}
        raw = fr.get("complete_payload_json")
        if raw:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
        ecse = payload.get("ecse") or {}
        tops = []
        for item in ecse.get("top10") or []:
            if isinstance(item, dict):
                tops.append(
                    {
                        "rank": item.get("rank"),
                        "score": item.get("scoreline") or item.get("score"),
                        "probability": to_fraction(item.get("probability")),
                    }
                )
        if not tops:
            for r in ev.execute(
                "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
                (pid,),
            ):
                tops.append(
                    {
                        "rank": r["rank"],
                        "score": r["score"],
                        "probability": to_fraction(r["probability"]),
                    }
                )
        evidence = payload.get("evidence") or {}
        ev.execute(
            """
            INSERT OR REPLACE INTO freeze_derived_research_metadata (
                prediction_id, fixture_id, derived_at_utc, source,
                odds_home, odds_draw, odds_away, bookmaker_count, odds_provider,
                odds_fetched_at_utc, odds_freshness_status,
                top3_mass, top5_mass, entropy, rank_probabilities_json,
                consensus, conflict_count, no_bet, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid,
                int(fr["fixture_id"]),
                now,
                "payload_or_rankings_reconstruction",
                evidence.get("odds_home") or fr.get("odds_home"),
                evidence.get("odds_draw") or fr.get("odds_draw"),
                evidence.get("odds_away") or fr.get("odds_away"),
                evidence.get("bookmaker_count") or fr.get("bookmaker_count"),
                evidence.get("provider"),
                evidence.get("odds_fetched_at_utc") or fr.get("odds_fetched_at_utc"),
                evidence.get("odds_freshness_status") or fr.get("odds_freshness_status"),
                top_mass(tops, 3),
                top_mass(tops, 5),
                entropy_from_scores(tops),
                json.dumps(tops[:10], default=str),
                fr.get("consensus") or payload.get("consensus"),
                payload.get("conflict_count"),
                1 if payload.get("no_bet") is True else (0 if payload.get("no_bet") is False else None),
                "Historical freezes untouched; values derived for research only",
            ),
        )
        n_ins += 1
    ev.commit()
    print(json.dumps({"derived_rows": n_ins, "table": "freeze_derived_research_metadata"}))
    ev.close()


if __name__ == "__main__":
    main()
