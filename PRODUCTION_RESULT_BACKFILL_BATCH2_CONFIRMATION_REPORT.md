# Production Result Backfill Batch 2 — Confirmation Report

**Generated:** 2026-07-11T08:15:00+00:00  
**Server:** `root@91.107.188.229:/opt/worldcup-predictor`  
**Git SHA:** `ec21a5637532a75ee6e83aaa7d502167a8e939c2`  
**DB:** `data/football_intelligence.db` (9.6G, updated 2026-07-11 08:10 UTC)

**FINAL STATUS:** `RESULT_BACKFILL_BATCH2_CONFIRMED_PARTIAL`

---

## 1. Killed tasks — replaced?

| Task | Outcome |
|------|---------|
| Production lightweight validation **382192** | Externally killed; **replaced** by successful `validate_provider_rescue_lightweight.py --before 220` runs (07:53 and 08:09 UTC) |
| Local export + validate **262818** | Externally killed; local DB lock **cleared**; **replaced** by production export `artifacts/provider_rescue/FT_WITHOUT_RESULT_TARGETS_220.jsonl` (220 rows, ~10s) |

No action required on killed tasks.

---

## 2. Artifact locations

There is **no** `artifacts/production_result_gap/` directory. All result-gap artifacts live under:

```
artifacts/provider_rescue/
├── FT_WITHOUT_RESULT_TARGETS_220.jsonl   (220 rows)
├── checkpoint.json                       (updated 2026-07-11T07:38:12Z)
├── rescue_ledger.jsonl                   (396 entries)
├── lightweight_validation.json           (updated 2026-07-11T08:09:49Z)
└── audit_payload.json
```

Ledger path used: `artifacts/provider_rescue/rescue_ledger.jsonl`

---

## 3. Did batch-2 run and complete?

There is **no explicit `batch2` ID** in the ledger (no lines matching `batch`). The continuation run is recorded as **`category: results`** entries completing **2026-07-11T07:37:50 – 07:38:12 UTC**.

Context from prior report (`FT_RESULT_BACKFILL_220_REPORT.md`):

- **Batch 1:** 86 repaired → 134 remaining  
- **Batch 2 (this confirmation):** resumed via `european_result_backfill` team+date matching; checkpoint `result_targets_done` now lists **208 fixture IDs**

### Batch run summary (final ledger entry)

| Field | Value |
|-------|------:|
| Batch ID | `results` backfill run (checkpoint `updated_at`) |
| Started (last fixture writes) | ~2026-07-11T07:37:50 UTC |
| Completed | **2026-07-11T07:38:12 UTC** |
| Targets total | **220** |
| Results inserted (`result_targets_done`) | **208** |
| Skipped existing | **5** |
| Conflicts | **0** |
| Provider errors | **12** |
| API calls | **379** |
| Checkpoint complete | **Yes** — `result_targets_done` populated, `updated_at` set |

Ledger `result_backfill_ok` line count: **307** (includes duplicate log lines per fixture; unique successful targets in checkpoint: **208**).

---

## 4. Lightweight validation (`--before 220`)

Script: `scripts/validate_provider_rescue_lightweight.py --before 220`  
Run: 2026-07-11T08:09:49 UTC (~218s, no full integrity)

| Check | Before | After | Pass |
|-------|-------:|------:|:----:|
| FT without result | 220 | **12** | ✓ (Δ −208) |
| Duplicate fixtures | 0 | **0** | ✓ |
| Orphan results | 0 | **0** | ✓ |
| Orphan odds | — | skipped (heavy) | n/a |
| Integrity / quick_check | — | **ok** | ✓ |
| Checkpoint batches | — | **79** | ✓ |
| Ledger entries | — | **396** | ✓ |
| Automation | — | **enabled** | ✓ |

**Inserted results** = 220 − 12 = **208** (matches `ft_without_result_delta`).

---

## 5. Remaining 12 FT-without-result — classification

All 12 failed with **`PROVIDER_MISSING_FIXTURE:no_provider_payload_or_goals`** from API-Football:

| Fixture ID | Classification |
|-----------:|----------------|
| 19135068 | **PROVIDER_FIXTURE_MISSING** |
| 19135067 | **PROVIDER_FIXTURE_MISSING** |
| 18151376 | **PROVIDER_FIXTURE_MISSING** |
| 18151377 | **PROVIDER_FIXTURE_MISSING** |
| 18151404 | **PROVIDER_FIXTURE_MISSING** |
| 18151405 | **PROVIDER_FIXTURE_MISSING** |
| 1058458 | **PROVIDER_FIXTURE_MISSING** |
| 1058470 | **PROVIDER_FIXTURE_MISSING** |
| 1058451 | **PROVIDER_FIXTURE_MISSING** |
| 1058436 | **PROVIDER_FIXTURE_MISSING** |
| 1058443 | **PROVIDER_FIXTURE_MISSING** |
| 1058472 | **PROVIDER_FIXTURE_MISSING** |

No safe provider payload available — **do not backfill blindly**.

---

## 6. Policy compliance

| Constraint | Status |
|------------|--------|
| Full PRAGMA integrity_check over SSH | **Not run** |
| Heavy orphan_odds scan | **Skipped** |
| Local 32GB export | **Not rerun** |
| Predictions regenerated | **No** |
| WDE / ECSE changed | **No** |
| Odds / bookmaker / freshness gates changed | **No** |
| Timers changed | **No** |
| Existing result rows overwritten | **No** (5 skipped_existing; 0 conflicts) |
| Results fabricated | **No** |

---

## 7. Production services

| Service | Status |
|---------|--------|
| worldcup-api | active |
| worldcup-gpt-actions | active |
| worldcup-mcp | active |

Production is **safe to continue prediction operations**. Remaining 12 gaps are provider-side missing fixtures, not structural DB corruption.

---

## 8. Answers (required)

1. **DB structurally suspicious?** No — dup=0, orphan_results=0, quick_check=ok.
2. **Duplicate fixtures remain 0?** Yes.
3. **Orphan results remain 0?** Yes.
4. **FT without result before?** 220.
5. **Provider-result-available (backfilled)?** 208 inserted from confirmed provider data.
6. **Safe to backfill?** 208 were safe; 12 blocked.
7. **Actually inserted?** **208**.
8. **Remain missing?** **12**.
9. **Why remaining?** API-Football returned no payload/goals for those fixture IDs.
10. **Existing results overwritten?** No.
11. **Predictions regenerated?** No.
12. **WDE/ECSE formulas changed?** No.
13. **Evaluation only on frozen prematch?** Not run in this confirmation phase.
14. **Newly evaluated predictions added?** 0 (confirmation only).
15. **Updated FT-without-result count?** **12**.
16. **Full integrity_check run?** No.
17. **Background plan created?** Not in scope for this confirmation; prior phase documented `nohup` approach.
18. **Log / check status?** Use `artifacts/provider_rescue/lightweight_validation.json` and `rescue_ledger.jsonl`.
19. **Production safe?** Yes.

---

## 9. Recommended next step (optional, not executed)

For the 12 `PROVIDER_FIXTURE_MISSING` rows: manual review only — verify whether fixture IDs are stale/merged in API-Football or status should be corrected from FT to postponed/abandoned. Do not retry blind bulk backfill.
