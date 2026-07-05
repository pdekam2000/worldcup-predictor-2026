"""Eligibility rules and temporal causality documentation."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_historical_replay.constants import REPLAY_START_DATE

ELIGIBILITY_RULE = {
    "replay_start_date": REPLAY_START_DATE,
    "source": "external_historical_csv_raw_rows",
    "finished_only": True,
    "required_fields": [
        "eventDate >= 2023-01-01",
        "goalsHomeFullTime valid integer",
        "goalsAwayFullTime valid integer",
        "oddsFT_1 > 1.0",
        "oddsFT_X > 1.0",
        "oddsFT_2 > 1.0",
        "extract_lambdas succeeds",
        "generate_score_distribution succeeds",
        "unique row_hash",
    ],
    "excluded": [
        "missing FT score",
        "invalid odds",
        "lambda extraction failure",
        "duplicate row_hash",
        "fixtures before 2023-01-01",
    ],
    "production_ecse_path": "external_row_to_ecse_odds_features → extract_lambdas → generate_score_distribution",
    "no_production_writes": True,
}

TEMPORAL_CAUSALITY_AUDIT = {
    "odds": {
        "rule": "CSV export contains single prematch closing line per fixture; no post-kickoff odds timestamp in raw JSON",
        "kickoff_field": "eventDate + eventHour",
        "verified": "odds assumed available before kickoff per football-data export convention",
        "limitation": "no explicit closing_unix; cannot verify sub-minute timing",
    },
    "team_form": {
        "rule": "NOT used in production ECSE odds-only lambda path for this replay",
        "verified": True,
    },
    "rolling_stats": {
        "rule": "NOT used in production ECSE odds-only lambda path",
        "verified": True,
    },
    "xg": {
        "rule": "NOT used in extract_lambdas for replay fixtures",
        "verified": True,
        "coverage": 0,
    },
    "pressure": {
        "rule": "NOT used in ECSE lambda extraction",
        "verified": True,
    },
    "standings": {
        "rule": "NOT used in ECSE lambda extraction",
        "verified": True,
    },
    "lineups_injuries": {
        "rule": "NOT used unless present in odds feature row; external CSV lacks these",
        "verified": True,
    },
    "target_match_result": {
        "rule": "actual score used ONLY for evaluation after prediction; never in extract_lambdas input",
        "verified": True,
    },
}


def build_eligibility_report(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "eligibility_rule": ELIGIBILITY_RULE,
        "temporal_causality_audit": TEMPORAL_CAUSALITY_AUDIT,
        "replay_eligible_count": inventory.get("replay_eligible", 0),
        "blocked_reason_if_zero": "ECSE_BACKTEST_BLOCKED_BY_TEMPORAL_DATA_GAPS" if inventory.get("replay_eligible", 0) < 1000 else None,
    }
