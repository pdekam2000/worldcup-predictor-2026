# DB-AUDIT-1 — Duplicate Report

**Audit:** PHASE DB-AUDIT-1  
**Mode:** Read-only  
**Database:** `data/football_intelligence.db`  
**Generated:** 2026-06-29 UTC

---

## Verdict

**PASS** — All primary deduplication keys enforce uniqueness. No duplicate rows exist on the canonical keys used by the DATA-1 pipeline. Apparent duplicates on `oddalerts_row_id` are **expected** (one CSV fixture row maps to many market/selection odds rows).

---

## Deduplication Key Design

| Table | Canonical unique key | Enforced by |
|-------|---------------------|-------------|
| `historical_csv_odds_imports` | `dedup_key` | UNIQUE autoindex |
| `historical_fixture_registry` | `registry_key` | UNIQUE autoindex |
| `historical_fixture_results` | `dedup_key` | UNIQUE autoindex |
| `historical_csv_odds_prematch_clean` | `source_odds_id` | UNIQUE autoindex |

---

## 1. Historical CSV Odds (`historical_csv_odds_imports`)

### By `dedup_key` (canonical — maps to "source odds row" uniqueness)

| Metric | Value |
|--------|-------|
| Total rows | 2,063,334 |
| Distinct `dedup_key` | 2,063,334 |
| Duplicate key groups | **0** |
| Extra rows from duplicates | **0** |

**Status: PASS** — Every row has a unique `dedup_key`. This is the correct dedup dimension for odds selections.

### By `oddalerts_row_id` (informational — NOT a uniqueness key)

| Metric | Value |
|--------|-------|
| Distinct `oddalerts_row_id` | 223,218 |
| Groups with count > 1 | 214,008 |
| Max rows per ID | 36 |

**Status: EXPECTED** — OddAlerts exports one row per fixture in the CSV, but each fixture generates multiple odds rows (one per market/selection/bookmaker combination). The pipeline correctly deduplicates at `dedup_key` level, not `oddalerts_row_id`.

Example: `oddalerts_row_id=332473436` appears 36 times (different markets/selections).

### By `source_odds_id`
Not applicable to raw imports table — `id` is the primary key (auto-increment, unique by definition).

---

## 2. Historical Fixture Registry (`historical_fixture_registry`)

### By `registry_key`

| Metric | Value |
|--------|-------|
| Total rows | 223,215 |
| Distinct `registry_key` | 223,215 |
| Duplicate key groups | **0** |

**Status: PASS** — One registry entry per unique match key (date + league + teams).

### By `registry_fixture_id`
Auto-increment primary key — 223,215 distinct IDs, no duplicates.

---

## 3. Historical Fixture Results (`historical_fixture_results`)

### By `registry_fixture_id`

| Metric | Value |
|--------|-------|
| Total rows | 222,985 |
| Distinct `registry_fixture_id` | 222,985 |
| Duplicate ID groups | **0** |

**Status: PASS** — Exactly one result label row per registry fixture.

### By `dedup_key`

Unique constraint enforced via autoindex — no duplicate groups detected.

---

## 4. Clean Pre-Match Odds (`historical_csv_odds_prematch_clean`)

### By `source_odds_id`

| Metric | Value |
|--------|-------|
| Total rows | 1,908,702 |
| Distinct `source_odds_id` | 1,908,702 |
| Duplicate ID groups | **0** |

**Status: PASS** — One clean row per source odds row. The 154,632 excluded source rows (2,063,334 − 1,908,702) were removed for leakage, not deduplication failure.

---

## 5. Production Fixtures (`fixtures`)

### By `fixture_id`

| Metric | Value |
|--------|-------|
| Total rows | 2,161 |
| Distinct `fixture_id` | 2,161 |
| Duplicate ID groups | **0** |

**Status: PASS**

### By match composite key (`competition_key`, `kickoff_utc`, `home_team`, `away_team`)

| Metric | Value |
|--------|-------|
| Duplicate match groups | **0** |

**Status: PASS** — No duplicate fixtures by provider/source match identity.

**Note:** `fixtures` table uses `fixture_id` as primary key; `source` column exists but there is no separate provider fixture ID column in schema. Duplicate audit used composite match identity.

---

## 6. Odds Snapshots (`odds_snapshots`)

### By (`fixture_id`, `snapshot_at`)

| Metric | Value |
|--------|-------|
| Total rows | 1,443 |
| Duplicate groups | **0** |

**Status: PASS**

---

## 7. xG Snapshots (`xg_snapshots`)

| Metric | Value |
|--------|-------|
| Total rows | 0 |
| Duplicate (`fixture_id`, `snapshot_at`) groups | 0 |

**Status: N/A** — Table is empty.

**Schema note:** `xg_snapshots` stores `payload_json` blobs with columns `fixture_id`, `competition_key`, `snapshot_at` only. There are no `team_id`, `minute`, or `period` columns at table level. A row-level xG dedup audit by provider + fixture + team + minute is **not possible** on current schema without parsing `payload_json`. No duplicates exist (empty table).

---

## 8. Provider ID Map (`provider_id_map`)

**Table does not exist** — duplicate audit skipped.

---

## Summary Matrix

| Entity | Dedup key | Duplicates | Safe for ECSE |
|--------|-----------|------------|---------------|
| Raw odds | `dedup_key` | 0 | Yes (with leakage filter) |
| Registry | `registry_key` | 0 | Yes |
| Results | `registry_fixture_id` / `dedup_key` | 0 | Yes |
| Clean odds | `source_odds_id` | 0 | Yes |
| Production fixtures | `fixture_id` | 0 | Yes |
| Odds snapshots | fixture + snapshot_at | 0 | Yes |
| xG snapshots | N/A (empty) | 0 | N/A |

---

## Recommendations

1. **Continue using `dedup_key`** as the authoritative uniqueness key for raw odds — do not dedupe on `oddalerts_row_id`.
2. **Clean table is 1:1 with source** — `source_odds_id` uniqueness confirms DATA-1G did not introduce duplicate clean rows.
3. **No dedup remediation required** before ECSE build.
4. **If `xg_snapshots` is populated later**, define and index a dedup key (e.g. `fixture_id + team_id + minute + period`) before bulk insert.

---

*Read-only audit. No rows deleted or modified.*
