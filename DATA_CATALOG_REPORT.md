# PHASE DATA-0B — Historical Data Catalog & Safe Attach Plan

**Date:** 2026-06-27  
**Mode:** Read-only audit — no API calls, no migrations, no deploy, no deletes, no production logic changes  
**Project root (local):** `C:\Users\kaman\Desktop\Footbal`  
**Production root (VPS):** `/opt/worldcup-predictor`

---

## 1. Executive summary

Historical football data **already exists locally** (~**7.1 GB** across JSON dumps, SQLite, parquet, CSV, and JSONL). The codebase is **already wired** to read several of these paths at runtime (feature stores, EGIE raw cache, SportMonks dumps). Nothing was moved, deleted, or overwritten during this phase.

| Finding | Detail |
|---------|--------|
| `data/imports/` | **Does not exist** locally or in repo. Production path `/opt/worldcup-predictor/data/imports` is **not yet provisioned**. |
| Canonical data root | `data/` (17 subfolders) + `.cache/` + `artifacts/` (derived datasets) |
| Primary DB | `data/football_intelligence.db` (470 MB, 74 tables) |
| Largest archives | SportMonks dump (3.9 GB), xG feature store (1.3 GB), UEFA EGIE raw JSON (~307 MB combined) |
| Attach strategy | Register existing paths in catalog → symlink/index under `data/imports/` (future, non-destructive) → offline backfill scripts read caches only |

---

## 2. Scan scope & methodology

- Enumerated `data/**`, `.cache/**`, `artifacts/**` (football-related subsets)
- Counted files, sizes, row/line counts where cheap (sqlite3, line counts, pyarrow for parquet)
- Mapped each store to **provider** and **existing Python consumer** (read-only reference)
- Verified: **`data/imports` absent** — grep across repo returns zero references

**Not scanned:** Full `C:\` drive (permission limits). Desktop DB duplicates noted separately.

---

## 3. `data/imports` status

| Location | Exists? | Notes |
|----------|---------|-------|
| `/opt/worldcup-predictor/data/imports` | **No** (expected VPS staging path) | Recommended future **read-only index** — symlinks to canonical stores, not copies |
| `data/imports/` (local) | **No** | Same — create in DATA-0C without moving source files |

**Design intent for DATA-0C (not executed here):**

```
data/imports/
  catalog.json              # machine-readable manifest (this report → JSON)
  sportmonks_dump/          → symlink ../sportmonks_dump
  sportmonks_xg/            → symlink ../feature_store/sportmonks_xg/raw
  api_football_wc/          → symlink ../egie/world_cup/raw/api_football
  uefa_club_raw/            → symlink ../egie/uefa_club/raw
  shadow/                   → symlink ../shadow
  README.md                 # human index
```

---

## 4. Data catalog by domain

### 4.1 SQLite — primary intelligence database

| Path | Size | Rows (key tables) | Provider | Modified |
|------|------|-------------------|----------|----------|
| `data/football_intelligence.db` | 470.4 MB | fixtures **2,161** · fixture_results **1,929** · fixture_goal_events **6,198** · odds_snapshots **1,443** · fixture_enrichment **1,684** · api_response_cache **2,410** · teams **393** · sportmonks_fixture_enrichment **28** · xg_snapshots **0** · predictions **17** | Multi-provider (API-Football, SportMonks, Odds API, OddAlerts) | 2026-06-27 |
| `C:\Users\kaman\Desktop\football_intelligence.db` | 470.4 MB | Identical copy | Same | 2026-06-27 |
| `C:\Users\kaman\Desktop\football_intelligence_backup.db` | 470.4 MB | Identical copy | Same | 2026-06-27 |

**Consumer modules (read):** `worldcup_predictor/database/repository.py`, prediction pipeline, backtesting, lifecycle stores.  
**Attach note:** DB is live production store — attach = ensure path in `SQLITE_PATH`; do **not** re-import over it.

#### Phase validation DBs (test-only, small)

| Path | Size | ~Rows | Purpose |
|------|------|-------|---------|
| `artifacts/phase44a_validation.db` | 320 KB | 9 | WC prediction validation |
| `artifacts/phase45b_validation.db` | 320 KB | 10 | WC prediction validation |
| `artifacts/phase46b_validation.db` | 320 KB | 11 | Predictions/markets test |
| `artifacts/phase46c1_validation.db` | 350 KB | 8 | Goal events test |
| `artifacts/phase46c2_validation.db` | 350 KB | 3 | Evaluations test |
| `artifacts/phase46c3_validation.db` | 350 KB | 3 | Evaluations test |
| `artifacts/phase46d_validation.db` | 360 KB | 5 | Unified events test |
| `data/shadow/_phase30e_test.db` | 260 KB | 12 | Shadow test |

---

### 4.2 SportMonks — full fixture dumps (JSON)

**Path:** `data/sportmonks_dump/`  
**Total:** 1,930 files · **3,947 MB** · modified 2026-06-27  
**Source script:** `scripts/sportmonks_full_dump.py`  
**Includes per fixture:** `odds;lineups;statistics;scores;participants;events`

| League / season | Files | ~Size |
|-----------------|-------|-------|
| conference_league / 2024_2025 | 410 | 748 MB |
| conference_league / 2025_2026 | 410 | 748 MB |
| europa_league / 2024_2025 | 270 | 617 MB |
| europa_league / 2025_2026 | 272 | 618 MB |
| champions_league / 2024_2025 | 51 | 136 MB |
| champions_league / 2025_2026 | 282 | 616 MB |
| world_cup / 2018 | 65 | 145 MB |
| world_cup / 2022 | 65 | 145 MB |
| world_cup / 2026 | 105 | 235 MB |

**Consumer modules:** `scripts/sportmonks_odds_import.py`, `scripts/sportmonks_wc2026_odds_import.py`, EGIE backfill scripts.

**Secondary dump:** `data/sportmonks_full_dump/world_cup/` — 104 files · 291 MB (WC-focused subset).

---

### 4.3 SportMonks xG feature store (JSON)

**Path:** `data/feature_store/sportmonks_xg/raw/`  
**Total:** 1,554 files · **1,294 MB** · modified 2026-06-23  
**Format:** `{sportmonks_fixture_id}.json` — raw xG match payloads  
**Consumer:** `worldcup_predictor/feature_store/sportmonks_xg_store.py` (`_CACHE_SUBDIR`)

| Metric | Value |
|--------|-------|
| File type | `.json` |
| Row equivalent | 1,554 fixtures |
| DB mirror | `xg_snapshots` table currently **empty** — JSON cache is ahead of SQLite |

---

### 4.4 SportMonks pressure (derived + cache)

**Configured cache path:** `data/feature_store/sportmonks_pressure/raw/` (may be empty — pressure store also reads fallbacks)

**Fallback read paths in code** (`sportmonks_pressure_store.py`):

- `data/egie/uefa_club/raw/{id}.json`
- `data/data/egie/uefa_club/raw/{id}.json`
- `data/feature_store/sportmonks_xg/raw/{id}.json`

**Derived parquet (artifacts):**

| Path | Rows | Cols | Modified |
|------|------|------|----------|
| `artifacts/phase54h1_pressure_shadow_backtest/pressure_inplay_dataset.parquet` | 177 | 33 | 2026-06-24 |
| `artifacts/phase54h1_pressure_shadow_backtest/pressure_prematch_dataset.parquet` | 65 | 39 | 2026-06-24 |
| `artifacts/phase54h2_pressure_expansion_proxy_audit/pressure_inplay_dataset.parquet` | 177 | 41 | 2026-06-24 |
| `artifacts/phase54h2_pressure_expansion_proxy_audit/pressure_prematch_dataset.parquet` | 65 | 39 | 2026-06-24 |

**Manifests:** `artifacts/phase54g_pressure_discovery/api_manifest.jsonl` (23 lines)

---

### 4.5 API-Football — raw & cache

#### EGIE World Cup raw (`data/egie/world_cup/raw/api_football/`)

| Resource | Files | Size | Provider |
|----------|-------|------|----------|
| `events/` | 50 | 289 KB | API-Football |
| `lineups/` | 50 | 446 KB | API-Football |
| `fixture_statistics/` | 50 | 141 KB | API-Football |
| `injuries/` | 50 | 44 KB | API-Football |

**Total:** 200 JSON files · ~919 KB · 50 WC fixtures covered  
**Consumer:** `worldcup_predictor/egie/world_cup/raw_cache.py`, `config.RAW_CACHE_DIR`

#### Live response cache (`.cache/api_football/`)

| Subfolder | Files | ~Size | Content |
|-----------|-------|-------|---------|
| `lineups/` | 1,696 | 10.4 MB | Cached lineup API responses |
| `sportmonks/` | 414 | 4.3 MB | Cross-provider bridge cache |
| `sportmonks/xg_match/` | 7 | 1.2 MB | xG match cache |
| `weather/` | 19 | <1 MB | Weather cache |
| **Total tree** | **10,563** | **~165 MB** | Mixed API-Football responses |

**Consumer:** API clients + enrichment pipeline (cache-first reads).

#### Historical importer (API live — not used in DATA-0B)

`worldcup_predictor/data_import/api_football_historical_importer.py` — exports to CSV shape; **not invoked** in this phase.

---

### 4.6 EGIE derived datasets

| Path | Type | Rows | Provider / notes | Modified |
|------|------|------|------------------|----------|
| `data/egie/world_cup/survival_dataset.parquet` | parquet | 317 | EGIE WC survival | 2026-06-26 |
| `data/egie/survival/survival_dataset.parquet` | parquet | 380 | EGIE survival | 2026-06-22 |
| `data/egie/uefa_club/uefa_survival_dataset.parquet` | parquet | 220 | EGIE UEFA | 2026-06-23 |
| `data/egie/world_cup/raw/goal_timing_features/` | json | 329 files | Derived timing features | — |
| `data/egie/world_cup/raw/goal_timing_features_enriched/` | json | 329 files | Enriched timing | — |
| `data/egie/confidence/hybrid_shadow_predictions.jsonl` | jsonl | 349 lines | Shadow | 2026-06-22 |
| `data/egie/survival/survival_shadow_predictions.jsonl` | jsonl | 359 lines | Shadow | 2026-06-22 |

#### UEFA club raw JSON (SportMonks full payloads — includes pressure, xG, odds, events, lineups)

| Path | Files | Size | Notes |
|------|-------|------|-------|
| `data/egie/uefa_club/raw/` | 81 | 210.6 MB | **Canonical** per `uefa_club/config.py` |
| `data/data/egie/uefa_club/raw/` | 105 | 97.9 MB | **Legacy duplicate tree** — overlap with canonical; dedupe before attach |

**Consumer:** `worldcup_predictor/egie/uefa_club/sportmonks_ingest.py`, pressure store fallbacks.

---

### 4.7 Odds datasets

| Path | Type | Rows/lines | Source |
|------|------|------------|--------|
| `data/football_intelligence.db` → `odds_snapshots` | sqlite | 1,443 | The Odds API / ingested |
| `data/football_intelligence.db` → `oddalerts_odds_history` | sqlite | (see DB) | OddAlerts |
| `data/sportmonks_dump/**/*.json` | json | embedded in 1,930 fixtures | SportMonks odds include |
| `artifacts/phase54m_goalscorer_odds_mapping/*.csv` | csv | 703 raw · 270 mapped · 433 unmapped | Goalscorer odds bridge |
| `data/shadow/phase54c1_pl_odds_backfill_manifest.jsonl` | jsonl | 380 lines | PL odds backfill manifest |
| `data/shadow/phase16_odds_primary_replay.jsonl` | jsonl | 28 lines | Odds replay |

---

### 4.8 Events & goal timing

| Path | Type | Count | Source |
|------|------|-------|--------|
| `data/football_intelligence.db` → `fixture_goal_events` | sqlite | 6,198 | API-Football / unified ingest |
| `data/sportmonks_dump/**/*.json` | json | events in dump includes | SportMonks |
| `data/egie/world_cup/raw/api_football/events/` | json | 50 files | API-Football |
| `artifacts/phase60c_goal_event_backfill/backfill_candidates.csv` | csv | 881 rows | Backfill research |
| `artifacts/phase60b_first_goal_timing_distribution/first_goal_timing_rows.csv` | csv | 1,813 rows | Goal timing model |

---

### 4.9 Lineups & injuries

| Path | Type | Count | Source |
|------|------|-------|--------|
| `.cache/api_football/lineups/` | json cache | 1,696 files | API-Football |
| `data/egie/world_cup/raw/api_football/lineups/` | json | 50 files | API-Football |
| `data/egie/world_cup/raw/api_football/injuries/` | json | 50 files | API-Football |
| `data/sportmonks_dump/**/*.json` | json | lineups in dump includes | SportMonks |
| `data/shadow/expected_lineup_accuracy.jsonl` | jsonl | 2,658 lines | Lineup accuracy shadow |
| `data/shadow/expected_lineup_promotion_shadow.jsonl` | jsonl | 14,000 lines | Lineup promotion shadow |

---

### 4.10 Shadow / replay archives (internal)

**Path:** `data/shadow/` — 47 files · **60.8 MB**

| File | Lines | Domain |
|------|-------|--------|
| `lambda_bridge_shadow.jsonl` | 13,878 | Lambda bridge |
| `tournament_context_promotion_shadow.jsonl` | 14,006 | Tournament context |
| `sportmonks_prediction_promotion_shadow.jsonl` | 13,880 | SportMonks predictions |
| `xg_promotion_shadow.jsonl` | 13,880 | xG promotion |
| `expected_lineup_promotion_shadow.jsonl` | 14,000 | Lineups |
| `rule_a_live_validation.jsonl` | 13,355 | Rule validation |
| `expected_lineup_accuracy.jsonl` | 2,658 | Lineup accuracy |
| + 18 smaller replay/test files | — | Phase replays |

**Sub-stores:**

- `data/shadow/elite_learning_store/post_match_evaluations.jsonl`
- `data/shadow/root_cause_store/knowledge_records.jsonl`

**Consumer:** Shadow runtime, root cause analysis — **does not affect production predictions**.

---

### 4.11 Validation & predictions history

| Path | Type | Lines/rows | Modified |
|------|------|------------|----------|
| `data/validation/real_world_validation.jsonl` | jsonl | **13,386** | 2026-06-27 |
| `data/verification/prediction_verification.jsonl` | jsonl | 542 | 2026-06-16 |
| `data/predictions/prediction_history.jsonl` | jsonl | 108 | 2026-06-20 |
| `data/historical/worldcup_sample.csv` | csv | 14 | 2026-06-11 |
| `artifacts/backtest_ranked_picks_full.csv` | csv | 19,392 | 2026-06-20 |
| `artifacts/ml1_unified_dataset.parquet` | parquet | 1,617 (42 cols) | 2026-06-23 |
| `artifacts/daily_picks_2026-06-27.json` | json | 4 picks | 2026-06-27 |

---

### 4.12 Goalscorer pipeline artifacts (derived, 47k rows each)

| Path | Type | Rows |
|------|------|------|
| `artifacts/phase54k_goalscorer_shadow/goalscorer_dataset.csv` | csv | 47,029 |
| `artifacts/phase54k_goalscorer_shadow/goalscorer_dataset.parquet` | parquet | 47,029 |
| `artifacts/phase54q_goalscorer_generalization/goalscorer_intelligence_v3.parquet` | parquet | 47,029 |
| `artifacts/phase54s_player_availability/goalscorer_dataset_v5.parquet` | parquet | 47,029 |
| + odds bridge CSVs/parquet variants | mixed | 1,416–18,693 |

**Provider chain:** API-Football fixtures → internal feature engineering → odds mapping.

---

### 4.13 Embedded PostgreSQL (EGIE raw store dev)

**Path:** `data/pgembed_dev/` — **565 MB** · embedded Postgres cluster  
**Connection:** `postgresql://postgres:@127.0.0.1:62973/postgres`  
**Purpose:** Local dev fallback for `EgieRawStoreRepository` when `save_raw_with_fallback()` cannot reach production PG.

**Attach note:** Optional — only if EGIE Postgres ingest is enabled. Not required for SQLite-only prediction path.

---

### 4.14 Artifacts summary (research outputs)

| Category | Files | ~Size |
|----------|-------|-------|
| Goalscorer phase54*–55* | ~25 | ~45 MB |
| Pressure phase54h* | 6 | <1 MB |
| EGIE/xG phase54f* | 8 | <1 MB |
| Validation DBs phase44–46 | 7 | ~2.4 MB |
| Market behavior / timing / daily picks | ~8 | ~2 MB |

---

## 5. Provider → canonical path map

| Provider | Data types | Canonical local path | Already consumed by code? |
|----------|------------|----------------------|---------------------------|
| **SportMonks** | fixtures, odds, lineups, stats, events | `data/sportmonks_dump/` | Yes (import scripts) |
| **SportMonks** | xG | `data/feature_store/sportmonks_xg/raw/` | Yes (`sportmonks_xg_store.py`) |
| **SportMonks** | pressure, full UEFA payloads | `data/egie/uefa_club/raw/` | Yes (pressure store, EGIE ingest) |
| **SportMonks** | WC xG/lineups import | `data/egie/world_cup/raw/sportmonks/` (target) | Partial — import via `sportmonks_wc_import.py` |
| **API-Football** | events, lineups, stats, injuries | `data/egie/world_cup/raw/api_football/` | Yes (`raw_cache.py`) |
| **API-Football** | live cache | `.cache/api_football/` | Yes (API clients) |
| **API-Football** | fixtures, goal events | `data/football_intelligence.db` | Yes (repository) |
| **The Odds API** | odds snapshots | `data/football_intelligence.db` → `odds_snapshots` | Yes |
| **Internal** | shadow replays | `data/shadow/` | Yes (shadow only) |
| **Internal** | backtest/ML | `artifacts/` | Yes (scripts/backtests) |

---

## 6. Safe attach plan (DATA-0C preview — no execution)

All steps are **additive**, **offline**, and **do not change production prediction logic**.

### Phase 0 — Guardrails (before any attach)

1. Snapshot `data/football_intelligence.db` (already duplicated on Desktop).
2. Create `data/imports/` as **index only** — symlinks or `catalog.json`, never move source files.
3. Run all ingest in **`--dry-run`** / **`--from-cache-only`** modes where scripts support it.
4. Keep shadow/EGIE paths separate from production prediction hot path.

### Phase 1 — SportMonks fixtures (odds, lineups, stats, events)

| Step | Action | Source | Target consumer | Risk |
|------|--------|--------|-----------------|------|
| 1.1 | Register dump in catalog | `data/sportmonks_dump/` | `scripts/sportmonks_odds_import.py` | None — read JSON |
| 1.2 | Index by league/season manifest | existing `_manifest.json` per season folder | New catalog entry only | None |
| 1.3 | Optional WC 2026 odds extract | `data/sportmonks_dump/world_cup/2026/` | `scripts/sportmonks_wc2026_odds_import.py` | Low — writes odds tables only via dedicated script |

**Do not:** Re-run `sportmonks_full_dump.py` (API calls forbidden in DATA-0B).

### Phase 2 — SportMonks xG

| Step | Action | Source | Target consumer | Risk |
|------|--------|--------|-----------------|------|
| 2.1 | Point xG store at existing cache | `data/feature_store/sportmonks_xg/raw/` | `SportmonksXgFeatureStore.load_cache()` | None — already default path |
| 2.2 | Offline normalize → SQLite (optional) | 1,554 JSON files | `xg_snapshots` via store ingest **from cache** | Low — fills empty table without API |
| 2.3 | Cross-link to WC mapping | `data/validation/phase62b_*` + `wc_fixture_mapping` table | Phase 62B import | Medium — mapping required first |

### Phase 3 — API-Football (events, lineups, injuries, statistics)

| Step | Action | Source | Target consumer | Risk |
|------|--------|--------|-----------------|------|
| 3.1 | Attach WC raw JSON (50 fixtures) | `data/egie/world_cup/raw/api_football/` | EGIE coverage + `raw_cache.py` | None |
| 3.2 | Attach lineup cache | `.cache/api_football/lineups/` | Enrichment / expected lineup engines | None — read cache |
| 3.3 | Expand WC raw (future) | Use existing importer **from cached API responses only** | `api_football_historical_importer` + `raw_cache` | Low if cache-only |
| 3.4 | Goal events → DB (optional) | Existing JSON + DB backfill candidates CSV | `fixture_goal_events` backfill script | Low — append-only |

**Do not:** Call `ApiFootballHistoricalImporter.import_fixtures()` without cache/API-off flag.

### Phase 4 — Pressure

| Step | Action | Source | Target consumer | Risk |
|------|--------|--------|-----------------|------|
| 4.1 | Read UEFA raw JSON (pressure in includes) | `data/egie/uefa_club/raw/` (81 files) | `SportmonksPressureFeatureStore.load_cache()` | None |
| 4.2 | Merge legacy duplicate tree | Compare `data/data/egie/uefa_club/raw/` vs canonical — **catalog diff only**, no delete | Dedup manifest | None in DATA-0B |
| 4.3 | Populate pressure cache dir | Copy-by-reference symlink `data/feature_store/sportmonks_pressure/raw/` → UEFA raw | Pressure store primary path | None — symlink |
| 4.4 | Use existing parquet for research | `artifacts/phase54h*/pressure_*.parquet` | Shadow backtests only | None |

### Phase 5 — Odds

| Step | Action | Source | Target consumer | Risk |
|------|--------|--------|-----------------|------|
| 5.1 | SQLite odds_snapshots (1,443 rows) | `football_intelligence.db` | Live enrichment | None — already attached |
| 5.2 | SportMonks odds from dump | `data/sportmonks_dump/**` | `sportmonks_odds_import.py` offline | Low |
| 5.3 | Goalscorer odds CSV bridge | `artifacts/phase54m_goalscorer_odds_mapping/` | Research / goalscorer pipeline | None |
| 5.4 | PL odds backfill manifest | `data/shadow/phase54c1_pl_odds_backfill_manifest.jsonl` | Targeted backfill queue | None — manifest only |

### Phase 6 — Events & goal timing

| Step | Action | Source | Target consumer | Risk |
|------|--------|--------|-----------------|------|
| 6.1 | DB goal events (6,198) | `fixture_goal_events` | Prediction evaluation, timing models | None |
| 6.2 | WC API-Football events JSON | 50 files in `api_football/events/` | EGIE WC pipeline | None |
| 6.3 | SportMonks events in dump | embedded in dump JSON | Offline extract script | None |
| 6.4 | Goal timing CSV | `artifacts/phase60b_first_goal_timing_distribution/` | First-goal timing model (research) | None |

### Phase 7 — Lineups & injuries

| Step | Action | Source | Target consumer | Risk |
|------|--------|--------|-----------------|------|
| 7.1 | API-Football lineup cache | `.cache/api_football/lineups/` (1,696) | Expected lineup engine | None |
| 7.2 | WC lineups/injuries raw | 50 + 50 JSON each | EGIE WC raw cache | None |
| 7.3 | SportMonks lineups in dump | dump includes | Offline parse | None |
| 7.4 | Shadow lineup archives | `expected_lineup_*.jsonl` | Shadow/promotion only | None — not production |

### Phase 8 — Shadow & validation (read-only attach)

| Step | Action | Source | Notes |
|------|--------|--------|-------|
| 8.1 | Register shadow JSONL in catalog | `data/shadow/` | ~95k replay lines — research only |
| 8.2 | Attach validation corpus | `data/validation/real_world_validation.jsonl` (13,386 lines) | Accuracy / rule testing |
| 8.3 | Link artifacts parquet/CSV | `artifacts/` goalscorer, EGIE, pressure | Backtest inputs |

---

## 7. Recommended execution order (DATA-0C)

```
1. Create data/imports/catalog.json from this report (no file moves)
2. Symlink-index canonical stores under data/imports/
3. Deduplicate catalog entry: data/egie/uefa_club/raw vs data/data/egie/uefa_club/raw
4. Offline xG: ingest 1,554 JSON → xg_snapshots (cache-only mode)
5. Offline SportMonks dump → odds_snapshots / enrichment (existing import scripts, --offline)
6. WC raw API-Football: verify 50-fixture coverage against wc_fixture_mapping
7. Pressure: wire sportmonks_pressure/raw symlink to UEFA raw
8. Run validation scripts (read-only counts) — no production deploy
```

---

## 8. Explicit non-goals (this phase)

- No changes to `worldcup_predictor/prediction/**` production engines
- No API calls (SportMonks, API-Football, Odds API)
- No SQLite schema migrations
- No file deletes, overwrites, or moves
- No VPS deploy or `/opt/worldcup-predictor` modifications
- No git commits (unless requested separately)

---

## 9. Gaps & risks

| Gap | Impact | Mitigation |
|-----|--------|------------|
| `data/imports/` not provisioned | No unified staging index | Create symlink catalog in DATA-0C |
| `xg_snapshots` empty despite 1,554 JSON cache | xG not in SQLite | Offline cache ingest (Phase 2.2) |
| Duplicate UEFA raw trees (81 vs 105 files) | Possible double-read | Catalog diff before ingest |
| WC API-Football raw covers only 50 fixtures | Limited WC historical depth | Expand from dump + mapping table |
| `data/imports` on VPS unknown | Production may differ | Mirror catalog scan on VPS before attach |
| Desktop DB triplicate (~1.4 GB) | Disk use | Keep one backup; catalog notes duplicates |

---

## 10. Quick reference — file type totals under `data/`

| Folder | Files | Size (MB) | Primary types |
|--------|-------|-----------|---------------|
| `sportmonks_dump/` | 1,930 | 3,947 | json |
| `feature_store/` | 1,554 | 1,294 | json |
| `pgembed_dev/` | 1,211 | 565 | postgres cluster |
| `sportmonks_full_dump/` | 104 | 291 | json |
| `egie/` | 947 | 217 | json, parquet, jsonl |
| `data/data/` (nested) | 105 | 98 | json (legacy UEFA) |
| `shadow/` | 47 | 61 | jsonl |
| `validation/` | 32 | 44 | jsonl, json |
| `football_intelligence.db` | 1 | 470 | sqlite |
| `logs/`, `dev/`, `predictions/`, etc. | 8 | <1 | jsonl |

**Grand total (project `data/` + `.cache/api_football` + key `artifacts/`): ~7.1 GB**

---

*Generated by PHASE DATA-0B read-only audit. No files were modified during catalog creation.*
