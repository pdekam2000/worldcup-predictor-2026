# PHASE 44 — HISTORICAL EVALUATION BACKFILL AUDIT

**Mode:** Read-only audit  
**Date:** 2026-06-21  
**Scope:** Production (`91.107.188.229` / `footballpredictor.it.com`) + local dev mirror  
**No code changes. No deploy. No DB modifications.**

---

## Executive summary

Performance Center shows **only 2 evaluated predictions** because the **`worldcup_prediction_evaluations` SQLite table literally contains 2 rows**, both written during **Phase 33/35 validation/deploy testing** — not from live post-match automation.

**Root cause (low coverage):**

1. **Automatic evaluation is not running in production** — systemd timers exist in repo but are **not installed/enabled**.
2. **Most stored predictions are for upcoming fixtures** (10/12 on prod still `NS`) — correctly not evaluable yet.
3. **Finished World Cup fixtures with real results were never stored in `worldcup_stored_predictions`** — Phase 33 storage started after those matches; legacy data lives in older SQLite/JSONL paths only.
4. **The 2 existing evaluation rows are stale test artifacts** — fixtures are still `NS` in `fixtures`, but evaluations claim `2-1` / `correct` from deploy-time validation runs.

**Recommendation:** Do **not** execute a blind “full historical backfill” yet. First enable scheduled evaluation + fix invalid test rows; then run a **targeted** backfill only where durable stored payloads exist for finished fixtures (currently **0 eligible** on prod).

---

## 1. Total predictions stored since project start

Counts below are **exact** from read-only SQL/JSONL scans on **2026-06-21**.

### Production (authoritative)

| Store | Table / path | Count | Notes |
|-------|----------------|------:|-------|
| **SQLite** | `worldcup_stored_predictions` | **12** | Phase 33+ durable archive (Performance Center source) |
| **SQLite** | `worldcup_prediction_evaluations` | **2** | Phase 33 eval table (Performance Center metrics) |
| **SQLite** | `predictions` (legacy engine) | **17 rows** / **5 distinct fixtures** | Pre–Phase 33 engine headers |
| **SQLite** | `verification_results` (legacy) | **70** | Per-market verification (GUI/legacy path) |
| **SQLite** | `learning_records_v2` | **152** | Self-learning records |
| **SQLite** | `.cache/predictions/` files | **46** | File cache (not all mirrored to `worldcup_stored_predictions`) |
| **PostgreSQL** | `user_prediction_history` | **9 rows** / **3 users** | Per-user view log (1X2 only); all `result=pending` in DB column |
| **JSONL** | `data/predictions/prediction_history.jsonl` | **100 lines** / **50 unique fixtures** | Global learning memory (Streamlit/accuracy tracker) |
| **JSONL** | `data/verification/prediction_verification.jsonl` | **542 lines** | Verification export log |
| **JSONL** | `data/results/match_results.jsonl` | **16 lines** / **16 fixtures** | Finished match outcomes (used by `FixtureOutcomeResolver`) |
| **JSONL** | `data/shadow/*.jsonl` | **0 files on prod** | Shadow/replay (dev only) |

### Local dev (reference)

| Store | Count |
|-------|------:|
| `worldcup_stored_predictions` | 2 |
| `worldcup_prediction_evaluations` | 2 |
| `prediction_history.jsonl` | 108 lines / 27 fixtures |
| `prediction_verification.jsonl` | 542 lines / 16 fixtures |
| `match_results.jsonl` | 16 lines / 16 fixtures |
| Shadow JSONL | 21 files / 28,221 lines |

---

## 2. Total finished fixtures represented in stored predictions

### Production

| Metric | Count |
|--------|------:|
| Finished fixtures in `match_results.jsonl` | **16** |
| Finished fixtures in SQLite `fixture_results` (all competitions) | **1,616** |
| Finished `world_cup_2026` in `fixtures` (`FT`/`AET`/`PEN`) | **4** |
| **`worldcup_stored_predictions` on finished fixtures** | **0** |
| Legacy `predictions` rows on finished WC fixtures (1489369, 1489370, 1538999, 1539000) | **16 rows** (duplicate runs) |

All **12** production stored predictions map to fixtures with status **`NS`** (not started).

Stored prediction fixture IDs (prod):  
`1489392, 1489393, 1489394, 1489395, 1489396, 1489397, 1489398, 1489399, 1489400, 1489401, 1539007, 1539017`

---

## 3. Total predictions already evaluated

### Performance Center pipeline (`worldcup_prediction_evaluations`)

| Environment | Rows | `correct` | `wrong` | `pending` |
|-------------|-----:|----------:|--------:|----------:|
| **Production** | **2** | 2 | 0 | 0 |
| Local dev | 2 | 2 | 0 | 0 |

Evaluated fixture IDs (prod): **`1489393`**, **`1539007`**

### Legacy parallel systems (not surfaced in Performance Center)

| System | Evaluated-ish rows |
|--------|-------------------:|
| `verification_results` (SQLite) | 70 market-level rows |
| JSONL `prediction_verification.jsonl` | 542 lines |
| PG `user_prediction_history.result` column | 0 resolved (9 pending) — enrichment is read-time via `FixtureOutcomeResolver` in API |

---

## 4. Predictions eligible for evaluation but not yet evaluated

**Eligible** = has row in `worldcup_stored_predictions` **AND** fixture is finished with a resolvable result **AND** no valid evaluation row (or evaluation should be refreshed).

### Production

| Category | Count |
|----------|------:|
| Stored + finished + not evaluated | **0** |
| Stored + not evaluated (upcoming) | **10** |
| Stored + “evaluated” but fixture still `NS` (invalid) | **2** |
| Finished WC fixtures with legacy `predictions` but **no** stored payload | **4** |
| JSONL learning records overlapping `match_results.jsonl` finished fixtures | **0** |

**Conclusion:** There are **zero** production rows that are both **validly finished** and **missing evaluation** in the Phase 33 table today. The gap is **missing stored payloads for historical finished matches**, not a failed evaluator on eligible rows.

---

## 5. Why only 2 evaluated predictions appear in Performance Center

Performance Center (`GET /api/performance/summary`) reads exclusively from:

- `worldcup_prediction_evaluations` via `get_accuracy_summary()` / `rebuild_accuracy_summary()`
- See `worldcup_predictor/api/performance_center.py`

Therefore the UI shows **exactly what is in that table: 2 rows**.

### How those 2 rows were created

| Fixture | Stored source | Fixture status now | Eval `final_score` | Eval `evaluated_at` |
|---------|---------------|-------------------|--------------------|---------------------|
| 1539007 | `phase35_test` | `NS` | 2-1 | 2026-06-20T16:10:14 |
| 1489393 | `user_predict` | `NS` | 2-1 | 2026-06-20T16:10:14 |

Both evaluation timestamps match **Phase 33/35 deploy validation** window (same second as test payload writes). They were produced by `run_evaluate_worldcup_results()` / validation scripts using **synthetic or stub outcomes**, not real FT results.

**Evidence:**

- `fixtures.status = NS` for both, kickoff still in the future/present window.
- `match_results.jsonl` on prod has **no** entries for 1489393 or 1539007.
- Phase 33 deploy report documented manual auto-cycle with **Evaluated: 0** initially; later validation added test evaluations.

**Impact:** Performance Center currently displays **100% winrate (2/2)** — **not representative** of real match performance.

---

## 6. Is evaluation running automatically?

| Question | Answer |
|----------|--------|
| Running automatically? | **No** |
| Scheduler installed? | **No** — `/etc/systemd/system/worldcup-*.timer` **not present** |
| `worldcup-evaluate-results.timer` | `not-found` / `inactive` |
| `worldcup-auto-cycle.timer` | `not-found` |
| `worldcup-daily-predict.timer` | `not-found` |
| Background job in API process? | **No** — evaluation is **CLI/admin triggered** only |

### Available triggers (manual)

| Trigger | Location |
|---------|----------|
| CLI | `python main.py evaluate-worldcup-results [--limit N]` |
| CLI | `python main.py worldcup-auto-cycle` (predict + evaluate + summary) |
| Admin API | `POST /api/admin/accuracy/rebuild` (runs evaluate + rebuild) |
| One-time deploy | Phase 33 deploy ran `worldcup-auto-cycle` manually |

### Evaluation job behavior (`result_evaluation_job.py`)

- Scans up to **`limit=100`** finished fixtures (`list_fixtures(status_class="finished")`).
- For each: load `worldcup_stored_predictions` → `evaluate_stored_prediction()` → `upsert_worldcup_prediction_evaluation()`.
- Rebuilds `worldcup_accuracy_summary`.
- **Does not modify** stored prediction payloads.

Repo includes systemd unit files under `deployment/systemd/` marked **“PLAN ONLY — not enabled”** (Phase 33 report explicitly: **“Not enabled (files prepared only)”**).

---

## 7. Can historical backfill safely evaluate old predictions without changing original values?

**Yes — with constraints.**

| Aspect | Assessment |
|--------|------------|
| Stored prediction immutability | **Safe** — `evaluate_stored_prediction()` only **reads** `payload_json` |
| Writes | Inserts/updates **`worldcup_prediction_evaluations`** and **`worldcup_accuracy_summary`** only |
| Upsert semantics | `ON CONFLICT(fixture_id) DO UPDATE` **overwrites** prior evaluation row for same fixture (does not touch prediction) |
| Risk | Re-running on the **2 test fixtures** will **replace** bogus `correct/2-1` when real results exist |
| Missing payloads | Cannot evaluate fixtures that were **never** stored in `worldcup_stored_predictions` without a separate **migration** step |
| Privacy | World Cup archive rows contain **no user_id** — safe for global metrics |

**Not safe without a plan:** importing JSONL/legacy rows into Performance Center metrics without dedupe rules and payload schema validation.

---

## 8. Backfill estimate

### Scenario A — Run evaluator on current prod data (no migration)

| Metric | Estimate |
|--------|----------|
| New evaluation rows | **0** (no finished + stored pairs) |
| Rows refreshed | **2** when those fixtures actually finish |
| Runtime | **< 5 seconds** (`limit=100` scan) |
| DB impact | **Negligible** (≤100 upserts + 1 summary JSON row) |

### Scenario B — Targeted backfill after migrating legacy finished fixtures

| Metric | Estimate |
|--------|----------|
| Finished WC fixtures with legacy `predictions` but no stored payload | **4** |
| Recoverable from file cache | **0** (no cache files for those fixture IDs) |
| JSONL overlap with finished `match_results` | **0** on prod |
| Realistic new evaluations if payloads reconstructed | **0–4** (only if full API payloads can be recovered) |
| Runtime | **< 30 seconds** |
| DB impact | **+4 rows** in evaluations + summary refresh |

### Scenario C — “Full historical” across all JSONL / verification / legacy

| Metric | Estimate |
|--------|----------|
| Legacy `verification_results` | **70** market rows / **~5** fixtures |
| JSONL `prediction_history` | **50** fixtures (mostly not finished on prod) |
| Duplicate systems risk | **High** — triple counting if merged naively |
| Recommended | **Do not** bulk-import without unified dedupe + schema mapping |

---

## 9. Market coverage

### Performance Center / `pick_evaluator` (Phase 33 path)

| Market | Evaluated in `worldcup_prediction_evaluations`? | Prod sample (2 rows) |
|--------|--------------------------------------------------|----------------------|
| **1X2** | ✅ `market_1x2_status` | 2 correct |
| **Over/Under 2.5** | ✅ `market_ou_status` | 2 correct |
| **BTTS** | ✅ `market_btts_status` | 2 void (no selection in payload) |
| **Double Chance** | ✅ `market_dc_status` | 2 null |
| **Safe / Value / Aggressive picks** | ✅ columns + `detail_json` | 2 correct each |
| **Correct Score** | ❌ not persisted to eval table | — |
| **Goal Timing / HT bucket** | ❌ not in Phase 33 eval table | — |
| **First Goal Team** | ⚠️ in `detail_json` / summary helper only | — |
| **Goalscorer** | ❌ not evaluated in Phase 33 path | — |

### Legacy `verification_results` (not in Performance Center)

| Market | correct | wrong |
|--------|--------:|------:|
| 1x2 | 13 | 3 |
| over_under_2_5 | 10 | 6 |
| halftime_bucket | 9 | 7 |
| first_goal_team | 3 | 13 |
| first_goal_scorer | 0 | 2 |
| scoreline_exact | 3 | 1 |

These **70 rows** represent a **separate accuracy pipeline** (pre–Phase 42D Performance Center) and are **not merged** into `/api/performance/summary`.

---

## 10. Recommendation

### Should we execute a full historical evaluation backfill?

**No — not as a single full backfill right now.**

### Recommended next steps (ordered)

1. **Enable automatic evaluation**  
   Install and enable `worldcup-evaluate-results.timer` (every 6h) or `worldcup-auto-cycle.timer` on production **after** operator approval. This prevents future gaps as WC 2026 matches complete.

2. **Quarantine invalid test evaluations**  
   Treat fixture IDs **1489393** and **1539007** as **non-authoritative** until matches finish. Optionally plan a one-time **re-evaluate on FT** (same job, no prediction mutation) to replace bogus `2-1` rows.

3. **Do not bulk-backfill yet**  
   With **0 eligible** stored+finished pairs, a backfill job today would **not increase** meaningful coverage.

4. **Optional Phase 44B — legacy payload recovery (small scope)**  
   Investigate reconstructing `worldcup_stored_predictions` for **4 finished WC fixtures** from legacy `predictions` + `prediction_markets` if full payloads are recoverable. Cache is **empty** for those IDs; success uncertain.

5. **Keep JSONL / verification separate unless unified**  
   Merging 542 verification JSONL lines or 70 SQLite verification rows into Performance Center requires an explicit **dedupe + schema** design (Phase 42A noted triple-store architecture).

6. **PostgreSQL user history**  
   9 rows are **read-time evaluated** in API responses but **not** written back to PG; this is orthogonal to Performance Center and should not be mixed into global winrate without a separate decision.

---

## Data sources used

| Source | Path / module |
|--------|----------------|
| Production SQLite | `/opt/worldcup-predictor/data/football_intelligence.db` |
| Production JSONL | `/opt/worldcup-predictor/data/predictions/`, `verification/`, `results/` |
| Production PostgreSQL | `user_prediction_history` via `.env.production` |
| Evaluation pipeline | `worldcup_predictor/automation/worldcup_background/result_evaluation_job.py` |
| Evaluator | `worldcup_predictor/automation/worldcup_background/pick_evaluator.py` |
| Performance API | `worldcup_predictor/api/performance_center.py` |
| Systemd (planned) | `deployment/systemd/worldcup-evaluate-results.{service,timer}` |
| Prior deploy notes | `PHASE_33_33B_DEPLOYMENT_AND_NO_BET_UX_REPORT.md` |

---

## Appendix — Production stored predictions snapshot

| fixture_id | source | kickoff_utc | status | evaluated |
|------------|--------|-------------|--------|-----------|
| 1489399 | background_daily | 2026-06-22T17:00 | NS | — |
| 1539017 | background_daily | 2026-06-22T21:00 | NS | — |
| 1489401 | background_daily | 2026-06-23T00:00 | NS | — |
| 1489400 | background_daily | 2026-06-23T03:00 | NS | — |
| 1539007 | phase35_test | 2026-06-20T17:00 | NS | ⚠️ test eval |
| 1489393 | user_predict | 2026-06-20T20:00 | NS | ⚠️ test eval |
| 1489394–1489398, 1489395, 1489396 | user_predict | various | NS | — |

---

## Final status

```
PHASE_44_STATUS = AUDIT_COMPLETE
PHASE_44_BACKFILL = NOT_RECOMMENDED_YET
BLOCKERS = [invalid_test_eval_rows, no_scheduler, zero_eligible_stored_finished_pairs]
NEXT_ACTION = enable_scheduled_evaluation + re-evaluate_after_real_FT
```

**STOP — Report only. No backfill implemented.**
