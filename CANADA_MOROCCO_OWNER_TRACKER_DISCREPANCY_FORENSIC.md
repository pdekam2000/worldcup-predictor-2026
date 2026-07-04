# Canada vs Morocco — Owner Tracker Discrepancy Forensic

Phase: **RESULT-TRUTH-REPAIR-1** | Generated: 2026-07-04 21:49:12 UTC

## Root cause classification

**`REPORT_MANUAL_VALUE_DRIFT`**

CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md was manually authored; Morocco shown likely from ECSE Top1 0-1 or highest implied away probability, not canonical_1x2_selection.

## Answers

1. **Authoritative frozen WDE pick:** `draw` → **Draw**
2. **DB row:** `worldcup_stored_predictions.fixture_id=1567824`
3. **Why tracker showed Morocco Win:** Manual markdown listed `Morocco (away)`; ECSE Top1=`0-1`; away_win prob=46.2
4. **Other fixtures affected:** Any row in manual tracker not regenerated from DB (all 4 controlled rows were manual)
5. **UI/API impact:** UI/API use stored payload via canonical helpers; **only markdown tracker** was wrong unless cached elsewhere
