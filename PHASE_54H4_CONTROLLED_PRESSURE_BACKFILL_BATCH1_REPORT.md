# PHASE 54H-4 — Controlled Server Pressure Backfill Batch 1

**Date:** 2026-06-24  
**Mode:** Controlled Server Backfill → Coverage Audit → Validation → Report  
**Host:** `91.107.188.229` (`/opt/worldcup-predictor`)  
**Status:** Batch executed; validation PASS; coverage target **not met**

---

## 1. Pre-run state

| Check | Result |
|-------|--------|
| `DATABASE_URL` | Present, DB `worldcup_predictor` |
| `SPORTMONKS_API_TOKEN` | Present (length=60, not logged) |
| Pressure tables | **Missing initially** — migration `012_pressure_feature_store` applied before backfill |
| Pressure fixtures (server DB) | **0** (fresh tables; local dev DB had 65 from prior phases) |
| Cache directory | Writable at `data/feature_store/sportmonks_pressure/raw` |
| Pressure include probe | HTTP 200, pressure rows confirmed (54H-3 probe script) |

**Prerun validation:** 8/8 PASS (`artifacts/phase54h4_pressure_backfill_batch1/prerun_validation.json`)

**Infrastructure note:** Server Alembic was at `011_sportmonks_xg_feature_store`. Migration `012_sportmonks_pressure_feature_store.py` was deployed and `alembic upgrade head` created:

- `fs_sportmonks_pressure_records`
- `fs_sportmonks_pressure_fixture_summary`
- `fs_sportmonks_pressure_ingest_manifest`

No production predictions, WDE, SaaS, frontend, or EGIE scoring were modified.

---

## 2. Commands executed

All commands ran **server-side only** via `.venv/bin/python3` (system `python3` lacks `pydantic`).

```bash
# One-time schema (required — tables did not exist on server)
alembic upgrade head   # 011 → 012_pressure_feature_store

# Orchestrated batch
bash scripts/phase54h4_server_pressure_batch1.sh
```

**Batch 1A — World Cup (league 732):**

```bash
.venv/bin/python3 scripts/phase54h_pressure_feature_store_backfill.py \
  --league-id 732 --max-calls 30 --cache-first --skip-existing --save-raw \
  --job-key phase54h4_wc_batch1 --artifact-dir artifacts/phase54h4_pressure_backfill_batch1 \
  --max-pages 10
```

**Batch 1B — Champions League (league 2):** `phase54h4_cl_batch1` — same flags  
**Batch 1C — Europa League (league 5):** `phase54h4_el_batch1` — same flags  
**Batch 1D — Conference League (league 2286):** `phase54h4_conference_batch1` — same flags (ran because partial count &lt; 150)

**Target manifest build:**

```bash
.venv/bin/python3 scripts/build_phase54h4_target_fixtures.py
```

**Post-run:**

```bash
.venv/bin/python3 scripts/audit_phase54h4_pressure_backfill_coverage.py
.venv/bin/python3 scripts/validate_phase54h4_pressure_backfill_batch1.py
```

---

## 3. API calls used

| Batch | Live API calls | Cache hits | Fixtures imported |
|-------|----------------|------------|-------------------|
| `phase54h4_wc_batch1` | 30 | 0 | 30 |
| `phase54h4_cl_batch1` | 0 | 0 | 0 |
| `phase54h4_el_batch1` | 0 | 0 | 0 |
| `phase54h4_conference_batch1` | 0 | 0 | 0 |
| **Total** | **30** | **0** | **30** |

- **max-calls budget:** 120 possible (4 × 30); **30 used** — well within limit.
- **Quota risk:** LOW (30 live calls).
- Discovery paging for CL/EL/Conference consumed league/season resolution calls but did not count toward ingest `max-calls`.

---

## 4. New pressure fixtures

| Metric | Value |
|--------|-------|
| Fixtures before (server) | 0 |
| Fixtures after (server) | **30** |
| New fixtures imported | **30** |
| Target minimum | 150 |
| Target met | **No** (30 / 150 = 20%) |

All 30 new fixtures are **World Cup 2026** (league `732`, season `26618`).

---

## 5. New pressure rows

| Metric | Value |
|--------|-------|
| Pressure records inserted | **6,134** |
| Fixture summaries | **30** |
| Avg rows per fixture | **204.5** |
| Fixtures with 0 pressure rows | **0** |
| Duplicate groups | **0** |

Raw cache files saved: **30** (`data/feature_store/sportmonks_pressure/raw/*.json`)

---

## 6. Coverage before / after

| | Before | After | Delta |
|---|--------|-------|-------|
| Pressure fixtures | 0 | 30 | +30 |
| Pressure records | 0 | 6,134 | +6,134 |
| Leagues with pressure | 0 | 1 | +1 (732) |
| Seasons with pressure | 0 | 1 | +1 (26618) |

**Context:** Prior phases reported 65 fixtures on the **local** PostgreSQL instance. Server production DB had no pressure schema until this run; counts are not directly comparable without a cache/DB sync step.

---

## 7. League / season breakdown

**By league (after):**

| League ID | Competition | Fixtures |
|-----------|-------------|----------|
| 732 | FIFA World Cup | 30 |
| 2 | Champions League | 0 |
| 5 | Europa League | 0 |
| 2286 | Conference League | 0 |

**By season (after):**

| Season ID | Fixtures |
|-----------|----------|
| 26618 | 30 |

---

## 8. Zero-row fixtures analysis

- **Imported fixtures with 0 pressure rows:** 0
- **Empty API responses on recent WC fixtures:** None observed in batch 1A
- **Legacy zero-pressure IDs (54H-3):** Excluded from target manifest (`1058477`, `1059951`, `18151405`, etc.)

**UEFA batches — root cause (not zero-row, but zero ingest):**

| Batch | Manifest skip reason | Count |
|-------|---------------------|-------|
| `phase54h4_cl_batch1` | `skipped_upcoming` | 56 |
| `phase54h4_el_batch1` | `skipped_upcoming` | 30 |
| `phase54h4_conference_batch1` | `skipped_upcoming` | 138 |
| `phase54h4_wc_batch1` | `skipped_upcoming` | 56 (remaining WC schedule) |

Discovery returned mostly **upcoming** fixtures for UEFA current seasons (`finished_only=True`). No live ingest calls were made for those leagues because no completed fixtures passed the filter.

---

## 9. Quota status

| Item | Status |
|------|--------|
| Live calls this batch | 30 |
| Estimated budget for 100 fixtures | ~90 (54H-3 estimate) |
| Quota warning | None observed |
| HTTP 401/403 | None |
| DB insert failures | None |

---

## 10. Validation result

**13/13 PASS** (`artifacts/phase54h4_pressure_backfill_batch1/validation.json`)

| Check | Result |
|-------|--------|
| Prerun completed | PASS |
| Server token worked | PASS |
| Backfill ran (4 batches) | PASS |
| Pressure records increased | PASS (+30 fixtures) |
| Duplicate groups = 0 | PASS |
| Raw cache saved | PASS (30 files) |
| Manifest saved | PASS |
| max-calls respected | PASS (30 ≤ 130 ceiling) |
| No production / WDE / SaaS / deploy changes | PASS |
| No token leaked in artifacts | PASS |

---

## 11. Final recommendation

### **`NEED_MORE_PRESSURE_BACKFILL`**

Pressure API access on the server is **healthy** (WC batch: 30/30 imports, ~204 rows/fixture, 0 empty). Coverage target **≥150 fixtures was not met** (30 fixtures after run).

### Exact blockers

1. **Server DB was empty** — pressure tables did not exist until migration 012; no prior local→server sync.
2. **WC batch hit `max-calls=30`** before exhausting finished fixtures; ~74 additional WC fixtures remain `skipped_upcoming` in discovery order.
3. **UEFA leagues (2, 5, 2286)** — current-season discovery returned only upcoming fixtures; `finished_only` filter blocked all ingest (0 API calls).
4. **Local token still invalid** — expansion must remain server-only.

### Suggested next batch (not executed — STOP per phase scope)

1. **WC batch 2+:** Re-run league 732 with `--job-key phase54h4_wc_batch2` and `--max-calls 30` until finished WC pool exhausted (~40+ more finished games expected as tournament progresses).
2. **UEFA prior season:** Discover finished fixtures from **2024/25** seasons (or explicit `season_id`) for leagues 2, 5, 2286 with `fixture_id >= 19_000_000` filter.
3. **Optional DB seed:** Bulk-import the **65-fixture local pressure cache** into server PostgreSQL to jump-start coverage without additional API quota.
4. **Manifest-driven ingest:** Use `target_fixtures.json` + `--manifest` for deterministic fixture lists.

### Not recommended yet

- **`READY_FOR_PRESSURE_BACKTEST_RERUN`** — requires ≥150 pressure fixtures (currently 30).
- **`PRESSURE_ACCESS_INCONSISTENT`** — WC data quality is consistent; UEFA issue is fixture state, not API failure.
- **`TOKEN_OR_DB_FIX_REQUIRED`** — server token and DB are operational after migration 012.

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/phase54h4_pressure_backfill_batch1/prerun_validation.json` | Pre-run checks |
| `artifacts/phase54h4_pressure_backfill_batch1/target_fixtures.json` | 40 candidate WC fixtures |
| `artifacts/phase54h4_pressure_backfill_batch1/backfill_phase54h4_*.json` | Per-batch results |
| `artifacts/phase54h4_pressure_backfill_batch1/coverage_audit.json` | Post-run coverage |
| `artifacts/phase54h4_pressure_backfill_batch1/validation.json` | Gate validation |
| `data/feature_store/sportmonks_pressure/raw/` (server) | 30 raw API payloads |

---

**Phase 54H-4 complete. No deploy. No live prediction changes. No modeling started.**
