# PHASE 54H — Pressure Feature Store Foundation Report

**Date:** 2026-06-24  
**Mode:** Architecture → Implementation → Validation → Report  
**Status:** COMPLETE (shadow/research layer only — no production, WDE, SaaS, or deploy)

**Artifacts:** `artifacts/phase54h_pressure_feature_store/`

---

## Executive Summary

Built a reusable **Sportmonks Pressure Feature Store** mirroring the xG store pattern: normalize minute-level `pressure` rows, persist to PostgreSQL, compute fixture aggregations, and support cache-first backfill.

| Metric | Value |
|--------|-------|
| Pressure records imported | **12,676** |
| Fixtures with pressure | **65** |
| Avg rows per fixture | **195.0** |
| Avg minutes per fixture | **97.5** |
| Leagues covered | **3** (CL, EL, Conference) |
| Duplicate groups | **0** |
| API calls (cache import) | **0** |
| Validation | **17/17 PASS** |

**Final recommendation:** Proceed to **Phase 54H-1** — pressure shadow backtest for Goal Minute and Next Goal Team (no EGIE scoring integration yet).

---

## Files Created / Changed

### New modules

| Path | Purpose |
|------|---------|
| `worldcup_predictor/feature_store/pressure_store/models.py` | `SportmonksPressureRecord`, `FixturePressureSummary`, `PressureIngestResult` |
| `worldcup_predictor/feature_store/pressure_store/normalizers.py` | Parse `pressure[]` rows + event-linked first goal |
| `worldcup_predictor/feature_store/pressure_store/aggregations.py` | 11 aggregation features per team/match |
| `worldcup_predictor/feature_store/pressure_store/repository.py` | PostgreSQL upsert, manifest, audit |
| `worldcup_predictor/feature_store/pressure_store/sportmonks_pressure_store.py` | Ingest orchestrator + backfill |
| `worldcup_predictor/feature_store/pressure_store/__init__.py` | Package exports |

### Migration

| Path | Purpose |
|------|---------|
| `alembic/versions/012_sportmonks_pressure_feature_store.py` | Revision `012_pressure_feature_store` |

### Scripts

| Path | Purpose |
|------|---------|
| `scripts/phase54h_pressure_feature_store_backfill.py` | CLI backfill |
| `scripts/validate_phase54h_pressure_feature_store.py` | Validation gate |

---

## PostgreSQL Tables Created

### `fs_sportmonks_pressure_records`

Minute-level rows. Unique constraint: `(sportmonks_fixture_id, pressure_row_id)`.

| Column | Type |
|--------|------|
| id | UUID |
| sportmonks_fixture_id | BIGINT |
| fixture_id | BIGINT (nullable) |
| league_id, season_id | INT |
| participant_id, team_id | INT |
| minute | INT |
| pressure_value | NUMERIC(12,4) |
| pressure_row_id | BIGINT (Sportmonks row id) |
| captured_at | TIMESTAMPTZ |
| source | VARCHAR(32) |
| raw_reference | VARCHAR(512) |
| metadata | JSONB |

### `fs_sportmonks_pressure_fixture_summary`

One row per fixture with aggregated `features_json`.

| Column | Type |
|--------|------|
| sportmonks_fixture_id | BIGINT PK |
| pressure_row_count, unique_minutes | INT |
| first_goal_minute | INT |
| features_json | JSONB (home/away/match aggregations) |
| home_team_id, away_team_id | INT |
| match_started_at | TIMESTAMPTZ |

### `fs_sportmonks_pressure_ingest_manifest`

Resumable job tracking. Unique: `(job_key, sportmonks_fixture_id)`.

---

## Records Imported

**Command:**

```bash
python scripts/phase54h_pressure_feature_store_backfill.py --cache-only --force-reimport --league-id 0
```

| Result | Value |
|--------|-------|
| Cache files processed | 80 |
| Fixtures imported | 65 |
| Fixtures empty (no pressure) | 15 |
| Records written | 12,676 |
| Summaries created | 65 |

### Coverage by league (from cache)

| League | Fixtures in cache | With pressure |
|--------|-------------------|---------------|
| Champions League (2) | 30 | 25 |
| Europa League (5) | 30 | 25 |
| Conference League (2286) | 20 | 15 |

---

## Aggregation Examples

Fixture `19135056` (Conference League):

```json
{
  "home": {
    "average_pressure": 24.98,
    "max_pressure": 100.0,
    "pressure_first_15": 3.87,
    "pressure_first_30": 5.86,
    "pressure_before_first_goal": 3.49,
    "pressure_spike_count": 17,
    "pressure_dominance": 0.8323,
    "pressure_momentum": 76.93,
    "pressure_swing": 100.0,
    "pressure_last_5": 80.0,
    "pressure_last_10": 90.0
  },
  "away": {
    "average_pressure": 5.03,
    "pressure_dominance": 0.1677,
    "pressure_first_15": 4.75
  },
  "match": {
    "pressure_asymmetry": 19.95,
    "pressure_first_15_edge": -0.88
  },
  "first_goal_minute": 3
}
```

All 11 required aggregations are computed per team in `features_json.home` / `features_json.away`.

---

## Duplicate Protection

- **DB constraint:** `UNIQUE (sportmonks_fixture_id, pressure_row_id)`
- **Ingest dedupe:** Skip duplicate `(fixture, participant, minute)` within same payload
- **Re-import:** `ON CONFLICT DO UPDATE` — re-running backfill does not duplicate rows
- **Manifest skip:** Second `--cache-only` run skips already-imported fixtures (0 new writes)
- **Audit:** `duplicate_groups_sample = []`

---

## EGIE Readiness

| Capability | Status |
|------------|--------|
| Minute-level pressure in DB | **Ready** |
| Fixture summaries + aggregations | **Ready** |
| First goal minute linkage | **Ready** (from `events.type`) |
| Shadow backtest dataset | **Not yet built** |
| EGIE scoring integration | **NOT wired** (by design) |
| WDE / production predictions | **NOT modified** |

### Market alignment (from 54G)

| Market | Store support |
|--------|---------------|
| Goal Minute | VERY_HIGH — full timeline available |
| Next Goal Team | HIGH — live windows (`pressure_last_5/10`, momentum) |
| First Goal Team | HIGH — `pressure_first_15`, dominance |
| Live Goal Probability | HIGH — momentum, swing, spikes |
| Goal Range / Team Goals | MEDIUM — match-level integrals only |

---

## Validation

```bash
python scripts/validate_phase54h_pressure_feature_store.py
```

**17/17 PASS** — records imported, minute rows, summaries, aggregations, duplicate protection, no token leaks, no production changes.

---

## CLI Reference

```bash
# Full UEFA cache import (recommended for local dev)
python scripts/phase54h_pressure_feature_store_backfill.py --cache-only --league-id 0

# Single league from cache
python scripts/phase54h_pressure_feature_store_backfill.py --cache-only --league-id 2

# Live API backfill (requires valid token)
python scripts/phase54h_pressure_feature_store_backfill.py --league-id 2 --season-id <id> --max-calls 80

# Force re-import
python scripts/phase54h_pressure_feature_store_backfill.py --cache-only --league-id 0 --force-reimport

# Dry run
python scripts/phase54h_pressure_feature_store_backfill.py --league-id 2 --dry-run
```

---

## Next Phase Recommendation

**Phase 54H-1 — Pressure Shadow Backtest**

1. Build `pressure_backtest` dataset from `fs_sportmonks_pressure_fixture_summary` (mirror 54F xG path).
2. Evaluate Goal Minute hazard and Next Goal Team arms vs baseline.
3. Keep First Goal Team on **no-xG** policy (54F-7); test pressure-only arm separately.
4. Do **not** wire to EGIE scoring or WDE until shadow validation passes significance thresholds.

---

## Constraints Honored

| Constraint | Status |
|------------|--------|
| Production deploy | **NOT done** |
| Live predictions | **NOT modified** |
| WDE | **NOT modified** |
| SaaS logic | **NOT modified** |
| EGIE scoring | **NOT integrated** |
