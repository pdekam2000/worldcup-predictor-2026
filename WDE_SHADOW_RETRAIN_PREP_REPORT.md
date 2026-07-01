# WDE Shadow Retrain Preparation Report

**Phase:** WDE-RETRAIN-SHADOW-1
**Recommendation:** `READY_FOR_WDE_SHADOW_TRAINING`

## Readiness status

- Readiness: **READY_FOR_SHADOW_TRAINING**
- Staged match rows: **353,396**
- Staged odds rows: **1,660,836**
- Usable WDE 1X2 rows: **77,100**

## Usable row counts

- odds_only_baseline: **77,100**
- wde_1x2: **77,100**
- wde_btts: **77,023**
- wde_ou25: **42,586**
- xg_enhanced_model: **77,100**

## Blockers

- None listed

## Shadow dataset

- Built: **yes**
- Path: `data\research\wde_shadow_training_dataset.parquet`
- Rows: **77,023**
- Skipped reason: none

## Validation

- Passed: **True**
- Checks: 13/13

## Safe to proceed to shadow training?

**Yes** — canonical shadow dataset validated; production WDE unchanged.

## Constraints

- Owner/internal research only
- No production WDE replacement
- No writes to worldcup_stored_predictions or odds_snapshots
- Staging tables only as source

Readiness report: `HISTORICAL_CSV_TRAINING_READINESS_REPORT.md`
Readiness artifact: `artifacts\historical_csv_training_readiness.json`