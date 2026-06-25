# PHASE 54C-1 — Premier League Odds Backfill Report

**Mode:** Implement → Validate → Report  
**Status:** Implementation complete — **coverage target not met (API data gap)**  
**Deploy:** Not performed (awaiting approval)

---

## Executive summary

Phase 54C-1 delivered a dedicated, resumable, odds-only backfill pipeline per `PHASE_54C1_PL_ODDS_BACKFILL_PLAN.md`. The job scanned **380** finished PL fixtures, consumed **380** live API-Football calls, and wrote **0** `odds_snapshots` rows because **API-Football returned `results: 0` for every historical PL fixture**.

| Metric | Before | After | Target |
|--------|--------|-------|--------|
| PL-aligned `odds_snapshots` | 0 / 380 | **0 / 380** | ≥ 350 / 380 |
| EGIE `coverage_pct.odds` | 0.0% | **0.0%** | > 50% |
| Goal Timing `has_reliable_goal_odds` (n=50) | 0% | **0%** | > 50% |
| World Cup `odds_snapshots` preserved | 527 orphan rows | **527** (unchanged) | Unchanged |

**Root cause (post-implementation):** API-Football `GET /odds?fixture={id}` does not retain bookmaker payloads for **finished** Premier League 2023 fixtures. Upcoming World Cup 2026 fixtures on the same API key **do** return odds (`results: 1`), confirming the key and client work; the gap is **historical odds availability**, not implementation logic.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/egie/backfill/api_football_provider_backfill.py` | Added `run_pl_odds_backfill()` odds-only path; extended `_pl_fixture_targets()` with optional `league_id` / `season` filters; cache fallback; dual `bookmakers` + `api_sports` payload; JSONL manifest support |
| `scripts/phase54c1_pl_odds_backfill.py` | **New** — dedicated CLI, artifact + utilization before/after |
| `scripts/validate_phase54c1_pl_odds_backfill.py` | **New** — 11-check validation suite |

**Not modified (per constraints):** WDE, SaaS predict path, EGIE scoring/enrichment math, Goal Timing agent math, schema/migrations, Sportmonks guard, Stripe, frontend.

---

## Execution summary

| Item | Value |
|------|-------|
| Command | `python scripts/phase54c1_pl_odds_backfill.py --league-id 39 --max-api-calls 400 --limit-fixtures 380` |
| Started | 2026-06-23T18:10:54Z |
| Finished | 2026-06-23T18:17:17Z |
| Duration | ~6.4 minutes |
| Fixtures scanned | 380 |
| API calls (live) | 380 |
| API calls (cache) | 0 |
| Snapshots created | 0 |
| Snapshots empty (API `results: 0`) | 380 |
| Snapshots error | 0 |
| Skipped (existing) | 0 |
| Skipped (cap) | 0 |

### Artifacts

| Path | Purpose |
|------|---------|
| `artifacts/phase54c1_pl_odds_backfill_result.json` | Full run payload + utilization before/after |
| `data/shadow/phase54c1_pl_odds_backfill_manifest.jsonl` | Per-fixture status (380 × `empty`) |
| `artifacts/phase54c1_pl_odds_validation.json` | Validation check results |

---

## API investigation

Raw API probe (Pro plan, active subscription):

```
GET /odds?fixture=1035037  →  HTTP 200, errors=[], results=0, response=[]
GET /odds?fixture=1489369  →  HTTP 200, errors=[], results=0, response=[]  (WC, previously had odds in DB)
GET /odds?fixture=1489402  →  HTTP 200, results=1, response=[{bookmakers:…}]  (upcoming WC 2026)
```

| Endpoint tried | PL historical result |
|----------------|---------------------|
| `odds?fixture={pl_id}` | Empty |
| `odds?fixture={id}&bookmaker=8` | Empty |
| `odds?league=39&season=2023&date=2023-08-11` | Empty |
| `odds/live?fixture={pl_id}` | Empty |

**Conclusion:** Backfill logic is correct; **API-Football does not expose historical closing odds** for the finished PL cohort in SQLite. Non-empty odds exist only in `api_response_cache` for **non-PL** fixture ids (WC / demo pool) — re-keying those rows was explicitly forbidden.

---

## Coverage metrics

### PL `odds_snapshots`

| Metric | Before | After |
|--------|--------|-------|
| Distinct PL fixtures with snapshots | 0 | 0 |
| Total PL snapshot rows | 0 | 0 |

### Parseable 1X2 (EGIE store)

| Metric | Value |
|--------|-------|
| Fixtures tested | 380 |
| `coverage["odds"]` + `odds_implied_home` | **0** (0.0%) |

### EGIE utilization audit

| Field | Before | After |
|-------|--------|-------|
| `coverage_pct.odds` | 0.0% | 0.0% |
| `coverage_count.odds` | 0 | 0 |

### Goal Timing

| Field | Before | After |
|-------|--------|-------|
| `has_reliable_goal_odds` (sample 50) | 0 / 50 | 0 / 50 |

### Safety checks

| Check | Result |
|-------|--------|
| World Cup contamination in PL rows | **PASS** — 0 WC ids under `competition_key='premier_league'` |
| WC orphan rows preserved | **PASS** — 527 rows intact |
| Duplicate snapshot explosion | **PASS** — 0 fixtures with >3 snapshots |

---

## Validation results

```
VALIDATION: 5/11 PASS
  [PASS] fixtures_scanned
  [PASS] api_calls_documented
  [FAIL] odds_snapshots_inserted
  [FAIL] parseable_1x2_odds
  [FAIL] pl_coverage_after
  [FAIL] egie_odds_coverage_after
  [FAIL] goal_timing_has_reliable_goal_odds
  [FAIL] has_reliable_goal_odds_status
  [PASS] no_world_cup_contamination
  [PASS] no_duplicate_snapshot_explosion
  [PASS] world_cup_rows_preserved
```

Run: `python scripts/validate_phase54c1_pl_odds_backfill.py`

---

## Rollback procedure

No PL backfill rows were inserted. **Rollback is a no-op** for `odds_snapshots`. Optional: clear polluted empty odds cache entries if re-run should force fresh live calls (already handled by empty-cache retry in `run_pl_odds_backfill`).

### Pre-run backup (recommended for any re-run)

```bash
cp data/football_intelligence.db data/football_intelligence.db.pre_phase54c1
```

### Surgical rollback (if snapshots are created in a future run)

```sql
DELETE FROM odds_snapshots
WHERE competition_key = 'premier_league'
  AND fixture_id IN (
    SELECT fixture_id FROM fixtures
    WHERE competition_key = 'premier_league' AND is_placeholder = 0
  )
  AND (
    json_extract(payload_json, '$.source') = 'api_football_live_backfill'
    OR json_extract(payload_json, '$.source') = 'api_f_pl_cache_backfill'
  );
```

### Full restore

```bash
cp data/football_intelligence.db.pre_phase54c1 data/football_intelligence.db
```

World Cup rows (`fixture_id` 1489369+, 900001+) are **not** affected by the surgical delete.

---

## Risks

| Risk | Status |
|------|--------|
| Production predict / WDE changed | **None** — no production files touched |
| WC data corruption | **None** — no WC rows written or re-keyed |
| Quota exhaustion | **Occurred** — 380 calls consumed; within 400 budget |
| Empty cache pollution | **Low** — empty responses cached; retry logic forces live when cache is empty |
| False confidence from implementation | **Mitigated** — validation explicitly failed coverage gates |

---

## Secondary finding (parser — Phase 54C-2 scope)

Even WC `odds_snapshots` with rich `api_sports.bookmakers` JSON return `coverage["odds"]=False` today because `parse_odds_snapshots()` delegates to `extract_api_sports_probs()`, which expects a report object with `.odds.bookmakers`, not a raw snapshot dict. **Fixing this is Phase 54C-2 (parser expansion)** and was out of scope for 54C-1 per constraints.

---

## Expected impact (deferred)

Until historical odds are ingested **and** parsers read snapshot payloads:

| System | Expected 54C-1 impact | Actual |
|--------|----------------------|--------|
| EGIE strategies D / E / F | Odds arm unlocks | **No change** |
| Goal Timing odds agent | `has_reliable_goal_odds` true | **No change** |
| WDE / SaaS | None | **None** |

---

## Recommendation for Phase 54C-2

1. **Parser repair (high priority, low risk):** Update `parse_odds_snapshots()` / snapshot reader to accept `bookmakers` and `api_sports.bookmakers` from `odds_snapshots.payload_json` without changing EGIE scoring weights.
2. **Historical odds source (required for PL cohort):** API-Football live `/odds` alone cannot backfill finished PL 2023. Options:
   - **Capture at predict-time** — persist odds via `OddsSnapshotService` when running PL predictions before kickoff.
   - **OddAlerts `odds/history`** — audit showed pool fixtures only; verify PL mapping.
   - **The Odds API** — historical archive if league/season coverage exists.
   - **Third-party CSV import** — one-time ingest into `odds_snapshots` with `source` tag (no WC re-key).
3. **Re-run 54C-1 script** after a viable source is wired — `run_pl_odds_backfill()` is resumable via `_has_pl_odds()` and manifest JSONL.

---

## How to re-run

```bash
# Odds-only backfill (default budget 400)
python scripts/phase54c1_pl_odds_backfill.py --league-id 39 --max-api-calls 400 --limit-fixtures 380

# Validate
python scripts/validate_phase54c1_pl_odds_backfill.py
```

**Note:** Do not pass `--season 2026` for the current SQLite cohort — fixtures are `season=2023`. Omit `--season` to scan all finished PL fixtures.

---

**STOP — Implementation and validation complete. No deploy. Await approval for Phase 54C-2.**
