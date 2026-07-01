# OddAlerts Probability CSV Export — Read-Only Audit Report

**Date:** 2026-06-29  
**Path audited:** `data/imports/oddalerts_probability_exports/`  
**Mode:** Read-only — no DB import, no file changes, no prediction logic changes

---

## 1. Executive summary

| Metric | Value |
|--------|-------|
| Manifest rows | **167** |
| CSV files on disk | **167** |
| Download status `ok` | **167** |
| Download status `failed` | **0** |
| Download status `skipped` | **0** (not recorded in manifest) |
| Total disk size | **464.3 MB** (486,847,414 bytes) |
| Total data rows (all files) | **2,094,444** |
| Unique schemas | **1** (30 columns, all files) |
| Empty / header-only files | **10** |
| Malformed CSVs | **0** |
| Encoding failures | **0** |
| Byte-identical duplicate file groups (sha256) | **5 groups** (16 files involved) |
| Files with `__dup` suffix | **126** (re-downloads of same market/outcome) |

Downloads completed successfully. Data is usable for offline analysis. Main quality issues: **email metadata not parsed** (all `date_from`/`date_to` = `unknown`), **many duplicate downloads** from repeated Gmail exports, and **10 empty exports** (header-only, 411 bytes).

---

## 2. Manifest summary (`manifest.csv`)

| Column | Finding |
|--------|---------|
| `download_status` | 167 × `ok`, 0 × `failed`, 0 × `no_link` |
| `email_id` | 167 unique emails |
| `received_at` | 2026-06-28 batch (~20:13–20:18 UTC) |
| `market` | 19 distinct markets (human-readable labels) |
| `outcome` | 26 outcome variants (trailing ` -` from parser) |
| `probability_range` | All rows: `50% - 100% -` |
| `date_from` / `date_to` | **All 167 rows: `unknown`** |
| `error` | Empty on all rows |

**Manifest ↔ disk:** All 167 manifest `local_path` entries exist on disk. No orphan CSVs outside manifest.

---

## 3. File inventory

### 3.1 Layout

All files live under:

```
data/imports/oddalerts_probability_exports/unknown_date_range/{market_slug}/
```

Because date range parsing failed at download time, every export uses folder `unknown_date_range`.

### 3.2 Markets on disk (19)

| Market slug | Files | Total rows | Total size (approx) |
|-------------|-------|------------|---------------------|
| `double_chance` | 12 | 482,298 | ~113 MB |
| `over_under_2_5` | 8 | 222,913 | ~50 MB |
| `over_under_3_5` | 8 | 131,465 | ~31 MB |
| `over_under_1_5` | 8 | 117,964 | ~26 MB |
| `over_under_4_5` | 8 | 108,578 | ~25 MB |
| `fulltime_result` | 12 | 100,679 | ~23 MB |
| `home_over_under_1_5` | 8 | 84,299 | ~19 MB |
| `away_over_under_1_5` | 8 | 84,289 | ~19 MB |
| `away_over_under_0_5` | 8 | 84,286 | ~19 MB |
| `home_over_under_0_5` | 8 | 84,265 | ~19 MB |
| `corners_over_under_10` | 11 | 81,260 | ~18 MB |
| `both_teams_to_score` | 7 | 77,435 | ~17 MB |
| `corners_over_under_6` | 8 | 73,115 | ~17 MB |
| `corners_over_under_5` | 8 | 72,803 | ~16 MB |
| `corners_over_under_7` | 8 | 72,512 | ~16 MB |
| `corners_over_under_11` | 8 | 70,944 | ~16 MB |
| `corners_over_under_8` | 8 | 64,550 | ~15 MB |
| `corners_over_under_9` | 8 | 41,706 | ~10 MB |
| `first_half_winner` | 13 | 39,083 | ~9 MB |

---

## 4. Grouping by market and outcome

### 4.1 Outcome breakdown (deduplicated view — all files including `__dup`)

| Market | Outcome | Files | Rows | Notes |
|--------|---------|-------|------|-------|
| **Double Chance** | home_away | 4 | 188,299 | Largest single outcome |
| | home_draw | 4 | 167,732 | |
| | draw_away | 4 | 126,267 | |
| **Over/Under 2.5** | over_25 | 4 | 129,151 | |
| | under_25 | 4 | 93,762 | |
| **Over/Under 1.5** | over_15 | 4 | 117,813 | |
| | under_15 | 4 | 151 | Nearly empty under side |
| **Over/Under 3.5** | under_35 | 4 | 120,822 | |
| | over_35 | 4 | 10,643 | |
| **Over/Under 4.5** | under_45 | 4 | 107,619 | |
| | over_45 | 4 | 959 | |
| **Fulltime Result** | home | 4 | 74,561 | |
| | away | 4 | 26,118 | |
| | draw | 4 | **0** | All 4 files empty (header only) |
| **BTTS** | yes | 4 | 51,971 | |
| | no | 3 | 25,464 | |
| **Corners O/U 5–11** | over_* | 4 each | 25k–72k | High row counts |
| | under_* | 4 each | 0–77k | Several under sides empty or tiny |
| **Home/Away O/U 0.5 & 1.5** | over / under | 4 each | 2k–82k | Asymmetric over vs under |
| **First Half Winner** | home / away / draw | 4–5 | 5k–18k | |

Row counts per file: min **0**, max **58,155**, median **~9,042**.

---

## 5. CSV schema (uniform across all 167 files)

All files share **one schema** — 30 columns:

| # | Column | Role |
|---|--------|------|
| 1 | `ID` | OddAlerts row / selection ID |
| 2 | `Fixture` | `"Home vs Away"` label |
| 3 | `Kickoff` | Datetime string |
| 4 | `Home Team` | Home team name |
| 5 | `Away Team` | Away team name |
| 6 | `Status` | Match status (e.g. `FT`) |
| 7–8 | `Home Goals`, `Away Goals` | Final score |
| 9 | `Corners` | Corner count |
| 10 | `HT Score` | Half-time score |
| 11–14 | `Home/Away Position`, `Home/Away Played` | Table context |
| 15 | `Competition Progress` | Season progress % |
| 16–19 | `Is Friendly`, `Competition Type`, `Competition Country`, `Competition Name` | Competition meta |
| 20 | `League Predictability` | poor / medium / good |
| 21 | `Probability (%)` | Model probability |
| 22 | `Implied Odds` | Derived from probability |
| 23 | `Outcome` | Selection outcome code |
| 24–29 | `Opening/Closing/Peak Odds` + Unix timestamps | Odds history |
| 30 | `Bookmaker` | e.g. `Bet365` |

**Key columns present in all non-malformed files:** `ID`, `Fixture`, `Kickoff`, `Home Team`, `Away Team`, `Probability (%)`, `Outcome`, `Bookmaker` — **no missing key columns** on any file.

**Encoding:** All files read successfully as `utf-8` or `utf-8-sig`. No encoding issues detected.

---

## 6. Duplicate analysis

### 6.1 Byte-identical files (sha256)

| SHA256 (prefix) | Files | Interpretation |
|-----------------|-------|----------------|
| `d1a6a32e…` | **10 files** | Identical 411-byte header-only CSV (empty data) |
| `946ad080…` | 2 | Same Corners O/U 10 under export re-downloaded |
| `8d97d6b1…` | 2 | Same Corners O/U 10 over export re-downloaded |
| `f68a2cf0…` | 2 | Same Corners O/U 10 under dup3/dup4 |
| `073d9066…` | 2 | Same First Half Winner draw dup1/dup2 |

**Unique content files (by sha256):** ~151 of 167 (16 are exact duplicates of another file).

### 6.2 Filename duplicates (`__dupN`)

126 of 167 files have `__dup1`, `__dup2`, etc. in the name — caused by the downloader receiving **multiple Gmail emails for the same market/outcome** within the 7-day window and saving each with an incremented suffix.

### 6.3 Row-level duplicates

| Check | Result |
|-------|--------|
| Duplicate rows **within** a single file (by `ID`) | **0** across all files |
| Same `ID` appearing in **multiple market files** | **Expected** — same fixture appears in different market exports (e.g. FT home + O/U 2.5 over) |
| Cross-file fixture overlap | ~214k IDs appear in more than one deduplicated file — normal for multi-market probability exports |

**Recommendation for import:** Deduplicate by `sha256` before ingest; use `ID` + `market` + `outcome` as composite key, not `ID` alone.

---

## 7. Quality issues

### 7.1 Empty / header-only files (10)

All are **411 bytes**, sha256 `d1a6a32e…`, **0 data rows**:

- `corners_over_under_5` under_55 (×2 dup)
- `corners_over_under_6` under_65 (×2 dup)
- `corners_over_under_7` under_75 (×2 dup)
- `fulltime_result` draw (×4 dup)

**Cause:** OddAlerts export contained no rows matching probability filter for these selections (likely no draws / under corners in 50–100% band).

### 7.2 Near-empty files

| File pattern | Rows | Size |
|--------------|------|------|
| `over_under_1_5` under_15 | 151 | 5 KB |
| `over_under_4_5` over_45 | 959 | 83 KB |
| `corners_over_under_11` over_115 | 180 | 16 KB |
| Various corners `under_*` | 319–2,561 | <1 MB |

### 7.3 Malformed CSVs

**None detected.** All files parsed with Python `csv.DictReader`.

### 7.4 Metadata gaps (manifest / folder structure)

| Issue | Impact |
|-------|--------|
| `date_from` / `date_to` = `unknown` | All files in `unknown_date_range/` — email body date range not parsed |
| `outcome` has trailing ` -` | Cosmetic; slug still usable |
| `probability_range` truncated | Shows `50% - 100% -` instead of clean range |

---

## 8. Largest exports (by row count)

| Rows | Size | File |
|------|------|------|
| ~58,155 | ~13 MB | `double_chance__home_away__unknown_to_unknown.csv` |
| ~58,155 | ~12 MB | `double_chance__home_draw__unknown_to_unknown.csv` |
| ~58,155 | ~9 MB | `double_chance__draw_away__unknown_to_unknown.csv` |
| ~29,038 | ~8 MB | `over_under_2_5__over_25__unknown_to_unknown.csv` |
| ~23,441 | ~6 MB | `over_under_2_5__under_25__unknown_to_unknown.csv` |

*(Approximate — multiple `__dup` copies share same row counts.)*

---

## 9. Provider and content notes

- **Source:** OddAlerts probability export emails (`joe@oddalerts.com`)
- **CDN:** `oddalertscdn.fra1.digitaloceanspaces.com`
- **Content:** Historical finished fixtures with model probability, implied odds, and Bet365 (primary) opening/closing/peak odds
- **Date coverage in data:** Kickoff dates in CSVs span **2024-08-01** onward (sampled from `fulltime_result` home export); exact global min/max not computed in this audit
- **Bookmaker:** Predominantly `Bet365` in sampled rows

---

## 10. Recommendations (next phase — not executed here)

1. **Deduplicate before import:** Keep one file per unique `sha256`; drop 16 byte-identical copies.
2. **Fix email metadata parser:** Extract `Date Range` from HTML emails so future exports land in dated folders.
3. **Skip empty exports:** Treat 411-byte header-only files as `no_data` in manifest.
4. **Import key:** `(ID, market_slug, outcome_slug)` or OddAlerts `ID` within single market file only.
5. **Do not import** `fulltime_result` draw until non-empty export is obtained.

---

## 11. Audit artifacts

| Artifact | Path |
|----------|------|
| Manifest | `data/imports/oddalerts_probability_exports/manifest.csv` |
| Machine-readable audit JSON | `artifacts/_oddalerts_csv_audit.json` |
| This report | `ODDALERTS_CSV_AUDIT_REPORT.md` |

---

## 12. Explicit non-actions

- No import into `football_intelligence.db`
- No changes to prediction engines or production code
- No files deleted, renamed, or modified

---

*Generated by read-only audit script. Total audit runtime ~16s for 167 CSV files / 464 MB.*
