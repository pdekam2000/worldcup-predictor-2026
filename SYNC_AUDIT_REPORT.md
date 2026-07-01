# SYNC-AUDIT REPORT — Local vs Production Server

**Audit date:** 2026-06-29  
**Mode:** Read-only (no writes, deploy, push, or migrations on either side)  
**Server:** `91.107.188.229`  
**Server project path:** `/opt/worldcup-predictor`  
**Local project path:** `C:\Users\kaman\Desktop\Footbal`

---

## Executive Summary

Production is **one full git commit behind** local `main` and has **none** of the DATA-1B through DATA-1G historical odds pipeline (code, tables, reports, or artifacts). The production database (`football_intelligence.db`) is **~409 MB** with **74 tables** and **no historical_* tables**. Local database is **~5.82 GiB** with **78 tables** and all four historical tables fully populated.

An in-progress `scp` transfer (`football_intelligence_new.db`, ~33% complete at audit time) is writing a **partial, malformed** copy of the local DB to the server. **Do not swap or query that file until the transfer completes and integrity is verified.**

---

## Git State

| Location | Commit | Message | Notes |
|----------|--------|---------|-------|
| **Local HEAD** | `d143e98` | DATA-1B-1C historical odds import and fixture registry | **1 commit ahead of `origin/main`**; not on server |
| **Server HEAD** | `4dd87d2` | Add daily picks system, scheduler, DailyPicksPage, result tracker | Matches `origin/main` |
| **origin/main** | `4dd87d2` | (same as server) | Local unpushed commit not on remote |

### Local working tree (uncommitted / untracked)

- **DATA-1E / 1F / 1G** modules, scripts, validators, reports, artifacts (all untracked)
- **DATA-1D** reports (`HISTORICAL_RESULTS_LABELS_REPORT.md`, `DATA_1D_BACKTEST_READINESS_REPORT.md`) — untracked
- Audit helper scripts: `artifacts/_sync_audit_*.py`, `artifacts/_sync_audit_server.sh`
- Deleted (unstaged): `artifacts/_data1d_probe.py`

### In local commit `d143e98` but NOT on server

Includes DATA-1B/1C/1D **code and scripts**, plus large non-code payloads that make a blind `git push` risky:

- `worldcup_predictor/data_import/historical_csv_odds.py`
- `worldcup_predictor/data_import/historical_fixture_registry.py`
- `worldcup_predictor/data_import/historical_fixture_results.py`
- `scripts/run_data_1b_csv_odds_import.py` through `validate_data_1d_historical_results_labels.py`
- Reports: `CSV_ODDS_CATALOG_REPORT.md`, `HISTORICAL_CSV_ODDS_IMPORT_REPORT.md`, `DATA_1C_COVERAGE_REPORT.md`, etc.
- Artifacts: `artifacts/data_1b_*.json`, `artifacts/data_1c_*.json`
- **Also in commit (problematic for push):** `credentials/*.json`, `data/backups/*.db` (multi-GB), `data/imports/oddalerts_probability_exports/` (~167 CSV files)

---

## Database State

| Metric | Local | Server (production) | Server (`football_intelligence_new.db`) |
|--------|-------|---------------------|----------------------------------------|
| **Path** | `data/football_intelligence.db` | `data/football_intelligence.db` | `data/football_intelligence_new.db` |
| **Size** | **6,255,153,152 bytes** (~5.82 GiB) | **428,699,648 bytes** (~409 MB) | **~2,120,417,280 bytes** at audit (~1.97 GiB); transfer in progress |
| **Table count** | 78 | 74 | Unreadable — **malformed** (incomplete transfer) |
| **schema_meta.schema_version** | `7` | `7` | N/A |
| **historical_* tables** | 4 present | **0** | N/A (incomplete) |

### Historical table row counts (local only)

| Table | Local rows | Server production |
|-------|-----------|-------------------|
| `historical_csv_odds_imports` | 2,063,334 | **MISSING** |
| `historical_fixture_registry` | 223,215 | **MISSING** |
| `historical_fixture_results` | 222,985 | **MISSING** |
| `historical_csv_odds_prematch_clean` | 1,908,702 | **MISSING** |

### Migration state

- No dedicated SQL migration files reference `historical_*` tables.
- Historical tables were created by **Python import scripts** (DATA-1B through DATA-1G), not by a migrations folder.
- Both local and server production DB report `schema_version = 7`; schema version alone does **not** indicate historical table presence.

### In-progress DB transfer

- Active local terminal: `scp` of `football_intelligence.db` → server `football_intelligence_new.db`
- Progress at audit: **~33%** (~1,976 MB of ~6,255 MB)
- Server file is **not valid SQLite** until transfer completes (confirmed: `database disk image is malformed`)

---

## DATA Phase Presence Matrix

| Phase | Description | Code on server | Tables on server | Reports on server | Artifacts on server | Local status |
|-------|-------------|----------------|----------------|-------------------|---------------------|--------------|
| **DATA-1B** | CSV odds import | **NO** | **NO** | **NO** | **NO** | Complete (committed + DB) |
| **DATA-1C** | Fixture registry / matching | **NO** | **NO** | **NO** | **NO** | Complete (committed + DB) |
| **DATA-1D** | Historical results labels | **NO** | **NO** | **NO** | **NO** | Complete (module/script committed; reports/artifacts local only) |
| **DATA-1E** | Baseline ROI backtest | **NO** | N/A (no new tables) | **NO** | **NO** | Complete locally (uncommitted) |
| **DATA-1F** | Positive ROI forensics | **NO** | N/A | **NO** | **NO** | Complete locally (uncommitted) |
| **DATA-1G** | Clean pre-match odds | **NO** | **NO** | **NO** | **NO** | Complete locally (uncommitted) |

**Conclusion:** DATA-1B through DATA-1G exist **only locally**. None are deployed to production.

---

## Four Lists

### A) Already on server

**Code**
- Full application at commit `4dd87d2` (daily picks, scheduler, DailyPicksPage, result tracker, and all prior merged phases)
- Standard production stack under `/opt/worldcup-predictor`

**Database tables**
- 74 production tables including fixtures, predictions, shadow data, etc.
- `schema_meta.schema_version = 7`
- **No** `historical_csv_odds_imports`, `historical_fixture_registry`, `historical_fixture_results`, or `historical_csv_odds_prematch_clean`

**Reports**
- Phase reports from commits ≤ `4dd87d2` (if present in repo at that commit)
- **No** DATA-1B through DATA-1G reports

**Datasets / artifacts**
- Production `football_intelligence.db` (~409 MB)
- Runtime shadow JSONL, sportmonks dumps, daily picks artifacts (server working tree has local modifications)
- **No** `artifacts/data_1*.json`

---

### B) Exists locally but NOT on server

**Code files**
- Entire local commit `d143e98` (DATA-1B/1C/1D import pipeline)
- Uncommitted DATA-1E/1F/1G modules:
  - `worldcup_predictor/data_import/historical_prematch_odds_clean.py`
  - `worldcup_predictor/research/historical_odds_baseline_backtest.py`
  - `worldcup_predictor/research/historical_odds_roi_forensics.py`

**Scripts**
- `scripts/run_data_1b_csv_odds_import.py` through `scripts/validate_data_1d_historical_results_labels.py` (in commit, not on server)
- `scripts/run_data_1e_baseline_backtest.py`, `run_data_1f_roi_forensics.py`, `run_data_1g_clean_prematch_odds.py`
- `scripts/validate_data_1e_baseline_backtest.py`, `validate_data_1g_clean_prematch_odds.py`

**Database tables**
- `historical_csv_odds_imports` (2,063,334 rows)
- `historical_fixture_registry` (223,215 rows)
- `historical_fixture_results` (222,985 rows)
- `historical_csv_odds_prematch_clean` (1,908,702 rows)

**Reports**
- Committed locally, not on server: `CSV_ODDS_CATALOG_REPORT.md`, `CSV_TO_FIXTURE_MATCHING_REPORT.md`, `DATA_1C_COVERAGE_REPORT.md`, `HISTORICAL_CSV_ODDS_IMPORT_REPORT.md`, `HISTORICAL_FIXTURE_REGISTRY_REPORT.md`, `HISTORICAL_ODDS_MATCHING_REPORT.md`, `ODDALERTS_CSV_AUDIT_REPORT.md`, `DATA_CATALOG_REPORT.md`
- Untracked locally: `HISTORICAL_RESULTS_LABELS_REPORT.md`, `DATA_1D_BACKTEST_READINESS_REPORT.md`, `DATA_1E_BASELINE_BACKTEST_REPORT.md`, `DATA_1E_MARKET_ROI_TABLES.md`, `DATA_1F_ROI_FORENSICS_REPORT.md`, `DATA_1F_LEAGUE_RANKINGS.md`, `DATA_1F_MARKET_RANKINGS.md`, `DATA_1G_CLEAN_PREMATCH_ODDS_REPORT.md`, `DATA_1G_CLEAN_ROI_BACKTEST_REPORT.md`

**Artifacts**
- `artifacts/data_1b_csv_catalog.json`, `data_1b_import_stats.json`, `data_1b_unmatched_rows.json`
- `artifacts/data_1c_ambiguous_matches.json`, `data_1c_coverage.json`, `data_1c_registry_stats.json`
- `artifacts/data_1d_ambiguous_results.json`, `data_1d_backtest_readiness.json`, `data_1d_field_audit.json`, `data_1d_no_result_fixtures.json`, `data_1d_results_stats.json`
- `artifacts/data_1e_backtest_summary.json`
- `artifacts/data_1f_forensics_summary.json`
- `artifacts/data_1g_clean_backtest_summary.json`

**Datasets (not suitable for git)**
- Full local `football_intelligence.db` (~5.82 GiB)
- `data/imports/oddalerts_probability_exports/` (167 CSV files, in commit)
- `data/backups/football_intelligence_pre_data1*.db` (multi-GB backups, in commit)

---

### C) Requires git push only

These items are **code/report/artifact files** that could reach the server via git (after commit + push + server `git pull`), with **no DB transfer**:

| Item | Action needed |
|------|---------------|
| DATA-1B/1C/1D modules and scripts (in `d143e98`) | Push commit (prefer **cleaned** commit without credentials/DB backups/CSV blobs) + server pull |
| DATA-1E/1F/1G modules and scripts | `git add` + commit + push + server pull |
| All DATA-1* markdown reports | Commit (where untracked) + push + server pull |
| `artifacts/data_1*.json` (except huge `data_1b_unmatched_rows.json`) | Commit + push + server pull |

**Caution:** Commit `d143e98` includes `credentials/*.json`, multi-GB `data/backups/*.db`, and ~167 CSV import files. A direct push of that commit is **not recommended**. Split into a code-only commit before pushing.

**Does NOT require DB transfer:** DATA-1E and DATA-1F (research/backtest only; no new tables).

---

### D) Requires database transfer or on-server re-run

| Item | Transfer / action |
|------|-------------------|
| `historical_csv_odds_imports` | Full DB transfer **or** re-run `run_data_1b_csv_odds_import.py` on server with CSV source files |
| `historical_fixture_registry` | Full DB transfer **or** re-run `run_data_1c_fixture_expansion.py` |
| `historical_fixture_results` | Full DB transfer **or** re-run `run_data_1d_historical_results_labels.py` |
| `historical_csv_odds_prematch_clean` | Full DB transfer **or** re-run `run_data_1g_clean_prematch_odds.py` (depends on 1B–1D tables) |
| Entire enriched local DB vs 409 MB production DB | **~5.4 GiB delta** — `scp`/`rsync` or staged import pipeline |

**Current transfer:** `scp` → `football_intelligence_new.db` is **in progress and incomplete**. After completion:

1. Verify size matches local (6,255,153,152 bytes)
2. Run `PRAGMA integrity_check;` and historical table row-count validation
3. Backup production `football_intelligence.db`
4. Atomic swap (operational step — **not performed in this audit**)

**Alternative to full DB swap:** Deploy code (C) then run DATA-1B → 1C → 1D → 1G scripts on server against import CSVs (requires copying `data/imports/oddalerts_probability_exports/` to server outside git).

---

## Missing Files (server relative to local)

### Modules (all missing on server)
- `worldcup_predictor/data_import/historical_csv_odds.py`
- `worldcup_predictor/data_import/historical_fixture_registry.py`
- `worldcup_predictor/data_import/historical_fixture_results.py`
- `worldcup_predictor/data_import/historical_prematch_odds_clean.py`
- `worldcup_predictor/research/historical_odds_baseline_backtest.py`
- `worldcup_predictor/research/historical_odds_roi_forensics.py`

### Scripts (all 11 DATA-1* run/validate scripts missing on server)

### Reports (all DATA-1* and related CSV/historical reports missing on server)

### Artifacts (all `artifacts/data_1*.json` missing on server)

---

## Missing Tables (server production DB)

| Table | Status |
|-------|--------|
| `historical_csv_odds_imports` | **MISSING** |
| `historical_fixture_registry` | **MISSING** |
| `historical_fixture_results` | **MISSING** |
| `historical_csv_odds_prematch_clean` | **MISSING** |

---

## Exact Next Actions Required

Ordered by dependency and safety:

1. **Let `scp` finish** (or cancel and restart with `rsync --partial` for resumability). Do not use `football_intelligence_new.db` until complete and integrity-checked.

2. **Clean git history before push**
   - Extract DATA-1B/1C/1D code, scripts, reports, and small artifacts into a **code-only commit**
   - Exclude: `credentials/`, `data/backups/*.db`, `data/imports/` CSV blobs
   - Commit DATA-1E/1F/1G code, scripts, reports, artifacts in a second commit

3. **Push to `origin/main`** and on server: `git pull` (brings code/reports/artifacts only; **not** DB tables)

4. **Database sync (choose one path)**
   - **Path A (fastest if transfer succeeds):** Complete `scp`, verify integrity + row counts, backup production DB, swap `football_intelligence_new.db` → `football_intelligence.db`
   - **Path B (reproducible):** Copy CSV import directory to server, run DATA-1B → 1C → 1D → 1G scripts in order on server

5. **Post-sync validation on server** (read-only checks first)
   - Confirm four historical tables exist with expected row counts
   - Run `validate_data_1b` through `validate_data_1g` scripts
   - Confirm application still starts against new DB

6. **Do not run migrations** — historical schema is script-managed; no pending SQL migrations were found for these tables.

---

## Audit Method Notes

- Local state: `git status`, `git rev-parse`, `artifacts/_sync_audit_local.py`
- Server state: SSH read-only commands, `artifacts/_sync_audit_server.py` uploaded to `/tmp` (read-only query; no server project files modified)
- No API calls, no deploys, no pushes, no migrations executed
- Server production DB queried successfully; `football_intelligence_new.db` rejected as malformed due to incomplete transfer

---

*End of SYNC-AUDIT report.*
