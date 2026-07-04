# NEXT-KNOCKOUT-FRESH-ODDS-1B — Controlled Production Report

**Phase:** NEXT-KNOCKOUT-FRESH-ODDS-1B  
**Host:** Hetzner `/opt/worldcup-predictor`  
**Run date:** 2026-07-04 (Europe/Vienna)  
**Final recommendation:** `PREDICTION_CREATED_WITH_ODDS_MISSING_WARNING`

Also: `DO_NOT_ENABLE_TIMERS`

---

## Part A — Production Confirmation

| Item | Value |
|------|-------|
| Commit | `9ca89f05ac9c0832fcb5fa858214888448cdc7a2` (= origin/main) |
| App version | A23.0.0 · hotfix-pack4 · **production** |
| worldcup-api | active |
| nginx | active |
| Env | `APP_ENV=production` → `.env.production` |

### Fixture confirmed

| Field | Value |
|-------|-------|
| fixture_id | **1567310** |
| Match | Colombia vs Ghana |
| Stage | Round of 32 |
| Kickoff | 2026-07-04 03:30 CEST |
| Pre-run odds | `ODDS_MISSING` |

---

## Part B — Odds Audit (Before Refresh)

```bash
.venv/bin/python scripts/run_odds_freshness_refresh.py \
  --mode audit --fixture-id 1567310 --dry-run --max-provider-calls 0 --source auto
```

| Field | Value |
|-------|-------|
| Freshness status | `ODDS_MISSING` |
| Odds source | — |
| odds_snapshot_at | — |
| odds_age_hours | — |
| Requires refresh | **Yes** |

---

## Part C — Odds Refresh Dry-Run

```bash
.venv/bin/python scripts/run_odds_freshness_refresh.py \
  --mode refresh --fixture-id 1567310 --dry-run --max-provider-calls 20 --source auto
```

| Field | Value |
|-------|-------|
| would_refresh | **Yes** |
| Provider | API-Football (auto) |
| Expected calls | ≤20 (bounded) |
| Quota risk | Low |
| Safe to proceed | **Yes** |

---

## Part D — Controlled Real Odds Refresh

### Bug fixed during run

`DailyProviderCallLog` missing `run_date` in `freshness_refresh.py` — patched and deployed before retry.

### Real refresh

```bash
.venv/bin/python scripts/run_odds_freshness_refresh.py \
  --mode refresh --fixture-id 1567310 --max-provider-calls 20 --source auto
```

| Metric | Value |
|--------|-------|
| refreshed (import batch) | 3 odds rows |
| Provider calls | **3** API-Football odds fetches (today's date window: 1567310, 1567824, 1569870) |
| Errors | 0 |

### Re-audit

| Field | Value |
|-------|-------|
| Freshness status | **`ODDS_FRESHNESS_UNKNOWN`** |
| odds_snapshot_at | `2026-07-04 00:55:59 UTC` |
| odds_source | `daily_owner_api-football_import` |
| requires_fresh_odds | **true** |
| would_refresh | false |

**Note:** Odds data exists (1X2, O/U, BTTS, correct score verified in ECSE odds audit), but timestamp format `"2026-07-04 00:55:59 UTC"` is not parsed by freshness policy → classified as unknown, **not** `FRESH_ODDS`.

---

## Part E — Prediction Dry-Run

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py \
  --mode predictions-only --fixture-id 1567310 \
  --refresh-stale-odds --max-odds-provider-calls 20 --dry-run --no-tomorrow
```

**Bug fixed:** Hetzner `predictions.py` missing `strict_fresh_odds` param — deployed.

| Field | Value |
|-------|-------|
| Fixtures targeted | **1** (1567310 only) |
| Would generate WDE | **Yes** |
| Would generate ECSE | **Yes** |
| Would store | Yes (dry-run, no write) |
| Provider calls planned | 0 (odds cached after refresh) |
| Odds in payload | has_odds=true, freshness unknown |
| Safe | **Yes** |

---

## Part F — Controlled Real Prediction

**Bug fixed:** `fixture_row` undefined in `run_daily_wde` — patched and deployed.

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py \
  --mode predictions-only --fixture-id 1567310 \
  --refresh-stale-odds --max-odds-provider-calls 20 --no-tomorrow
```

| Metric | Value |
|--------|-------|
| Fixtures discovered | 1 |
| WDE generated | **1** |
| ECSE generated | **1** |
| Stored predictions before → after | 48 → **49** |
| ECSE snapshots before → after | 0 → **1** (first production ECSE snapshot) |
| Errors | 0 |
| Additional provider calls | 0 (odds cache hit) |

---

## Part G — Stored Prediction Inspection

```bash
.venv/bin/python scripts/show_owner_predictions.py \
  --date 2026-07-04 --scope all --format markdown
```

### WDE (fixture 1567310)

| Check | Status |
|-------|--------|
| WDE 1X2 stored | ✅ Home win (1) |
| BTTS stored | ✅ No (71.2%) |
| O/U 2.5 stored | ✅ Under 2.5 (55.0%) |
| odds_freshness_status | `ODDS_FRESHNESS_UNKNOWN` |
| prediction_engine_version | `34b-v1` |
| cache_source | `live` |
| generated_at | `2026-07-04T00:58:13Z` |

### ECSE snapshot (id=1)

| Check | Status |
|-------|--------|
| ECSE Top3 | ✅ 2-0, 1-0, 3-0 |
| ECSE Top5 | ✅ 2-0, 1-0, 3-0, 4-0, 2-1 |
| Top1 end result | 2-0 |
| Model | ECSE-LIVE-1 · ECSE-1C-v1 · ECSE-1D-B-v1 |
| Frozen | yes |

---

## Part H — Owner Summary

Path: [`NEXT_KNOCKOUT_FRESH_ODDS_1B_COLOMBIA_GHANA_SUMMARY.md`](NEXT_KNOCKOUT_FRESH_ODDS_1B_COLOMBIA_GHANA_SUMMARY.md)

---

## Provider Calls Summary

| Step | API-Football calls |
|------|-------------------:|
| Odds refresh (Part D) | 3 (date-scoped batch) |
| Prediction run (Part F) | 0 |
| **Total** | **3** |

All calls logged in `logs/daily_provider_calls_20260704.jsonl`.

---

## Warnings

1. **Not FRESH_ODDS certified** — status is `ODDS_FRESHNESS_UNKNOWN`; do not claim fresh-odds prediction.
2. **Odds refresh fetched 3 fixtures** for today's date window, not only 1567310 — bounded but broader than single-fixture ideal.
3. **12 stale group-stage NS fixtures** remain unchanged (separate from this run).
4. **Do not enable timers.**
5. **Do not run eval** until match finishes.

---

## Code Fixes Deployed (Hetzner)

| File | Fix |
|------|-----|
| `worldcup_predictor/odds/freshness_refresh.py` | Added `run_date` to `DailyProviderCallLog` |
| `worldcup_predictor/owner_daily/predictions.py` | Added `strict_fresh_odds` support; fixed `fixture_row` lookup |
| `worldcup_predictor/odds/freshness_metadata.py` | Deployed for freshness stamping |

---

## Next Actions After Match Finishes

1. **results-only**
   ```bash
   export APP_ENV=production
   .venv/bin/python scripts/run_production_prediction_pipeline.py --mode results-only
   ```
2. **eval-only**
   ```bash
   .venv/bin/python scripts/run_production_prediction_pipeline.py --mode eval-only
   ```
3. **Evaluation report** — ECSE snapshot id=1 + WDE fixture 1567310

---

## Final Recommendation

### `PREDICTION_CREATED_WITH_ODDS_MISSING_WARNING`

Controlled WDE + ECSE production prediction created for Colombia vs Ghana (1567310). Odds were imported but **`odds_freshness_status ≠ FRESH_ODDS`** — freshness unknown due to snapshot timestamp format. First production ECSE snapshot stored.

**Do not enable timers.**

Follow-up fix (optional): normalize `odds_snapshots.snapshot_at` to ISO-8601 so knockout freshness policy can classify `FRESH_ODDS`.
