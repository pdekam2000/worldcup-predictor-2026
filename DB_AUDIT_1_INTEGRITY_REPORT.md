# DB-AUDIT-1 — Integrity Report

**Audit:** PHASE DB-AUDIT-1  
**Mode:** Read-only  
**Generated:** 2026-06-29 UTC  
**Database:** `data/football_intelligence.db`  
**Runtime:** ~94 seconds

---

## Verdict

| Check | Result |
|-------|--------|
| **PRAGMA integrity_check** | **PASS** (`ok`) |
| **PRAGMA quick_check** | **PASS** (`ok`) |
| **PRAGMA foreign_key_check** | **PASS** (no violations; FK enforcement disabled) |
| **Expected row counts** | **PASS** (all four historical tables match exactly) |
| **ECSE modeling readiness** | **PASS with caveats** (see warnings below) |

The database file is structurally sound, row counts match DATA-1B through DATA-1G expectations, and the clean pre-match odds table has zero post-kickoff leakage. Minor referential gaps and one extreme score outlier are documented below and do not block ECSE work if handled in feature engineering.

---

## Database Size & Metadata

| Metric | Value |
|--------|-------|
| **File size** | 6,255,153,152 bytes (~5.83 GiB) |
| **Page size** | 4,096 bytes |
| **Page count** | 1,527,137 |
| **Freelist pages** | 0 |
| **schema_meta.schema_version** | `7` |
| **PRAGMA foreign_keys** | `0` (disabled) |

No freelist fragmentation detected. File size is dominated by historical odds tables (~2M+ rows).

---

## SQLite Integrity Checks

### PRAGMA integrity_check
```
ok
```

### PRAGMA quick_check
```
ok
```

### PRAGMA foreign_key_check
```
(empty — no violations reported)
```

**Note:** `foreign_keys` is disabled at connection level. Historical tables rely on application-level joins, not declared SQLite FOREIGN KEY constraints. This is consistent with the existing schema design.

---

## Table Row Counts vs Expected

| Table | Expected | Actual | Delta | Status |
|-------|----------|--------|-------|--------|
| `historical_csv_odds_imports` | 2,063,334 | 2,063,334 | 0 | **MATCH** |
| `historical_fixture_registry` | 223,215 | 223,215 | 0 | **MATCH** |
| `historical_fixture_results` | 222,985 | 222,985 | 0 | **MATCH** |
| `historical_csv_odds_prematch_clean` | 1,908,702 | 1,908,702 | 0 | **MATCH** |

### Supporting production tables

| Table | Rows |
|-------|------|
| `fixtures` | 2,161 |
| `fixture_results` | 1,929 |
| `predictions` | 17 |
| `odds_snapshots` | 1,443 |
| `xg_snapshots` | 0 |

### Missing tables (requested but not present)

| Table | Status |
|-------|--------|
| `provider_id_map` | **NOT FOUND** in database |
| `data_import_log` | **NOT FOUND** in database |

These tables are not part of the current schema. Historical pipeline tracking is embedded in import columns (`source_file`, `imported_at`, `build_batch`) rather than a dedicated log table.

---

## Referential Consistency

| Check | Count | Assessment |
|-------|-------|------------|
| Odds rows without `registry_fixture_id` | 0 | **PASS** |
| Odds rows with invalid `registry_fixture_id` | 0 | **PASS** |
| Clean rows without source odds row | 0 | **PASS** |
| Result rows without registry fixture | 0 | **PASS** |
| Registry fixtures without result | **230** | **WARN** — cancelled/deleted matches (`CANCL`, `Deleted`) |
| Clean rows joinable to results | 1,907,698 (99.95%) | **PASS** |
| Raw odds joinable to results | 2,062,130 | **PASS** |
| Registry → production fixture links | 242 linked, 0 invalid | **PASS** |
| Predictions with orphan fixtures | 0 | **PASS** |
| Fixture results with orphan fixtures | 0 | **PASS** |

The 230 registry fixtures without results are fixtures with status `CANCL` or `Deleted` in the registry — expected for abandoned matches, not a data corruption issue.

---

## Leakage Audit

### Clean pre-match table (`historical_csv_odds_prematch_clean`)

| Check | Violations | Status |
|-------|------------|--------|
| `closing_unix > kickoff_unix` | 0 | **PASS** |
| `opening_unix > kickoff_unix` | 0 | **PASS** |
| `peak_unix > kickoff_unix` | N/A | Column not present in clean table |
| Missing `kickoff_unix` | 0 | **PASS** |

The clean dataset is **leakage-free** for ECSE modeling use.

### Raw import table (`historical_csv_odds_imports`) — informational

| Check | Violations | Notes |
|-------|------------|-------|
| `peak_unix > kickoff_unix` | 34,464 | Present in raw; excluded from clean table |
| `closing_unix > kickoff + 2h` | 3,519 | Present in raw; excluded from clean table |
| Missing `kickoff_utc` | 0 | **PASS** |

Raw-table leakage is expected and is why DATA-1G built the clean subset (92.5% retention). **Use `historical_csv_odds_prematch_clean` for modeling, not the raw imports table.**

---

## Data Quality Summary

| Check | Count | Status |
|-------|-------|--------|
| Raw odds < 1.0 | 0 | **PASS** |
| Clean odds < 1.0 | 0 | **PASS** |
| Negative goal scores | 0 | **PASS** |
| Extreme goals (>20) | 1 (23–0) | **WARN** — `registry_fixture_id=214705` |
| Null home/away teams (registry) | 0 | **PASS** |
| Null league/date (registry) | 0 | **PASS** |
| Null home/away teams (raw odds) | 0 | **PASS** |
| Missing `raw_json` (odds) | 0 | **PASS** |
| Missing `raw_result_json` (results) | 0 | **PASS** |
| `result_1x2` encoding | `home` / `draw` / `away` | **PASS** (pipeline convention) |

**`result_1x2` note:** All 222,985 labeled rows use `home`, `draw`, or `away` — not `1`/`X`/`2`. This matches `historical_odds_baseline_backtest.py` and validation scripts. Not a defect.

### Market names

Seven distinct markets in raw data. Three extend beyond the original DATA-1B core set:

- Core: `ft_result`, `btts`, `over_under`, `corners_over_under`
- Additional: `double_chance`, `first_half_winner`, `team_over_under`

All seven are valid imported markets; no corrupt market strings detected.

---

## Index Inventory (Historical Tables)

### `historical_csv_odds_imports`
| Index | Unique | Columns |
|-------|--------|---------|
| `sqlite_autoindex_*_1` | Yes | `dedup_key` |
| `idx_historical_csv_odds_registry_fixture` | No | `registry_fixture_id` |
| `idx_historical_csv_odds_registry_key` | No | `registry_key` |
| `idx_historical_csv_odds_match_date` | No | `match_date` |
| `idx_historical_csv_odds_market` | No | `market`, `selection` |
| `idx_historical_csv_odds_fixture` | No | `internal_fixture_id` |

### `historical_fixture_registry`
| Index | Unique | Columns |
|-------|--------|---------|
| `sqlite_autoindex_*_1` | Yes | `registry_key` |
| `idx_historical_fixture_registry_internal` | No | `internal_fixture_id` |
| `idx_historical_fixture_registry_league` | No | `league_normalized`, `season` |
| `idx_historical_fixture_registry_date` | No | `match_date` |

### `historical_fixture_results`
| Index | Unique | Columns |
|-------|--------|---------|
| `sqlite_autoindex_*_1` | Yes | `dedup_key` |
| `idx_historical_fixture_results_registry` | No | `registry_fixture_id` |
| `idx_historical_fixture_results_source` | No | `source` |

### `historical_csv_odds_prematch_clean`
| Index | Unique | Columns |
|-------|--------|---------|
| `sqlite_autoindex_*_1` | Yes | `source_odds_id` |
| `idx_prematch_clean_registry` | No | `registry_fixture_id` |
| `idx_prematch_clean_market` | No | `market` |
| `idx_prematch_clean_kickoff_unix` | No | `kickoff_unix` |

---

## Performance & Slow-Query Risks

| Risk | Detail | Recommendation |
|------|--------|----------------|
| Full table scan on 2M+ rows | `historical_csv_odds_imports` without index filter | Use indexed columns (`market`, `match_date`, `registry_fixture_id`) in WHERE clauses |
| Join clean → results | 1.9M rows; indexed on `registry_fixture_id` | Acceptable for batch jobs; avoid in API hot path |
| `bookmaker` grouping | No index on `bookmaker` | Optional index if frequent bookmaker filters needed (not created in this audit) |
| `xg_snapshots` empty | 0 rows | No performance concern |
| DB size 5.8 GiB | Single-file SQLite | Consider read-only replicas or ATTACH for parallel research queries |

**No indexes were created during this audit.**

---

## Warnings for ECSE

1. **Use clean table only** — `historical_csv_odds_prematch_clean` for all modeling; raw table retains post-kickoff odds.
2. **230 fixtures without results** — filter by join to `historical_fixture_results` (already 99.95% coverage on clean rows).
3. **One 23–0 score** — verify or cap in feature engineering if using goal-difference features.
4. **`provider_id_map` / `data_import_log` absent** — not required for historical odds ECSE; production fixture mapping uses `internal_fixture_id` (242 links).
5. **`xg_snapshots` empty** — xG features must come from other sources for ECSE.

---

## Exact Next Actions

1. **Proceed with ECSE** using `historical_csv_odds_prematch_clean` joined to `historical_fixture_results`.
2. **Do not model on** `historical_csv_odds_imports` without additional leakage filters.
3. **Optional:** Investigate `registry_fixture_id=214705` (23–0) if goal-based features are sensitive to outliers.
4. **Optional:** Create `bookmaker` index only if query plans show full scans (not needed yet — single bookmaker: Bet365).
5. **Production sync:** This audit is local only; production DB does not yet contain these tables (see `SYNC_AUDIT_REPORT.md`).

---

*Read-only audit. No modifications, migrations, index creation, or deployments performed.*
