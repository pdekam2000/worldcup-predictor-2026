"""Team form snapshot service + writer (future jobs / derived historical).

Does NOT mutate historical freezes. Production team_form_snapshots remains
untouched unless an explicit future job writes new rows.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.football_strength_foundation.constants import (
    DERIVED_FORM_TABLE,
    FEATURE_SCHEMA_VERSION,
)
from worldcup_predictor.research.football_strength_foundation.team_strength_engine import (
    MatchStrengthBundle,
    TeamStrengthEngine,
)

DERIVED_DDL = f"""
CREATE TABLE IF NOT EXISTS {DERIVED_FORM_TABLE} (
    snapshot_id TEXT PRIMARY KEY,
    fixture_id INTEGER NOT NULL,
    team_id TEXT,
    team_name TEXT NOT NULL,
    home_or_away_role TEXT NOT NULL,
    cutoff_timestamp TEXT NOT NULL,
    history_window INTEGER,
    matches_used INTEGER,
    payload_json TEXT NOT NULL,
    feature_completeness REAL,
    fallback_count INTEGER,
    source_hash TEXT,
    feature_schema_version TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    UNIQUE(fixture_id, team_name, home_or_away_role, cutoff_timestamp, feature_schema_version)
)
"""

# Additive enrichment for future production writer (safe; does not rewrite freezes)
PROD_WRITER_DDL_NOTE = """
-- Optional additive columns for future production team_form_snapshots enrichment:
-- ALTER TABLE team_form_snapshots ADD COLUMN feature_schema_version TEXT;
-- ALTER TABLE team_form_snapshots ADD COLUMN snapshot_hash TEXT;
-- ALTER TABLE team_form_snapshots ADD COLUMN cutoff_timestamp TEXT;
-- Writers must only INSERT for NEW prediction jobs; never UPDATE historical freeze-linked rows.
"""


def root_cause_markdown() -> str:
    return """# team_form_snapshots root cause

## Finding
Table `team_form_snapshots` exists in `worldcup_predictor/database/schema.py` with columns
`(fixture_id, team_name, competition_key, snapshot_at, payload_json)`.

## Why empty (n=0)
1. **No writer** — repository lists the table but no INSERT path populates it.
2. **No scheduler / prediction hook** — form is not called from ECSE live prediction builder.
3. **Not a failed migration** — schema creates an empty table successfully.
4. **Incomplete integration** — snapshots were planned for agent/enrichment flows but never wired
   into `extract_lambdas` or freeze persistence.
5. Form for research was derived ad-hoc from results (`PHASE_31C` note) instead of snapshots.

## Classification
**Incomplete integration / missing writer**, not intentional odds-only design for form storage.
Canonical λ remains odds-only because ECSE never consumed football form even if snapshots existed.

## Safe remediation
- Write **derived_historical_team_form_snapshots** for research reconstruction (this package).
- Add optional future-job writer for new predictions only.
- Do not backfill historical freezes as if features existed at prediction time.
"""


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def build_team_payload(
    role: str,
    team_name: str,
    bundle: MatchStrengthBundle,
    *,
    cutoff: datetime,
    window: int,
) -> dict[str, Any]:
    side = bundle.home if role == "home" else bundle.away
    return {
        "team_name": team_name,
        "role": role,
        "cutoff": cutoff.isoformat(),
        "history_window": window,
        "matches_used": side.n_total,
        "attack": {
            "global": side.attack_global,
            "home": side.attack_home,
            "away": side.attack_away,
            "trend": side.scoring_trend,
            "variance": side.scoring_var,
            "freq_2plus": side.freq_score_2plus,
            "freq_3plus": side.freq_score_3plus,
        },
        "defense": {
            "global": side.defense_global,
            "home": side.defense_home,
            "away": side.defense_away,
            "trend": side.defensive_trend,
            "variance": side.conceding_var,
            "freq_concede_2plus": side.freq_concede_2plus,
            "freq_concede_3plus": side.freq_concede_3plus,
            "clean_sheet_rate": side.freq_clean_sheet,
        },
        "volatility": {
            "btts": side.freq_btts,
            "over25": side.freq_over25,
            "over35": side.freq_over35,
            "over45": side.freq_over45,
        },
        "league_normalization": {
            "league_avg_home": bundle.league_avg_home,
            "league_avg_away": bundle.league_avg_away,
            "environment": bundle.league_environment,
        },
        "quality": {
            "fallback_count": side.fallback_count,
            "low_data": side.low_data,
            "promoted_like": side.promoted_like,
            "uncertainty": side.uncertainty,
            "quality_tier": side.quality_tier,
        },
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
    }


class TeamFormSnapshotWriter:
    """Writes derived research snapshots only (default)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.execute(DERIVED_DDL)
        from worldcup_predictor.research.football_strength_foundation.schema_upgrade import (
            upgrade_shadow_tables,
        )

        upgrade_shadow_tables(self.conn)
        self.conn.commit()

    def persist_derived(
        self,
        *,
        fixture_id: int,
        home_team: str,
        away_team: str,
        cutoff: datetime,
        engine: TeamStrengthEngine,
        league: str,
        window: int = 40,
    ) -> list[str]:
        bundle = engine.build_match(home_team, away_team, cutoff, league, target_fixture_id=fixture_id)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        ids = []
        for role, name in (("home", home_team), ("away", away_team)):
            payload = build_team_payload(role, name, bundle, cutoff=cutoff, window=window)
            sh = _hash(payload)
            sid = f"dfs-{fixture_id}-{role}-{sh[:12]}"
            self.conn.execute(
                f"""
                INSERT OR REPLACE INTO {DERIVED_FORM_TABLE} (
                    snapshot_id, fixture_id, team_id, team_name, home_or_away_role,
                    cutoff_timestamp, history_window, matches_used, payload_json,
                    feature_completeness, fallback_count, source_hash,
                    feature_schema_version, snapshot_hash, created_at_utc
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid,
                    int(fixture_id),
                    None,
                    name,
                    role,
                    cutoff.isoformat(),
                    window,
                    int(payload["matches_used"]),
                    json.dumps(payload, default=str),
                    max(0.0, 1.0 - payload["quality"]["fallback_count"] / 4.0),
                    int(payload["quality"]["fallback_count"]),
                    sh[:16],
                    FEATURE_SCHEMA_VERSION,
                    sh,
                    now,
                ),
            )
            ids.append(sid)
        self.conn.commit()
        return ids


def write_future_production_snapshot(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    team_name: str,
    competition_key: str,
    payload: dict[str, Any],
    allow_production_write: bool = False,
) -> None:
    """Optional writer for NEW jobs only. Disabled unless explicitly allowed."""
    if not allow_production_write:
        raise RuntimeError("Production team_form_snapshots write disabled (shadow/research default)")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    conn.execute(
        """
        INSERT INTO team_form_snapshots (fixture_id, team_name, competition_key, snapshot_at, payload_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(fixture_id), team_name, competition_key, now, json.dumps(payload, default=str)),
    )
    conn.commit()
