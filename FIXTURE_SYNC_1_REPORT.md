# FIXTURE-SYNC-1 — Production WC Fixture Schedule Repair Report

**Phase:** FIXTURE-SYNC-1  
**Host:** Hetzner `91.107.188.229` — `/opt/worldcup-predictor`  
**Run date:** 2026-07-04 (Europe/Vienna)  
**Final recommendation:** `FIXTURE_SYNC_REPAIRED_READY_FOR_FRESH_ODDS_PREDICTION`

Also: `DO_NOT_ENABLE_TIMERS`

---

## Summary

Production WC fixture discovery was broken (0 future fixtures). After a controlled API-Football sync using production credentials (`.env.production` via `APP_ENV=production`), **7 upcoming knockout fixtures** were imported. The next knockout match is now discoverable.

**12 stale group-stage NS fixtures remain** — results-only pipeline synced 0 rows (no ECSE snapshots), and API-Football still returns `NS` for those fixture IDs (no fake results created).

---

## Part A — Fixture Audit (Before)

| Metric | Before |
|--------|-------:|
| FT | 317 |
| NS | 12 |
| Past kickoff + NS | 12 |
| Future kickoff (any status) | **0** |
| Upcoming fixtures listed | 0 |

Artifact: `FIXTURE_SYNC_1_AUDIT.md` (before snapshot: `artifacts/fixture_sync/fixture_sync_1_audit_before.json`)

---

## Part B — Results-Only Repair (Stale NS)

### Dry-run

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode results-only --dry-run
```

- `result_synced`: **0**
- Provider calls: **0**

### Controlled run

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode results-only
```

- `result_synced`: **0** (expected — 0 ECSE snapshots; sync targets snapshot fixtures only)
- WDE evaluated: 0
- No fake results created

### Stale NS re-audit

| Metric | After Part B |
|--------|-------------:|
| Stale NS (past kickoff) | **12** (unchanged) |

**Part B outcome:** `RESULTS_SYNC_NO_UPDATE` for stale NS fixtures.

Provider-backed repair dry-run (12 API calls) also returned provider status `NS` for all 12 — cannot safely mark FT without provider confirmation.

---

## Part C — Upcoming WC Fixture Sync

**Important:** CLI scripts must load `.env.production` on Hetzner (`APP_ENV=production` or auto-detect added to audit/sync scripts).

### Dry-run (production env)

```bash
export APP_ENV=production
.venv/bin/python scripts/sync_wc_upcoming_fixtures.py \
  --competition wc --from-date today --dry-run --max-provider-calls 20 --source api_football
```

- API-Football fetched: **7** upcoming fixtures
- Provider calls: **1** (bounded)

### Controlled write

```bash
export APP_ENV=production
.venv/bin/python scripts/sync_wc_upcoming_fixtures.py \
  --competition wc --from-date today --write --max-provider-calls 20 --source api_football
```

| Metric | Value |
|--------|------:|
| Provider calls (upcoming sync) | **1** (`api_football`) |
| Fixtures imported/synced | **7** |
| Duplicates avoided | 0 |
| Future fixtures before → after | 0 → **7** |

Sportmonks skipped (`sportmonks_league_id not configured in registry`) — API-Football alone was sufficient.

---

## Part A — Fixture Audit (After)

| Metric | Before → After |
|--------|----------------|
| NS | 12 → **19** (+7 upcoming) |
| FT | 317 → **317** (unchanged) |
| Past kickoff + NS | 12 → **12** |
| Future kickoff + NS | 0 → **7** |
| Future kickoff (any) | 0 → **7** |
| Duplicate suspects | 0 → **0** |
| Finished missing result | 0 → **0** |

---

## Part D — Fixture Discovery Validation

```bash
export APP_ENV=production
.venv/bin/python scripts/find_next_knockout_fixture.py \
  --competition wc --from-date today --format markdown --limit 10
```

**Next knockout fixture found:**

| Field | Value |
|-------|-------|
| fixture_id | **1567310** |
| Match | Colombia vs Ghana |
| Stage | Round of 32 |
| Kickoff (Vienna) | 2026-07-04 03:30 CEST |
| Status | NS |
| WDE stored | no |
| ECSE snapshot | no |
| Odds | ODDS_MISSING |

Additional upcoming knockouts synced: Round of 16 fixtures on 2026-07-04 through 2026-07-07.

---

## Part E — Safety Validation

```bash
.venv/bin/python scripts/validate_fixture_sync_1.py
```

**Result:** **23/23 checks passed**

Validated:

- No local DB import / no DB overwrite pattern
- Future fixtures have future `kickoff_utc`
- No duplicate fixture groups
- Provider calls bounded and logged
- FT count not corrupted (317 preserved)
- WDE/ECSE code paths unchanged
- Timers not enabled
- `worldcup-api` and `nginx` active

Artifact: `artifacts/fixture_sync/fixture_sync_1_validation.json`

---

## Provider Calls Summary

| Step | Calls |
|------|------:|
| Results-only pipeline | 0 |
| Stale NS repair (dry-run probe) | 12 |
| Upcoming sync (write) | **1** |
| **Total persisted sync calls** | **1** |

---

## Warnings

1. **12 stale group-stage NS fixtures** remain — provider also reports `NS`; do not fake FT.
2. **CLI must use production env** on Hetzner — use `APP_ENV=production` or updated audit/sync scripts with auto-detect.
3. **New knockout fixtures have no odds yet** — fresh-odds workflow must refresh before prediction.
4. **Do not enable timers** — controlled manual runs only.

---

## NEXT-KNOCKOUT-FRESH-ODDS-1 — Ready to Retry

**Yes.** Discovery now returns knockout fixture `1567310`.

### Exact next commands (dry-run first)

```bash
cd /opt/worldcup-predictor
export APP_ENV=production

# Odds audit
.venv/bin/python scripts/run_odds_freshness_refresh.py \
  --mode audit --fixture-id 1567310 --dry-run --max-provider-calls 0

# Prediction dry-run
.venv/bin/python scripts/run_production_prediction_pipeline.py \
  --mode predictions-only --fixture-id 1567310 \
  --refresh-stale-odds --max-odds-provider-calls 20 --dry-run
```

Then proceed with controlled real odds refresh + prediction per NEXT-KNOCKOUT-FRESH-ODDS-1.

---

## Artifacts

| File | Purpose |
|------|---------|
| `FIXTURE_SYNC_1_AUDIT.md` | Latest schedule audit |
| `FIXTURE_SYNC_1_REPORT.md` | This report |
| `artifacts/fixture_sync/fixture_sync_1_audit_before.json` | Pre-sync audit |
| `artifacts/fixture_sync/fixture_sync_1_audit.json` | Post-sync audit |
| `artifacts/fixture_sync/fixture_sync_1_sync_latest.json` | Sync run details |
| `artifacts/fixture_sync/fixture_sync_1_validation.json` | Safety validation |

---

## Final Recommendation

### `FIXTURE_SYNC_REPAIRED_READY_FOR_FRESH_ODDS_PREDICTION`

Upcoming WC knockout fixtures are now in production DB and discoverable. Stale historical NS rows remain but were not faked. Retry controlled fresh-odds prediction for fixture **1567310**.

**Do not enable timers.**
