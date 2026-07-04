# RESULT TRUTH REPAIR 1 — Final Report

Phase: **RESULT-TRUTH-REPAIR-1** | Recommendation: **`CANONICAL_EVALUATION_CONFIRMED`**

## Summary

1. **AET/PEN bug:** legacy `home_goals` stored post-AET aggregate; evaluators read it as 90m score.
2. **Fix:** schema v8 adds explicit regulation/AET/PEN columns + central market resolver.
3. **Synced:** 0 fixtures (0 provider calls).
4. **All 11 in DB:** 11/11 with regulation scores.
5. **Separate scores:** regulation + AET + PEN columns populated for AET/PEN fixtures.
6. **Market eval:** FixtureOutcomeResolver now uses regulation via resolver.
7. **Canada discrepancy:** REPORT_MANUAL_VALUE_DRIFT in manual owner tracker.
8. **Owner tracker:** regenerated from frozen DB rows (`CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md`).
9. **Metrics match forensic:** WDE 1X2 7/11 · ECSE Top3 5/11
10. **Colombia hash:** local vs production artifact drift — environment copy, not repair mutation.
11. **Next research:** BTTS calibration, O/U calibration, ECSE rank-lift shadow.

**Backup:** `C:\Users\kaman\Desktop\Footbal\artifacts\result_truth_repair_1\football_intelligence_pre_repair_20260704_214542.db`

**Final recommendation:** `CANONICAL_EVALUATION_CONFIRMED`
