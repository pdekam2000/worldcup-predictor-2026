# OddAlerts Lower-Band Gmail Import Report

**Phase:** ODDALERTS-LOWER-BAND-GMAIL  
**Date:** 2026-06-30  
**Mode:** Owner/internal — download 0–50% exports, incremental import, policy rerun — no odds_snapshots writes, no ECSE generation

---

## Summary

Lower-band OddAlerts probability exports (`0% - 50%`) were downloaded from Gmail, imported incrementally, crosswalked to local fixtures, and the bookmaker policy pipeline was re-run.

**ECSE READY_FULL increased from 0 → 197** (all original high-confidence Premier League fixtures now have complete complementary outcomes). Policy dry-run preview shows **197 fixtures would insert** to `odds_snapshots` — not executed.

**Final recommendation:** `READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN`

---

## Part A — Gmail download

**Command:**
```bash
python scripts/download_today_oddalerts_csv_from_gmail.py --date 2026-06-30 --tag-ecse-lower-band
```

**Query:** `from:joe@oddalerts.com subject:"Your Probability Export is Ready" after:2026/6/30 before:2026/7/1`

**Artifacts:**
- `artifacts/oddalerts_lower_band_gmail_download_summary_20260630.json`
- `artifacts/oddalerts_today_gmail_csv_download_summary_20260630.json`

| Metric | Value |
|--------|-------|
| Emails scanned | 500 |
| Links found | 500 |
| Lower-band emails (0%–50%) | **323** |
| Lower-band files downloaded | **285** (222 + 63 across runs) |
| Lower-band duplicates skipped | 260 |
| Upper-band duplicates skipped (50%–100%) | 177 |
| Links expired | 0 |
| Failed downloads | 0 |

**Band split:** 323 × `0% - 50%`, 177 × `50% - 100%` (duplicates only on second pass)

**Fix applied:** Probability range parser updated for OddAlerts trailing dash format (`0% - 50% -`).

---

## Part B — ECSE lower-band market coverage

**Artifact:** `artifacts/oddalerts_lower_band_ecse_market_coverage_20260630.json`

| Normalized key | Status |
|----------------|--------|
| match_result_home | **FOUND_0_50** |
| match_result_draw | **FOUND_0_50** |
| match_result_away | **FOUND_0_50** |
| goals_over_2_5 | **FOUND_0_50** |
| goals_under_2_5 | **FOUND_0_50** |
| btts_yes | **FOUND_0_50** |
| btts_no | **FOUND_0_50** |

**7/7 ECSE outcomes present** in lower band.

---

## Part C — Incremental import

**Command:** `python scripts/import_oddalerts_csv_incremental.py --input-dir data/oddalerts_csv/inbox`

| Metric | Value |
|--------|-------|
| Files staged | **285** |
| Promoted to odds_snapshots | **false** |
| Duplicate sha256 skipped | 0 (all new hashes) |

---

## Part D — All-market audit + import

**Command:** `python scripts/audit_oddalerts_csv_all_markets.py`

| Metric | Before | After |
|--------|--------|-------|
| Total mapped rows | 2,408,831 | **8,742,569** |
| Rows inserted (new) | — | **6,333,738** |
| Files scanned | 152 | **437** |
| Unknown markets | 0 | **0** |
| Bookmakers preserved | 8 | **8** |

**Key ECSE market row counts (after):**

| Key | Before | After |
|-----|--------|-------|
| match_result_draw | 12 | **426,696** |
| match_result_away | 35,313 | **412,585** |
| match_result_home | 101,160 | **381,810** |
| goals_under_2_5 | 96,415 | **335,616** |
| goals_over_2_5 | 129,074 | **299,511** |
| btts_yes | 108,983 | **237,847** |
| btts_no | 80,237 | **245,747** |

---

## Part E — Fixture crosswalk + bookmaker policy

**Required step:** `python scripts/crosswalk_oddalerts_probability_csv_to_fixtures.py`  
(New rows need `internal_fixture_id` before policy can use them.)

| Metric | Before crosswalk | After crosswalk |
|--------|------------------|-----------------|
| High-confidence fixtures in policy | 197 | **561** |
| ECSE READY_FULL | **0** | **197** |
| ECSE READY_PARTIAL | 197 | **364** |
| Policy would_insert (dry-run) | 0 | **197** |
| odds_snapshots written | 0 | **0** |

**Policy validation:** `BOOKMAKER_POLICY_READY_FOR_PROMOTION` (dry-run only)

---

## Part F — Complete coverage validation

**Artifact:** `artifacts/oddalerts_ecse_complete_coverage_readiness.json`

| Metric | Before (baseline) | After |
|--------|-------------------|-------|
| READY_FULL | **0** | **197** |
| READY_PARTIAL | **197** | **364** |

**Note:** 364 READY_PARTIAL fixtures are additional high-confidence crosswalk matches beyond the original 197 PL fixtures — they still lack some ECSE keys.

**Complete coverage validation:** 11/12 checks passed; `no_odds_snapshot_promotion` check flags `would_insert_count=197` (expected — preview only, no writes).

---

## Part G — Safety confirmation

| Rule | Status |
|------|--------|
| No odds_snapshots writes | ✓ (count unchanged at 2,015) |
| No ECSE generation | ✓ (8 snapshots unchanged) |
| No WDE generation | ✓ (173 unchanged) |
| No public changes | ✓ |
| Duplicate sha256 skipped | ✓ |
| Signed URLs redacted in logs | ✓ |

---

## Remaining blockers

1. **364 fixtures** still READY_PARTIAL — need additional market/date coverage or alias mapping for non-PL leagues.
2. **Odds snapshot promotion** not executed — owner approval required for next phase.
3. **Server DB** (`91.107.188.229`) not yet synced — pipeline run on local machine where Gmail OAuth exists. Deploy updated scripts to server; re-run after syncing inbox + DB or Gmail token.

---

## Files updated

- `worldcup_predictor/data_import/oddalerts_today_gmail_downloader.py` — lower-band classification, coverage artifacts
- `scripts/download_today_oddalerts_csv_from_gmail.py` — `--tag-ecse-lower-band`
- `scripts/validate_oddalerts_ecse_complete_coverage.py` — lower-band summary path

---

## Final recommendation

**`READY_FOR_ODDS_SNAPSHOT_PROMOTION_DRYRUN`**

Lower-band data imported successfully. All 7 ECSE outcomes present at 0–50%. Original **197 high-confidence fixtures** are now **READY_FULL**. Policy dry-run would insert 197 fixture snapshots — do not promote until owner approves next phase.

Also valid: **`ODDALERTS_LOWER_BAND_IMPORTED`** / **`ODDALERTS_COMPLETE_COVERAGE_READY`**
