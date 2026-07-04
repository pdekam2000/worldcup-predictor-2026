# EVAL-COVERAGE-1 — Final Report

Phase: **EVAL-COVERAGE-1** | Status: Complete — **DO NOT PROMOTE S5**

## Final Recommendation: `NO_UNEVALUATED_FINISHED_FIXTURES`

S5 promotion gate: **`S5_NEEDS_MORE_DATA`** (blocked — **0 ECSE research sample on production**)

Validation: **18/18 passed** (Hetzner + local)

---

## Executive Summary

Production audit on Hetzner (`/opt/worldcup-predictor`, canonical DB) reveals a **critical gap**: **`ecse_prediction_snapshots` is empty (0 rows)**. All prior S5 / Top3 / Top10 shadow research (13 knockout matches, 61.5% S5) ran against the **local dev DB**, not production.

| Finding | Production (Hetzner) | Prior research (local) |
|---------|---------------------:|----------------------:|
| Finished WC fixtures | 317 | 13 (knockout) |
| ECSE snapshots | **0** | 13+ |
| ECSE research sample | **0** | 13 |
| WDE stored (finished) | 33 | — |
| WDE evaluations | 34 | — |
| Pending WDE/ECSE eval | **0** | — |
| Finished with result, no prediction | **284** | — |

**Results/eval pipeline:** Dry-run and controlled real runs completed safely with **0 new syncs** and **0 new evaluations** — backlog is clear, but **ECSE snapshots must be generated before End Result optimizer metrics can expand on production**.

---

## PART A — Before / After Evaluation Coverage

| Metric | Before | After | Δ |
|--------|-------:|------:|--:|
| Finished WC | 317 | 317 | +0 |
| Finished with 90' result | 317 | 317 | +0 |
| ECSE research sample | 0 | 0 | +0 |
| ECSE pending eval | 0 | 0 | +0 |
| WDE pending eval | 0 | 0 | +0 |
| WDE evaluations | 34 | 34 | +0 |

Full table: `EVAL_COVERAGE_1_AUDIT.md`

**Unevaluated finished fixtures found:** **0** (all 33 finished fixtures with WDE stored predictions already have evaluation rows).

**Coverage gap (different issue):** **284** finished WC fixtures have results but **no stored WDE prediction**; **317** finished fixtures have **no ECSE snapshot**.

---

## PART B — Dry-run Results/Eval Pipeline

Dry-run **supported** (`--dry-run` flag on `run_production_prediction_pipeline.py`).

| Mode | Exit | Would sync results | Would evaluate | DB writes | Provider calls |
|------|------|-------------------:|---------------:|-----------|----------------|
| `results-only --dry-run` | 0 | 0 | 0 | none | none |
| `eval-only --dry-run` | 0 | 0 | 0 | none | none |

Warnings: none. Stored predictions stable at 48 before/after dry-run.

---

## PART C — Controlled Real Results/Eval Run

Executed manually on Hetzner (safe — no pending backlog):

```bash
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode results-only
.venv/bin/python scripts/run_production_prediction_pipeline.py --mode eval-only
```

| Mode | Exit | Results synced | Evaluated | Errors |
|------|------|---------------:|----------:|--------|
| `results-only` | 0 | 0 | 0 | 0 |
| `eval-only` | 0 | 0 | 0 | 0 |

No fake rows created. No timers enabled. WDE/ECSE production logic unchanged.

---

## PART D — Research Metrics (Production DB)

Re-ran on Hetzner after audit:

```bash
python scripts/run_top3_endresult_optimizer_1.py
python scripts/run_ecse_rerank_1_shadow_analysis.py
```

| Metric | Production | Prior local research |
|--------|------------|---------------------|
| Finished ECSE eval sample | **0** | 13 |
| Raw ECSE Top1 | N/A | 15.4% |
| Raw ECSE Top3 | N/A | 53.8% |
| Raw ECSE Top5 | N/A | 76.9% |
| S5 optimized Top3 | N/A | 61.5% |

**Segment metrics:** unavailable on production (n=0). Cannot reproduce 53.8% / 61.5% on canonical DB until ECSE snapshots exist for finished fixtures.

---

## PART E — Odds Freshness

See `EVAL_COVERAGE_1_ODDS_FRESHNESS_SUMMARY.md`.

| Question | Answer |
|----------|--------|
| Stale odds on evaluated ECSE fixtures? | **0** (no ECSE evaluated fixtures) |
| Unknown odds? | **0** |
| Top5 worse on stale odds? | **Untestable** (n=0) |
| ODDS-FRESHNESS-1 before promotion? | **Yes**, but **ECSE snapshot backfill is prerequisite** |

---

## PART F — S5 Promotion Gate

| Check | Status |
|-------|--------|
| evaluated_matches ≥ 40 | **Fail** (0/40) |
| S5 Top3 ≥ 58% | **Fail** (no sample) |
| S5 − raw Top3 ≥ +5pp | **Fail** |
| S5 best or tied best | N/A |
| No major segment regression | Pass (vacuous) |
| Odds freshness not invalidating | Pass (vacuous) |

**Gate decision:** `S5_NEEDS_MORE_DATA`

Even if local 61.5% held, production has **zero** ECSE evaluation rows — promotion is blocked.

**Do NOT promote S5.**

---

## PART G — Validation

Script: `scripts/validate_eval_coverage_1.py`

Checks: audit runs, no DB overwrite during validation, no prediction generation in this phase, WDE/ECSE unchanged, promotion gate evaluated, reports exist, timers not enabled.

---

## Next Recommended Phase

1. **ECSE snapshot backfill on production** — populate `ecse_prediction_snapshots` for finished WC fixtures with stored WDE (prerequisite for any End Result optimizer evaluation at scale).
2. **KEEP_COLLECTING_EVALUATIONS** — 284 finished matches still lack any stored prediction.
3. **ODDS-FRESHNESS-1** — after ECSE sample exists; segment stale vs fresh before trusting S5 metrics.
4. **DO NOT ENABLE timers** for predictions until ECSE coverage gap is understood.
5. **DO NOT PROMOTE S5** — shadow-only until production n≥40 with ECSE snapshots.

**Not recommended now:** `OWNER_PREVIEW_S5`, `ENABLE_RESULTS_TIMER_ONLY` (eval backlog clear but ECSE gap blocks research validation).

---

STOP — No promotion. No timers. Shadow S5 remains research-only.
