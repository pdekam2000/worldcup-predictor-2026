# ECSE-1B — FT Draw Coverage Audit Report

**Phase:** ECSE-1B  
**Mode:** Read-only (no modifications, no rebuild)  
**Generated:** 2026-06-29 UTC  
**Database:** `data/football_intelligence.db`

---

## Executive Summary

**`ft_draw` coverage is zero because the upstream OddAlerts CSV export contains no draw rows.** Four `fulltime_result__draw__*.csv` files exist on disk but each contains **only a header row (411 bytes, 0 data rows)**. The import pipeline, market normalization, parser, and DATA-1G prematch filter never received draw data to process.

**Root cause:** `SOURCE_EXPORT_GAP` — empty draw CSV stubs from OddAlerts export, not an application bug.

---

## Row Counts

| Layer | Expected draw rows | Actual draw rows | Status |
|-------|-------------------|------------------|--------|
| **Raw CSV exports** | ~50,000+ (see below) | **0** | **FAIL — empty files** |
| **`historical_csv_odds_imports`** | Same as CSV | **0** | Correct (nothing to import) |
| **`historical_csv_odds_prematch_clean`** | Subset of imports | **0** | Correct (nothing to clean) |
| **`ecse_training_dataset.ft_draw_*`** | Per-fixture pivot | **0** | Correct (no source) |

### FT result breakdown (actual)

| Selection | Raw imports | Clean prematch |
|-----------|-------------|----------------|
| `home` | 74,561 | 64,571 |
| `away` | 26,118 | 22,766 |
| `draw` | **0** | **0** |
| **Total `ft_result`** | 100,679 | 87,337 |

### Expected draw rows (estimate)

| Basis | Estimate |
|-------|----------|
| Actual draw **results** in `historical_fixture_results` | **53,537** fixtures ended in a draw |
| Home odds rows in imports | 74,561 |
| Fixtures with home odds but no away odds (clean) | 64,567 |
| Reasonable lower bound if export were complete | **≥ 22,000** (away row count) |
| Reasonable target if 1X2 symmetric | **~50,000–75,000** |

Draw odds should exist for roughly the same fixture universe as home/away 1X2 selections. With **53,537 draw results** in the label table, we would expect tens of thousands of draw odds rows — not zero.

---

## Investigation by Layer

### 1. Raw CSV exports

| File type | Files | Data rows |
|-----------|-------|-----------|
| `fulltime_result__home__*` | 4 | **74,561** |
| `fulltime_result__away__*` | 4 | **26,118** |
| `fulltime_result__draw__*` | 4 | **0** |

Draw file paths (all header-only):

- `data/imports/oddalerts_probability_exports/unknown_date_range/fulltime_result/fulltime_result__draw__unknown_to_unknown.csv`
- `...__dup1.csv`, `...__dup2.csv`, `...__dup3.csv`

Each draw file is **411 bytes** (header line only). Home files are **3.8–4.9 MB** with thousands of rows.

`CSV_ODDS_CATALOG_REPORT.md` and `artifacts/data_1b_csv_catalog.json` already recorded `row_count: 0` for all draw files at DATA-1B catalog time.

**Outcome values found in all FT CSVs:** `home` (74,561), `away` (26,118). **No `draw` outcome in any row.**

---

### 2. `historical_csv_odds_imports`

| Check | Result |
|-------|--------|
| `ft_result` + `selection='draw'` | **0 rows** |
| Distinct FT selections | `home`, `away` only |
| Rows from `__draw__` source files | **0** |
| Selection vs filename mismatch | **0** (no cross-contamination) |

Import correctly ingested all non-empty CSV data. Empty draw files produced zero rows.

---

### 3. `historical_csv_odds_prematch_clean`

| Check | Result |
|-------|--------|
| `ft_result` + `selection='draw'` | **0 rows** |
| Draw rows excluded by prematch filter | **N/A** (no draw rows to filter) |
| Draw rows that would pass prematch SQL | **0** |

DATA-1G `is_prematch_row()` was **not** the cause. There is no draw data to exclude.

---

### 4. `ecse_training_dataset`

| Check | Result |
|-------|--------|
| `ft_draw_closing IS NOT NULL` | **0** |
| `ft_draw_opening IS NOT NULL` | **0** |

ECSE-1A correctly pivots `ft_draw_*` from clean table; columns exist but are NULL for all 217,518 rows.

---

## Root Cause Analysis

| Hypothesis | Verdict | Evidence |
|------------|---------|----------|
| **Parser bug** | **RULED OUT** | Home/away parse correctly with `Outcome` → `selection`; same code path would handle `draw` |
| **Market normalization issue** | **RULED OUT** | `detect_market_from_path()` maps `fulltime_result` → `ft_result`; draw files use same folder/pattern as home/away |
| **Naming / selection mismatch** | **RULED OUT** | No draw rows exist to mis-name; filename `__draw__` never produces rows |
| **DATA-1G filtering bug** | **RULED OUT** | Zero draw rows in imports; exclusion counters N/A |
| **ECSE-1A pivot bug** | **RULED OUT** | `ft_draw` spec looks for `market='ft_result', selection='draw'` — correct, but no source rows |
| **Upstream export gap** | **CONFIRMED** | 4 draw CSV stubs, 0 data rows, cataloged at DATA-1B |

### Primary root cause

> **OddAlerts probability export delivered empty `fulltime_result__draw__*.csv` files (header-only).** The pipeline is working as designed; the draw 1X2 leg was never exported with data.

### Secondary observation (not the zero cause)

Home and away FT exports are **asymmetric** (74,561 vs 26,118 rows), so even home/away 1X2 coverage is incomplete across fixtures. Only **87,333** fixtures have any FT odds in clean; **0** have all three 1X2 legs.

---

## Impact on ECSE

| Item | Impact |
|------|--------|
| `ft_draw_opening/closing/movement` | Always NULL — cannot train direct draw odds features |
| Draw result labels | **53,537** available in `historical_fixture_results` |
| Proxy signals | `double_chance` (`home_draw`, `draw_away`) and `fh_draw` have data; partial draw information |
| Implied draw probability | Could be derived from home/away odds (Shin / normalization) in a future phase — not in current dataset |

---

## Recommended Next Actions (informational — not executed)

1. **Re-export** OddAlerts `fulltime_result` draw probability CSVs with the same date ranges as home/away files.
2. **Re-run DATA-1B** import only for new draw CSVs (read-only on existing rows if using `INSERT OR IGNORE`).
3. **Re-run DATA-1G** clean build to pull draw rows through prematch filter.
4. **Re-run ECSE-1A** (or incremental pivot update) to populate `ft_draw_*` columns.
5. **Validate** draw row count ≈ same order of magnitude as away rows (≥ 20k) before modeling.

---

## Artifacts

- `artifacts/ecse_1b_ft_draw_audit.json` — machine-readable audit payload
- Audit script: `artifacts/_ecse_1b_draw_audit.py` (read-only runner)

---

*Read-only audit. No database modifications, rebuilds, or deployments performed.*
