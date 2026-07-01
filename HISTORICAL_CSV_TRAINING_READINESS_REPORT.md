# Historical CSV Training Readiness Report

**Phase:** WDE-RETRAIN-SHADOW-1
**Audited:** 2026-07-01 09:30:25 UTC
**Readiness:** `READY_FOR_SHADOW_TRAINING`

## Staging inventory

- Match rows: **353,396**
- Odds rows: **1,660,836**
- Date range: **2010-05-08** → **2027-06-06**
- Countries (top): 30 sampled in report
- Leagues (top): 30 sampled in report

## Match quality

- Completed matches with final score: **340,585**
- Complete FT 1X2 odds: **77,100**
- Complete O/U 2.5 odds: **42,586**
- Complete BTTS odds: **77,023**
- Rows with xG: **340,585**
- Rows with corners: **340,585**
- Duplicate match groups: **184**
- Invalid odds rows (odds staging): **0**
- Missing team names: **0**

## Usable rows for shadow training

- odds_only_baseline: **77,100**
- wde_1x2: **77,100**
- wde_btts: **77,023**
- wde_ou25: **42,586**
- xg_enhanced_model: **77,100**

## Team alias issues

- Internal normalized collisions: **0**
- Crosswalk NO_MATCH (local DB): **0**
- Crosswalk high confidence: **0**

## League alias issues

- Distinct leagues (top sample): **30**

## Blockers

- None critical

Artifact: `artifacts\historical_csv_training_readiness.json`
