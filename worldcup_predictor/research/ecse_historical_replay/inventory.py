"""Load and audit historical fixture inventory from 2023."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.ecse_historical_replay.constants import REPLAY_START_DATE
from worldcup_predictor.research.ecse_market_prior.dataset import external_row_to_ecse_odds_features
from worldcup_predictor.research.ecse_lambda_extraction import extract_lambdas


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _parse_date(raw: dict) -> str | None:
    d = str(raw.get("eventDate") or "")[:10]
    return d if len(d) >= 10 else None


def _competition_label(league: str, source_file: str) -> str:
    sf = source_file.lower()
    if "champions" in sf or league.upper() in ("CL1", "UCL"):
        return "Champions League"
    if "europa" in sf and "conference" not in sf:
        return "Europa League"
    if "conference" in sf:
        return "Conference League"
    if "world" in sf or "wc" in sf:
        return "World Cup"
    return league or "unknown"


def build_inventory(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    by_competition: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    years = Counter()
    total_rows = 0
    finished = 0
    odds_ok = 0
    lambda_ok = 0
    eligible = 0

    for row in conn.execute("SELECT row_hash, source_file, raw_row_json FROM external_historical_csv_raw_rows"):
        total_rows += 1
        try:
            raw = json.loads(row["raw_row_json"])
        except json.JSONDecodeError:
            continue
        d = _parse_date(raw)
        if not d or d < REPLAY_START_DATE:
            continue
        years[d[:4]] += 1
        comp = _competition_label(str(raw.get("league") or ""), str(row["source_file"]))
        by_competition[comp]["total"] += 1

        gh, ga = raw.get("goalsHomeFullTime"), raw.get("goalsAwayFullTime")
        if gh is None or ga is None or str(gh).strip() == "" or str(ga).strip() == "":
            continue
        try:
            int(float(gh)); int(float(ga))
        except (TypeError, ValueError):
            continue
        finished += 1
        by_competition[comp]["finished"] += 1

        oh, od, oa = raw.get("oddsFT_1"), raw.get("oddsFT_X"), raw.get("oddsFT_2")
        if not all([oh, od, oa]):
            continue
        try:
            if float(oh) <= 1 or float(od) <= 1 or float(oa) <= 1:
                continue
        except (TypeError, ValueError):
            continue
        odds_ok += 1
        by_competition[comp]["odds_coverage"] += 1

        features = external_row_to_ecse_odds_features(raw)
        features["registry_fixture_id"] = 0
        lam = extract_lambdas(features)
        if not lam or not lam.get("lambda_home") or not lam.get("lambda_away"):
            continue
        lambda_ok += 1
        by_competition[comp]["ecse_eligible"] += 1
        eligible += 1
        by_competition[comp]["replayable"] += 1

    table = []
    for comp, stats in sorted(by_competition.items(), key=lambda x: -x[1].get("replayable", 0)):
        table.append(
            {
                "competition": comp,
                "finished": stats.get("finished", 0),
                "ecse_eligible": stats.get("ecse_eligible", 0),
                "odds_coverage": stats.get("odds_coverage", 0),
                "required_feature_coverage": stats.get("ecse_eligible", 0),
                "replayable": stats.get("replayable", 0),
            }
        )

    frozen_n = 0
    if _table_exists(conn, "ecse_prediction_snapshots"):
        frozen_n = conn.execute(
            """
            SELECT COUNT(1) FROM ecse_prediction_snapshots ec
            INNER JOIN fixture_results fr ON fr.fixture_id = ec.fixture_id
            INNER JOIN fixtures f ON f.fixture_id = ec.fixture_id
            WHERE f.kickoff_utc >= ?
            """,
            (REPLAY_START_DATE,),
        ).fetchone()[0]

    return {
        "generated_at_utc": _utc_now(),
        "replay_start_date": REPLAY_START_DATE,
        "source_table": "external_historical_csv_raw_rows",
        "total_external_rows": total_rows,
        "fixtures_from_2023": sum(years.values()),
        "finished_with_scores": finished,
        "prematch_odds_coverage": odds_ok,
        "ecse_lambda_eligible": lambda_ok,
        "replay_eligible": eligible,
        "years": dict(sorted(years.items())),
        "competition_table": table,
        "feature_coverage_notes": {
            "odds": "oddsFT_1/X/2 prematch closing in CSV export",
            "xg": conn.execute("SELECT COUNT(1) FROM xg_snapshots").fetchone()[0] if _table_exists(conn, "xg_snapshots") else 0,
            "pressure": "not in external CSV source",
            "standings": "not reconstructed for external CSV replay",
            "form": "not used in production ECSE odds-only path",
            "lineups": "not in external CSV source",
            "injuries": "not in external CSV source",
        },
        "frozen_production_snapshots_2023plus": frozen_n,
    }
