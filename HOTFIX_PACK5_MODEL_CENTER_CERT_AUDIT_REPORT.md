# HOTFIX PACK 5 — Model Center Certification Audit

**Mode:** Read-only audit (no deploy, no engine changes)  
**Date:** 2026-06-20  
**Production host:** `91.107.188.229` (`/opt/worldcup-predictor/data/football_intelligence.db`)  
**UI surface:** Owner → `/owner/model-center` → `GET /api/owner/model-center`

---

## Executive summary

Model Center shows **PREDS = 0 · EVAL = 0 · PENDING = 0 · CERT = BLOCKED** for every market due to **two independent failures**:

| # | Issue | Severity | Effect |
|---|--------|----------|--------|
| **RC-1** | **Metrics key mismatch** in `OwnerPlatformService.model_center()` | **Display bug** | Counters always zero even when autonomous data exists (102 snapshots / 102 eval rows on production) |
| **RC-2** | **Autonomous eval pipeline never re-scores `pending` rows** after matches finish | **Data pipeline bug** | `evaluated` stays 0 → certification logic returns `BLOCKED` |
| **RC-3** | **Wrong data plane** — Model Center reads Phase-61 autonomous tables only | **Architecture gap** | Ignores `worldcup_stored_predictions` (56), `worldcup_prediction_evaluations` (6), `predops_snapshots` (94), shadow JSONL |

Certification labels are technically populated (`production:1x2` → `BLOCKED`) but use a **generic token** with no reason code. Counters are wrong because of RC-1.

---

## Architecture — what Model Center actually reads

```
OwnerModelCenter.jsx
  └─ fetchOwnerModelCenter()  →  GET /api/owner/model-center
       └─ OwnerPlatformService.model_center()
            └─ AutonomousPerformanceService.certification_summary()
                 ├─ autonomous_certification_runs  (latest report_json)
                 └─ autonomous_snapshot_evaluations  (latest_evaluated list only)
```

**Model Center does NOT query:**

- `worldcup_stored_predictions`
- `worldcup_prediction_evaluations`
- `predops_snapshots`
- `data/shadow/*.jsonl`
- EGIE / WDE engines directly

---

## Per-card data source mapping

### Production Engine cards

| Market | PREDS source (intended) | PREDS source (actual API) | EVAL | PENDING | WINRATE | CERT |
|--------|-------------------------|---------------------------|------|---------|---------|------|
| `1x2` | `autonomous_prediction_snapshots` WHERE `engine='production'` | **Broken lookup → 0** | `autonomous_snapshot_evaluations` `correct+wrong` | same table `status='pending'` | `correct/(correct+wrong)` | `certification_levels['production:1x2']` from latest `autonomous_certification_runs` |
| `double_chance` | same | **0** | same | same | same | `production:double_chance` |
| `btts` | same | **0** | same | same | same | `production:btts` |
| `over_under_2_5` | same | **0** | same | same | same | `production:over_under_2_5` |
| `correct_score` | same (no prod snapshots on server) | **0** | same | same | same | `production:correct_score` |

### Elite Engine cards (adds 4 markets)

| Market | Notes |
|--------|-------|
| `goal_timing` | No `elite_shadow` snapshots on production → all metrics 0 |
| `first_goal_team` | same |
| `team_to_score_first` | same |
| `goalscorer` | Production has **20 `production` engine** goalscorer snapshots (mis-tagged engine on elite card) |

Elite card calls `_market_rows("elite_shadow", …)` but production DB has **zero** `engine='elite_shadow'` rows. Shadow research lives in JSONL (`elite_orchestrator_predictions.jsonl` ~538 lines) — **not wired**.

---

## Certification thresholds (Phase 61)

From `worldcup_predictor/autonomous/performance_certification.py`:

| Level | Min evaluated (`correct+wrong`) | Min winrate |
|-------|--------------------------------|-------------|
| `PRODUCTION_READY` | 30 | 52% |
| `PAPER_READY` | 15 | 48% |
| `RESEARCH_ONLY` | 5 | 0% (any winrate) |
| `BLOCKED` | &lt; 5 evaluated | — |

`_certify()` uses **only** `correct + wrong`. Rows with `status='pending'` do **not** count toward evaluated.

---

## Production row counts (verified 2026-06-20)

### Primary tables

| Table / store | Row count | Used by Model Center? |
|---------------|-----------|------------------------|
| `worldcup_stored_predictions` | **56** | ❌ No |
| `worldcup_prediction_evaluations` | **6** | ❌ No |
| `autonomous_prediction_snapshots` | **102** | ✅ Yes (but not displayed — RC-1) |
| `autonomous_snapshot_evaluations` | **102** | ✅ Yes (aggregated into cert report) |
| `autonomous_certification_runs` | **15** | ✅ Yes (latest report drives UI) |
| `predops_snapshots` | **94** | ❌ No |
| `data/shadow/*.jsonl` | **~7,516 lines** total | ❌ No |

### Autonomous snapshots by engine × market (production)

| engine | market_id | snapshots |
|--------|-----------|-----------|
| production | 1x2 | 22 |
| production | btts | 20 |
| production | double_chance | 20 |
| production | goalscorer | 20 |
| production | over_under_2_5 | 20 |
| elite_shadow | *any* | **0** |

### Autonomous evaluations by status (production)

| engine | market_id | status | count |
|--------|-----------|--------|-------|
| production | 1x2 | **pending** | 22 |
| production | btts | **pending** | 20 |
| production | double_chance | **pending** | 20 |
| production | goalscorer | **pending** | 20 |
| production | over_under_2_5 | **pending** | 20 |
| *all* | *all* | correct | **0** |
| *all* | *all* | wrong | **0** |

### World Cup evaluation rows (separate pipeline — Hotfix Pack 2)

| market column | non-null count (of 6 rows) |
|---------------|---------------------------|
| `market_1x2_status` | 6 |
| `market_ou_status` | 6 |
| `market_btts_status` | 6 |
| `market_cs_status` | 4 |
| `market_fg_team_status` | 4 |
| `market_goal_minute_status` | 4 |

These are produced by `worldcup_background/result_evaluation_job.py` → `upsert_worldcup_prediction_evaluation()`. **Not connected to Model Center.**

### Latest certification report on production (run #15, 2026-06-25)

```json
"markets": {
  "1x2": {
    "production": {
      "pending": 22,
      "evaluated": 0,
      "correct": 0,
      "wrong": 0,
      "winrate": null,
      "certification": "BLOCKED"
    },
    "elite_shadow": { "evaluated": 0, "certification": "BLOCKED" }
  }
}
```

`certification_levels` correctly includes `production:1x2` → `BLOCKED` (and all other production markets).

---

## Root cause analysis

### RC-1 — Counter display bug (PREDS / EVAL / PENDING all zero)

**File:** `worldcup_predictor/owner/platform_service.py` → `model_center()` → `_market_rows()`

```python
key = f"{engine_key}:{m}"
metrics = markets.get(key) or markets.get(m) or {}
```

**Actual report shape** from `run_performance_certification()`:

```python
result.markets[market] = {
    "production": { "evaluated": 0, "pending": 22, ... },
    "elite_shadow": { ... },
}
```

Lookup expects `markets["production:1x2"]` or flat `markets["1x2"]` as metrics dict — but `markets["1x2"]` is a **nested** `{engine: metrics}` object. Result: empty `{}` → all counters default to **0**.

**Local proof:**

| Lookup | `1x2` production row |
|--------|-------------------|
| Current (broken) | `predictions=0, evaluated=0, pending=0` |
| Fixed nested access | `predictions=4, evaluated=0, pending=4` (local DB) |
| Production equivalent | `predictions=22, evaluated=0, pending=22` |

**PREDS field:** `aggregate_performance()` never returns `total` or `predictions`. Even after RC-1 fix, PREDS should be `evaluated + pending` or a separate `COUNT(*)` from `autonomous_prediction_snapshots`.

---

### RC-2 — Certification BLOCKED (evaluated = 0)

**File:** `worldcup_predictor/autonomous/evaluation_engine.py`

`run_autonomous_evaluations()` only processes snapshots **without any evaluation row**:

```sql
LEFT JOIN autonomous_snapshot_evaluations e ON e.snapshot_id = s.id
WHERE e.id IS NULL
```

**Lifecycle failure:**

1. Autonomous cycle runs before kickoff → inserts eval row with `status='pending'` (`fixture_not_finished`).
2. Match finishes → row already exists → **never re-queued**.
3. `aggregate_performance()` → `evaluated = correct + wrong = 0`.
4. `_certify()` → `evaluated < 5` → **`BLOCKED`**.

Meanwhile `worldcup_prediction_evaluations` **does** get updated for finished fixtures (6 rows) via a **different job** — but Model Center never reads it.

**Intended reason code:** `NOT_ENOUGH_EVALUATIONS (0/5)` or `WAITING_DATA (0/30)` — not generic `BLOCKED`.

---

### RC-3 — Data plane disconnect (user expectation vs implementation)

Users see stored predictions, evaluated results (`/results`), PredOps, and shadow research elsewhere in the product. Model Center was built for **Phase 61 autonomous certification** only.

| User-visible data | Location | Model Center visibility |
|-------------------|----------|-------------------------|
| Public WC predictions | `worldcup_stored_predictions` | None |
| Finished eval UI (Pack 3) | `worldcup_prediction_evaluations` | None |
| PredOps intelligence | `predops_snapshots` | None |
| Elite shadow research | `data/shadow/elite_orchestrator_*.jsonl` | None |
| Autonomous immutable snapshots | `autonomous_prediction_snapshots` | Exists but hidden (RC-1) |

This is **not** a missing-data problem on production — it is a **wrong-source / broken-bridge** problem.

---

## Why CERT shows generic `BLOCKED`

1. `certification_levels['production:1x2']` resolves correctly to `"BLOCKED"`.
2. `_certify()` returns only the enum string — **no `reason_code` or progress fraction**.
3. `OwnerModelCenter.jsx` `CertBadge` renders `level` verbatim — no mapping to `WAITING_DATA (6/50)`.

**Policy mapping (proposed, not implemented):**

| Condition | Display label |
|-----------|---------------|
| `evaluated < 5` | `WAITING_DATA (N/5)` → reason `NOT_ENOUGH_EVALUATIONS` |
| `5 ≤ evaluated < 15` | `LOW_SAMPLE (N/15)` → `LOW_SAMPLE_SIZE` |
| `evaluated ≥ 15` but winrate &lt; 48% | `LOW_WINRATE (XX%)` |
| `engine == elite_shadow` and snapshots = 0 | `SHADOW_RESEARCH_ONLY` |
| `AUTONOMOUS_PLATFORM_ENABLED=false` | `CERTIFICATION_DISABLED` |
| RC-1 masking pending | *(currently shows 0 pending — hides `WAITING_DATA`)* |

---

## Card-by-card expected vs displayed (production)

| Card | True PREDS | True PENDING | True EVAL | True CERT reason | UI today |
|------|------------|--------------|-----------|------------------|----------|
| Prod · 1x2 | 22 | 22 | 0 | `NOT_ENOUGH_EVALUATIONS (0/5)` | 0 / 0 / 0 / BLOCKED |
| Prod · btts | 20 | 20 | 0 | same | 0 / 0 / 0 / BLOCKED |
| Prod · double_chance | 20 | 20 | 0 | same | 0 / 0 / 0 / BLOCKED |
| Prod · over_under_2_5 | 20 | 20 | 0 | same | 0 / 0 / 0 / BLOCKED |
| Prod · correct_score | 0 | 0 | 0 | `NO_SNAPSHOTS` | 0 / 0 / 0 / BLOCKED |
| Elite · all markets | 0 | 0 | 0 | `SHADOW_RESEARCH_ONLY` | 0 / 0 / 0 / BLOCKED |
| Elite · goalscorer* | *20 prod mis-bucketed* | 20 | 0 | mislabeled engine | 0 / 0 / 0 / BLOCKED |

\*Goalscorer snapshots exist under `engine='production'`, not `elite_shadow`.

---

## Proposed fix (Hotfix Pack 5 — implementation phase, post-audit)

**Scope:** Owner platform + autonomous eval plumbing only. **No changes** to WDE, EGIE, scoring, calibration, billing, subscriptions.

### Fix A — Display (RC-1) · `platform_service.py`

```python
# Replace flat lookup with nested engine access
bucket = markets.get(m) or {}
metrics = bucket.get(engine_key) if isinstance(bucket, dict) else {}
if not metrics and isinstance(bucket, dict) and "evaluated" in bucket:
    metrics = bucket  # backward compat if flat

predictions = metrics.get("evaluated", 0) + metrics.get("pending", 0)
# Optional: query snapshot COUNT for preds if pending rows missing
```

### Fix B — Re-evaluation (RC-2) · `autonomous/store.py` + `evaluation_engine.py`

- Add `list_snapshots_pending_revaluation()` → eval rows where `status='pending'` and fixture is finished.
- Re-run `evaluate_stored_prediction` and **UPDATE** (or upsert) eval status to `correct`/`wrong`.
- Alternatively: delete stale `pending` rows and re-insert on completion cycle.

### Fix C — Reason-coded certification · `performance_certification.py` + UI

Extend `_certify()` return:

```python
{
  "level": "BLOCKED",
  "reason_code": "NOT_ENOUGH_EVALUATIONS",
  "label": "WAITING_DATA (0/5)",
  "evaluated": 0,
  "required": 5,
}
```

Update `CertBadge` to show `label` when present.

### Fix D — Production truth bridge (optional, larger)

Add read-only aggregation from `worldcup_prediction_evaluations` for **Production Engine** public WDE metrics (parallel row or “WDE Live” section), without replacing autonomous immutable snapshots.

PredOps / shadow: surface as **research-only** badges (`SHADOW_RESEARCH_ONLY`) — do not mix into certification denominators without explicit policy.

### Validation script (post-fix)

`scripts/validate_hotfix_pack5_model_center_cert.py`:

1. Seed autonomous pending + finished fixture → re-eval → `evaluated > 0`.
2. Call `model_center()` → assert `pending > 0` or `evaluated > 0` matches DB.
3. Assert cert label contains reason code, not bare `BLOCKED` when `evaluated < 5`.
4. Production smoke: `GET /api/owner/model-center` (owner auth).

---

## Files referenced

| File | Role |
|------|------|
| `base44-d/src/pages/owner/OwnerModelCenter.jsx` | UI table |
| `base44-d/src/api/saasApi.js` | `fetchOwnerModelCenter()` |
| `worldcup_predictor/api/routes/owner.py` | Route |
| `worldcup_predictor/owner/platform_service.py` | **`model_center()` — RC-1** |
| `worldcup_predictor/admin/autonomous_performance.py` | `certification_summary()` |
| `worldcup_predictor/autonomous/performance_certification.py` | Thresholds + `_certify()` |
| `worldcup_predictor/autonomous/store.py` | Snapshots, evals, aggregates |
| `worldcup_predictor/autonomous/evaluation_engine.py` | **RC-2 pending trap** |
| `worldcup_predictor/automation/worldcup_background/result_evaluation_job.py` | WC evals (disconnected) |
| `worldcup_predictor/predops/store.py` | PredOps snapshots (disconnected) |

---

## Audit conclusion

| Question | Answer |
|----------|--------|
| Why PREDS = EVAL = PENDING = 0? | **RC-1:** nested `markets[market][engine]` not read; metrics dict always empty. |
| Why CERT = BLOCKED? | **RC-2:** 0 `correct`/`wrong` autonomous evals; all 102 rows stuck `pending`; `_certify` requires ≥5 evaluated. Secondary: no reason-code UX. |
| Is production data missing? | **No.** 56 stored preds, 6 WC evals, 94 PredOps snaps, 102 autonomous snaps — Model Center reads the wrong store and mis-parses the one it does read. |
| Safe to deploy fix? | Audit complete. Implementation can proceed as Hotfix Pack 5 without touching WDE/EGIE/scoring/calibration/billing. |

**Status:** `AUDIT_COMPLETE` — awaiting implementation approval (no deploy in this phase).
