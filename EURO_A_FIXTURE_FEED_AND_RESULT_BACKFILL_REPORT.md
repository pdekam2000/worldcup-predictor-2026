# EURO-A — European Fixture Feed & Result Backfill Report

**Phase:** EURO-A (data import/wiring only)  
**Date:** 2026-06-30  
**Scope:** No prediction logic, ECSE, WDE, EGIE, billing, or public UI changes.

---

## Executive summary

EURO-A delivered a central European competition registry, upcoming fixture import CLI, UEFA historical result backfill CLI, domestic verification, validation harness, and coverage artifacts. **Upcoming UEFA fixtures are now in SQLite** with provider IDs and UTC kickoffs. **PL/Bundesliga historical results remain intact.** UEFA cup historical `fixture_results` were **partially** backfilled (58 of ~220 finished fixtures without results at audit time); the majority of legacy Sportmonks-keyed rows still cannot be resolved via API-Football team+date matching alone.

**Final recommendation:** `NEED_RESULT_BACKFILL_FIX`

---

## Part A — Competition registry

Central registry: `worldcup_predictor/config/euro_feed_registry.py`  
League registry hook: `EURO_A_FEED_KEYS` in `worldcup_predictor/config/league_registry.py`

| competition_key | provider | provider_league_id | provider_season_id | timezone | fixtures | results | odds | ECSE* | WDE* |
|-----------------|----------|-------------------|-------------------|----------|----------|---------|------|-------|------|
| premier_league | api-football | 39 | 2026 (active) | utc_storage | yes | yes | yes | yes* | yes* |
| bundesliga | api-football | 78 | 2026 (active) | utc_storage | yes | yes | yes | yes* | yes* |
| champions_league | api-football | 2 | 2026 (active) | utc_storage | yes | yes | yes | yes* | yes* |
| europa_league | api-football | 3 | 2025 (active) | utc_storage | yes | yes | yes | yes* | yes* |
| conference_league | api-football | 848 | 2025 (active) | utc_storage | yes | yes | yes | yes* | yes* |

\*ECSE/WDE flags indicate registry capability only — **no predictions were generated in EURO-A.**

Sportmonks league IDs are recorded for reference (`8`, `82`, `2`, `5`, `2286`); live enrichment remains WC-scoped elsewhere by design.

No generic `euro_club_tournaments` internal prediction key is used.

---

## Part B — Upcoming fixture import

**Script:** `scripts/import_european_fixtures.py`  
**Module:** `worldcup_predictor/data_import/european_fixture_feed.py`

### CLI examples (verified)

```bash
python scripts/import_european_fixtures.py --competitions premier_league bundesliga --days-ahead 14
python scripts/import_european_fixtures.py --competitions champions_league europa_league conference_league --days-ahead 30
python scripts/import_european_fixtures.py --dry-run
```

### Behavior

- Fetches from API-Football (primary) and optional Sportmonks supplement
- Normalizes `competition_key` per registry
- Persists to SQLite `fixtures` with deduplication
- Stores provider fixture IDs, kickoff UTC, teams, status, raw payload refs (`euro_fixture_feed` / `artifacts/euro_a/raw_payloads/`)
- Skips unsupported competitions with explicit reasons
- **Does not** create WDE/ECSE predictions

### Import outcome (30-day window, final run)

| Competition | Fixtures before → after | Upcoming before → after | New rows imported (net) |
|-------------|-------------------------|-------------------------|-------------------------|
| premier_league | 380 → 380 | 0 → 0 | 0 (off-season window) |
| bundesliga | 1,232 → 1,232 | 0 → 0 | 0 (off-season window) |
| champions_league | 90 → 150 | 0 → 36 | +60 fixtures in DB |
| europa_league | 65 → 93 | 0 → 20 | +28 fixtures in DB |
| conference_league | 65 → 177 | 0 → 86 | +112 fixtures in DB |

Provider fetches in the latest run mostly hit existing rows (`duplicates_avoided: 366`); upcoming UEFA fixtures were established in earlier EURO-A runs and remain present.

---

## Part C — UEFA historical result backfill

**Script:** `scripts/backfill_european_fixture_results.py`  
**Module:** `worldcup_predictor/data_import/european_result_backfill.py`

### Fix applied during EURO-A

API-Football rejects `season` combined with `from`/`to`. Backfill resolver now:

1. Tries fixture-by-id (legacy Sportmonks IDs usually fail)
2. Queries **league + date only** (no season param)
3. Falls back to full-season scan filtered by date + normalized team names (Unicode accent stripping)
4. Re-keys fixtures to API-Football IDs when resolved

### Backfill results (full run)

| Competition | Scanned (missing results) | Backfilled | Still missing provider | Results before → after |
|-------------|---------------------------|------------|------------------------|------------------------|
| champions_league | 90 | 24 | 66 | 0 → 24 |
| europa_league | 65 | 8 | 57 | 0 → 8 |
| conference_league | 65 | 26 | 39 | 0 → 26 |
| **Total** | **220** | **58** | **162** | — |

Remaining gaps are predominantly **legacy Sportmonks `fixture_id` rows** with team-name mismatches vs API-Football (special characters, alternate club names) and older seasons (2021–2023) where date+league queries return no match.

---

## Part D — PL/Bundesliga verification

Read-only 20-fixture random samples per league:

| Competition | Sample OK | Total fixture_results | Status |
|-------------|-----------|----------------------|--------|
| premier_league | 20/20 | 380 | passed |
| bundesliga | 20/20 | 1,232 | passed |

No re-import performed. `competition_key` preserved on all sampled rows.

---

## Part E — Coverage summary artifact

**Path:** `artifacts/euro_a_fixture_feed_summary.json`

Includes `registry`, `fixture_import`, `result_backfill`, `domestic_verification`, and consolidated `coverage_summary` per competition (fixtures/upcoming/results before/after, odds rows, provider mapping notes, backfill counts).

---

## Part F — Validation

**Script:** `scripts/validate_euro_a_fixture_feed.py`  
**Result:** **PASSED** (all checks green)

Verified:

- Competition keys preserved; no `international` mislabels
- No duplicate `fixture_id` groups
- Provider league IDs present; kickoff UTC valid
- UEFA finished fixtures can receive `fixture_results` (58 demonstrated)
- PL/Bundesliga samples intact
- **0** ECSE snapshots for European keys
- **0** WDE stored predictions for European keys
- ECSE baseline tables present (unchanged)
- No billing/subscription/public output changes

---

## Skipped competitions and errors

| Item | Reason |
|------|--------|
| premier_league / bundesliga upcoming | No fixtures in 30-day provider window (off-season) |
| UEFA historical rows (162) | `no_provider_payload_or_goals` — legacy Sportmonks IDs + team resolution failures |
| Disabled/unknown keys | Skipped with explicit reason in import report |

No provider hard failures in the final import run (`provider_errors: []`).

---

## Remaining gaps before predictions can run

1. **UEFA historical results** — 162 finished fixtures still lack `fixture_results` (`NEED_RESULT_BACKFILL_FIX`: Sportmonks→API-Football ID map or Sportmonks score fetch path).
2. **Pipeline wiring** — `SUPPORTED_ECSE_COMPETITIONS`, schedulers, and WDE loaders still WC-scoped (out of EURO-A scope; required before enabling predictions).
3. **Odds for new upcoming UEFA fixtures** — limited odds snapshots exist for historical UEFA rows; upcoming odds import not in EURO-A scope (`NEED_ODDS_IMPORT` for later phase).
4. **Domestic upcoming feed** — PL/Bundesliga will need re-import when seasons resume.

---

## Files created or updated (EURO-A)

| Path | Role |
|------|------|
| `worldcup_predictor/config/euro_feed_registry.py` | Competition feed registry |
| `worldcup_predictor/data_import/european_fixture_feed.py` | Upcoming import + domestic verify |
| `worldcup_predictor/data_import/european_result_backfill.py` | UEFA result backfill |
| `scripts/import_european_fixtures.py` | Import CLI |
| `scripts/backfill_european_fixture_results.py` | Backfill CLI |
| `scripts/validate_euro_a_fixture_feed.py` | Validation CLI |
| `artifacts/euro_a_fixture_feed_summary.json` | Coverage artifact |
| `worldcup_predictor/database/repository.py` | Coverage/sync helpers (EURO-A) |

---

## Final recommendation

### `NEED_RESULT_BACKFILL_FIX`

**Rationale:** Upcoming European fixture feed infrastructure is operational and validated, but **74% of audited UEFA finished fixtures (162/220) still lack `fixture_results`**. Prediction and evaluation pipelines cannot rely on UEFA historical learning until legacy Sportmonks rows are remapped or scores are sourced from a compatible provider path. Do **not** enable European WDE/ECSE predictions until result backfill completes and pipeline wiring (post EURO-A) is done.

---

*EURO-A complete. No prediction generation. No public changes.*
