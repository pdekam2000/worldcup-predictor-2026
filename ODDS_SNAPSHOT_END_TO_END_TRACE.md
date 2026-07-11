# Odds Snapshot End-to-End Trace

Test date: 2026-07-11 (Europe/Vienna). Five fixtures blocked in production with impossible state: filter showed complete 1X2 odds while prediction reported `ODDS_MISSING` / `age_minutes=null`.

## Root bridge defect

| Layer | Read path (before) | Read path (after hotfix) |
|-------|-------------------|--------------------------|
| `filterMatchesByOdds` / `_match_odds` | Parsed `payload.bookmakers` via `_latest_odds_snapshot` | `get_latest_valid_1x2_odds_snapshot` |
| `build_fixture_freshness_metadata` | `has_odds = bool(snapshot_at column)` only | Canonical snapshot: odds from payload + timestamp from column or payload aliases |
| `validate_legitimate_1x2_snapshot` | Required DB column `snapshot_at` | Canonical snapshot with `extract_odds_fetched_at_utc` |
| `refresh_gate` post-refresh | Same column-only semantics | Re-reads canonical snapshot after committed import |

## Per-fixture trace (production failure pattern)

All five fixtures share the same mismatch signature:

| Step | Observation |
|------|-------------|
| 1 Discovery | Fixture present in owner scope |
| 2 filterMatchesByOdds | `bookmaker_count=14`, complete H/D/A, `provider=api-football` |
| 3 Provider refresh | `refresh_success=true`, rows imported |
| 4 DB row | `payload.fetched_at_utc` populated; `snapshot_at` column often null on legacy rows |
| 5 Freshness lookup (before) | `load_fixture_odds_snapshot` returned `(None, provider)` → `has_odds=False` |
| 6 Classification (before) | `ODDS_MISSING`, `age_minutes=null`, `STALE_ODDS_AFTER_REFRESH` |
| 7 Block | WDE/BTTS/O-U/ECSE unavailable |

### Fixture 1581037 — Norway vs England (Tier A)

| Stage | fixture_id | provider | market | H/D/A | timestamp source | freshness |
|-------|------------|----------|--------|-------|------------------|-----------|
| Filter | 1581037 | api-football | Match Winner | 4.00/3.82/1.87 | payload | visible |
| Pre-fix freshness | 1581037 | api-football | — | — | column null | ODDS_MISSING |
| Post-fix freshness | 1581037 | api-football | FULL_TIME_1X2 | median | payload.fetched_at_utc | ODDS_FRESH or ODDS_STALE with real age |

### Fixture 1494694 — Fredrikstad vs Lillestrom (Tier B)

| Stage | fixture_id | provider | H/D/A | timestamp | freshness |
|-------|------------|----------|-------|-----------|-----------|
| Filter | 1494694 | api-football | 2.90/3.40/2.35 | payload | visible |
| Pre-fix | 1494694 | — | — | missing in column | ODDS_MISSING |
| Post-fix | 1494694 | api-football | same | payload alias | classified with age |

### Fixture 1495730 — Lahti vs HJK Helsinki (Tier B)

Same pattern as 1494694.

### Fixture 1494206 — Mjallby AIF vs AIK Stockholm (Tier B)

Same pattern as 1494694.

### Fixture 1494692 — Aalesund vs Molde (Tier B)

Same pattern as 1494694.

## Shared fix

`worldcup_predictor/odds/canonical_snapshot.py` provides:

- `normalize_odds_market_name`
- `extract_odds_fetched_at_utc`
- `get_latest_valid_1x2_odds_snapshot`

All consumers now call this single service.
