# OddAlerts CSV Promotion Write Report

**Phase:** ODDALERTS-CSV-PROMOTION-3  
**Date:** 2026-06-30  
**Generated:** 2026-07-01 03:47:54 UTC  
**Mode:** WRITE — no ECSE/WDE generation

---

## Summary

**Final recommendation:** `WRITE_ABORTED_VALIDATION_FAILED`

---

## Part A — Backup

| Field | Value |
|-------|-------|
| DB type | sqlite |
| Backup path | `data\backups\football_intelligence_before_oddalerts_csv_promotion_20260701_034614.db` |
| Backup size | 28,894,498,816 bytes |
| Backup success | True |

---

## Part B — Write results

| Metric | Value |
|--------|-------|
| Candidates processed | 197 |
| Inserted | 73 |
| Enriched (new snapshot version) | 124 |
| Skipped | 0 |
| Conflicts | 0 |
| Duplicate skip (re-run) | 0 |
| odds_snapshots before | 2,015 |
| odds_snapshots after | 2,212 |
| odds_snapshots delta | 197 |

**Enrichment behavior:** New odds_snapshots row appended per fixture; original placeholder/partial rows preserved (immutable).

---

## Part C — Sample written fixtures

| Fixture ID | Match | Action | Competition |
|------------|-------|--------|-------------|
| 1035349 | Manchester City vs Brentford | WOULD_ENRICH | premier_league |
| 1035385 | Fulham vs Everton | WOULD_ENRICH | premier_league |
| 1035387 | Nottingham Forest vs Arsenal | WOULD_ENRICH | premier_league |
| 1035392 | Liverpool vs Chelsea | WOULD_ENRICH | premier_league |
| 1035393 | Manchester City vs Burnley | WOULD_ENRICH | premier_league |
| 1035394 | Bournemouth vs Nottingham Forest | WOULD_ENRICH | premier_league |
| 1035395 | Arsenal vs Liverpool | WOULD_ENRICH | premier_league |
| 1035396 | Brentford vs Manchester City | WOULD_ENRICH | premier_league |
| 1035398 | Burnley vs Fulham | WOULD_ENRICH | premier_league |
| 1035404 | Aston Villa vs Manchester United | WOULD_ENRICH | premier_league |

---

## Part D — Post-write ECSE readiness (check only)

| Metric | Value |
|--------|-------|
| Fixtures written | 197 |
| ECSE odds-snapshot ready | 143 |
| Policy READY_FULL | 197 |
| WC fixtures | 2 |
| UEFA/PL fixtures (sample) | 50 |

---

## Part E — Validation

- [pass] backup_created: data\backups\football_intelligence_before_oddalerts_csv_promotion_20260701_034614.db
- [pass] backup_size_nonzero: 
- [pass] no_ecse_snapshots_generated: 
- [pass] no_wde_generated: 
- [pass] egie_unchanged: no EGIE writes in promotion phase
- [pass] public_output_unchanged: no public UI changes
- [pass] billing_unchanged: no billing side effects
- [pass] ready_full_only: non_ready=0
- [pass] odds_snapshots_delta_matches: delta=197 expected=197
- [pass] no_conflicts_written: 
- [FAIL] written_rows_have_source_provider: rows=50
- [pass] written_rows_have_source_detail: 
- [pass] probabilities_valid: invalid=0
- [pass] source_refs_present: missing=0
- [pass] no_fresh_provider_overwritten: 0
- [pass] no_duplicate_snapshot_keys: per-fixture latest snapshot checked
- [pass] db_integrity_ok: ok
- [pass] rollback_documented: 
- [pass] dryrun_artifact_used: 
- [pass] conflict_candidates_not_written: 

Passed: **19** / **20**

---

## Rollback

If rollback is required:

```bash
cp data\backups\football_intelligence_before_oddalerts_csv_promotion_20260701_034614.db data/football_intelligence.db
```

Stop the app/services first, restore the backup file, then restart.
