# External Historical ZIP Ingest Report

**Phase:** HISTORICAL-CSV-INGEST-1  
**Date:** 2026-06-30  
**Server:** 91.107.188.229 (`/opt/worldcup-predictor`)  
**Mode:** Owner/internal — stage only — no production writes

---

## Summary

HISTORICAL-CSV-INGEST-1 files were deployed to the server and the full staging pipeline completed successfully. The uploaded ZIP was preserved. All data landed in staging tables only.

**Final recommendation:** `NEED_TEAM_ALIAS_MAPPING`

---

## Deployment

Files deployed via SCP to `/opt/worldcup-predictor`:

| File | Status |
|------|--------|
| `config/external_historical_csv_schema.json` | Deployed |
| `worldcup_predictor/data_import/external_historical_ddl.py` | Deployed |
| `worldcup_predictor/data_import/external_historical_zip_importer.py` | Deployed (+ semicolon delimiter, path fixes) |
| `worldcup_predictor/data_import/external_historical_crosswalk.py` | Deployed (+ date-indexed fast crosswalk) |
| `scripts/inspect_external_historical_zip.py` | Deployed |
| `scripts/import_external_historical_zip.py` | Deployed |
| `scripts/crosswalk_external_historical_to_local_fixtures.py` | Deployed |
| `scripts/preview_external_historical_final_import.py` | Deployed |
| `scripts/validate_external_historical_zip_ingest.py` | Deployed (+ missing-table safe checks) |

**ZIP preserved:** `/opt/worldcup-predictor/data/external_historical_csv/inbox/historical_csv_data.zip` (6.8 MB)

---

## ZIP inspection

**Artifact:** `artifacts/external_historical_zip_profile.json`

| Metric | Value |
|--------|-------|
| CSV files in ZIP | **117** |
| Total rows | **366,592** |
| Countries | **78** |
| Leagues | **107** |
| Date range | 2010-05-08 → 2027-06-06 |
| Schema columns | 41 (semicolon-delimited CSV) |
| Schema match | **true** |
| Duplicate file groups | **5** |
| Path traversal blocked | 0 |

**Note:** CSVs use `;` delimiter (European export format). Importer auto-detects delimiter.

---

## Staging import (`--stage-only`)

**Artifact:** `artifacts/external_historical_zip_import_summary.json`

| Metric | Value |
|--------|-------|
| Files total | 117 |
| Files staged | **112** |
| Files skipped (duplicate hash) | **5** |
| Files rejected | 0 |
| Raw rows staged | **353,396** |
| Match history rows staged | **353,396** |
| Odds rows staged | **1,660,836** |
| Invalid odds skipped (≤1) | 3,146 |
| Errors | 0 |

Row delta vs ZIP total (366,592 − 353,396 = **13,196**) = rows in 5 duplicate CSV files skipped by `file_hash`.

---

## Market coverage (odds staging)

Top markets by row count:

| Market | Rows |
|--------|------|
| ft_result_home/draw/away | ~77,204 each |
| ft_goals_over_2_5 | 77,182 |
| ht_result_home/draw/away | ~77,174 each |
| ft_btts_yes/no | ~77,126 each |
| ft_goals_under_2_5 | 42,690 |

All FT/HT mapped markets present. `implied_probability = 1/odds` applied; invalid odds ≤1 skipped.

---

## Top leagues by match rows

EN2, EN3, EN4, JP2, IT1, EN1, BR1, US1, FR2, FR1, SP1, …

---

## Fixture crosswalk

**Artifact:** `artifacts/external_historical_fixture_crosswalk.json`

| Status | Unique matches |
|--------|----------------|
| NO_MATCH | 350,848 |
| MATCHED_HIGH_CONFIDENCE (≥0.90) | **2,019** |
| MATCHED_LOW_CONFIDENCE | 42 |
| **Total unique matches** | 352,909 |

Most external historical matches have no local fixture (expected — local DB is mostly WC/competition-specific). High-confidence matches exist for enrichment of 2,019 local fixtures.

---

## Final import preview

**Artifact:** `artifacts/external_historical_final_import_preview.json`

| Metric | Value |
|--------|-------|
| Could create new historical fixtures | ~350,890 |
| High-confidence local matches | 2,019 |
| Could become odds_snapshots (estimate) | 1,660,836 |
| xG enrichment rows | 353,396 |
| Corners enrichment rows | 353,396 |
| Existing odds_snapshots | 1,447 (unchanged) |
| Production promotion | **None** |

---

## Validation

**Artifact:** `artifacts/external_historical_zip_validation.json`

**16/16 checks passed**

- ZIP inspected
- Duplicate files skipped
- Raw + match + odds rows staged
- Odds probabilities valid
- No production fixtures written
- No odds_snapshots written
- No ECSE/WDE changes
- Artifacts created

---

## Fixes applied during deploy

1. **Status counter KeyError** — dict `.get()` increment in inspector  
2. **Semicolon delimiter** — auto-detect `;` vs `,` for European CSVs  
3. **Extract path resolution** — absolute paths for `relative_to()`  
4. **Crosswalk performance** — date-indexed fixture lookup (was O(n×m), now practical)  
5. **Validation** — graceful handling when `ecse_prediction_snapshots` absent on server

---

## Safety confirmation

| Rule | Status |
|------|--------|
| ZIP not deleted | ✓ |
| No production fixtures | ✓ |
| No odds_snapshots | ✓ |
| No WDE/ECSE generation | ✓ |
| Stage only | ✓ |
| Re-run safe (file_hash + row_hash dedup) | ✓ |

---

## Final recommendation

**`NEED_TEAM_ALIAS_MAPPING`**

Staging is complete and healthy (**353k match rows**, **1.66M odds rows**). Before any production import, build team/league alias maps — crosswalk shows **350,848** unique external matches with no local fixture vs **2,019** high-confidence matches. Do not promote to `fixtures` or `odds_snapshots` until alias mapping and a follow-up import phase are approved.

**Staging status:** `HISTORICAL_ZIP_STAGED_READY` (data in staging tables)  
**Production import status:** blocked pending team alias mapping
