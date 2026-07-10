# Pre-Automation Evaluation DB Integrity Report

Date: 2026-07-10  
DB: `/opt/worldcup-predictor/data/evaluation/forward_prediction_tracking.db`

## Result: **PASS**

| Check | Expected | Actual |
|-------|----------|--------|
| Frozen predictions | 3 | 3 |
| PENDING | 3 | 3 |
| Exact-score rank rows | 15 | 15 |
| Orphan rank rows | 0 | 0 |
| Duplicate payload groups | 0 | 0 |
| Missing Top1–Top5 | none | none |
| Post-kickoff freeze violations | none | none |

## Known fixtures

| fixture_id | evaluation_status | payload_hash (prefix) |
|------------|-------------------|------------------------|
| 1494204 | PENDING | ac21f1ea… |
| 1494205 | PENDING | 0650521f… |
| 1494208 | PENDING | 78a6ea71… |

Checksum SHA256 (source): `e1fdcc08e06bbb54743b6fb163f95a81f2055bc0a7ae4b614f564b725eb9ecd1`

## Backup

Path: `data/evaluation/backups/forward_prediction_tracking_20260710T173405Z.db`  
Verified readable: frozen=3, ranks=15

**Status:** `EVALUATION_DB_INTEGRITY_PASS`
