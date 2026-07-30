# FINAL PHASE-2 EXECUTIVE SUMMARY

## Primary status

**DATASET_RECONCILIATION_AND_EXPERIMENTS_COMPLETE**

## Answers (required)

1. Freezes originally evaluated (prior audit rows): **142**
2. Unique fixtures originally evaluated: **142**
3. Newly resolved results: **26**
4. Still unresolved: **83** (73 not terminal / future; 5 test; 5 regulation mismatch)
5. Duplicate groups: **62**
6. Canonical unique-fixture evaluation count: **168**
7. Corrected Exact Top1/Top3/Top5/Top10: **14.9% / 29.8% / 45.2% / 75.6%**
8. Corrected WDE/BTTS/O/U: **48.8% / 51.8% / 56.0%**
9. Previous conclusions changed?: **No material change** (Top5 +0.9 pp; Top1 slightly lower with larger n)
10. Persistence fixes: FIX-001 rank prob backfill (prior) + freeze meta v3 (odds provider, no_bet, conflict_count, probability_unit, pct fields, schema version) for **new** freezes; derived research table for historical reconstruction
11. Unit-contract fixes: `probability_units.py` — canonical fractions [0,1]; `*_pct` presentation; tests added
12. Best challenger: **G3 Dixon–Coles** (val Top5 54.4%, +4.4 pp)
13. Challenger regressions: G3 Top1 −2.9 pp; G2 overall Top5 regression; **all fail high-score tail (0%)**
14. High-score-tail improvement: **none achieved**
15. Rank-calibration improvement: **none** (G5 flat)
16. WDE improvement: diagnostic only (disagree severity predicts failure); no formula promotion
17. Proposed forward-shadow: G3 DC + WDE/ECSE severity flag
18. Minimum forward sample: **≥150** settled (≥30 high-score)
19. Production-safe changes: persistence + unit contract + timer comment clarity + result sync of missing FT (eval DB only)
20. Shadow-only: all G1–G6 formula challengers, Tier S rules, WDE blend ideas
21. GitHub parity: audit branch local (commits on `audit/deep-model-forensic-20260730T115031Z`)
22. Production parity: **UNKNOWN** (no live deploy)
23. GPT Actions parity: **UNKNOWN** (MCP previously errored; schema unit docs not deployed)
24. Remaining blockers: 83 unresolved (mostly not finished); production/GPT live verify; complete-metadata cohort n=3; high-score tail unsolved

## Tests

- `pytest tests/forward_evaluation/` → **113 passed** (timer-unit failure fixed via repo comment)
- Targeted unit/probability/freeze tests included

## Production changes

**None deployed.** Local/eval DB only: new `actual_results` rows + `freeze_derived_research_metadata` research table.

## Artifact path

`artifacts/dataset_reconciliation_experiments/20260730T125305Z/`
