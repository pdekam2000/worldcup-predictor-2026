"""Additive column upgrades for thin Gate-0 shadow tables (idempotent)."""

from __future__ import annotations

import sqlite3

UPGRADES: dict[str, list[tuple[str, str]]] = {
    "derived_historical_team_form_snapshots": [
        ("team_id", "TEXT"),
        ("history_window", "INTEGER"),
        ("matches_used", "INTEGER"),
        ("feature_completeness", "REAL"),
        ("fallback_count", "INTEGER"),
        ("source_hash", "TEXT"),
        ("created_at_utc", "TEXT"),
    ],
    "totals_market_shadow_snapshots": [
        ("registry_fixture_id", "INTEGER"),
        ("implied_over", "REAL"),
        ("implied_under", "REAL"),
        ("devig_over", "REAL"),
        ("provider", "TEXT"),
        ("bookmaker", "TEXT"),
        ("bookmaker_count", "INTEGER"),
        ("consensus", "TEXT"),
        ("odds_timestamp", "TEXT"),
        ("odds_age_minutes", "REAL"),
        ("freshness", "TEXT"),
        ("source_hash", "TEXT"),
        ("payload_json", "TEXT"),
    ],
    "lambda_v2_shadow_outputs": [
        ("canonical_prediction_id", "TEXT"),
        ("model_version", "TEXT"),
        ("feature_schema_version", "TEXT"),
        ("feature_cutoff", "TEXT"),
        ("history_count_home", "INTEGER"),
        ("history_count_away", "INTEGER"),
        ("missing_count", "INTEGER"),
        ("fallback_count", "INTEGER"),
        ("odds_freshness", "TEXT"),
        ("totals_lines_json", "TEXT"),
        ("lambda_home", "REAL"),
        ("lambda_away", "REAL"),
        ("lambda_uncertainty", "REAL"),
        ("score_distribution_type", "TEXT"),
        ("top1", "TEXT"),
        ("top5_json", "TEXT"),
        ("top10_json", "TEXT"),
        ("top5_mass", "REAL"),
        ("entropy", "REAL"),
        ("wde_direction_mass", "REAL"),
        ("btts_mass", "REAL"),
        ("ou_mass", "REAL"),
        ("payload_json", "TEXT"),
    ],
}


def upgrade_shadow_tables(conn: sqlite3.Connection) -> list[str]:
    applied: list[str] = []
    for table, cols in UPGRADES.items():
        try:
            have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        except Exception:
            continue
        if not have:
            continue
        for name, typ in cols:
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {typ}")
                applied.append(f"{table}.{name}")
    if applied:
        conn.commit()
    return applied
