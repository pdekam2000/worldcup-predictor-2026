# PHASE 61B — Production EGIE + Unified Validation

**Generated:** 2026-06-26T13:46:07Z (production server `91.107.188.229`)  
**Mode:** Production validation only — **no flags changed**, **no public rollout**  
**Script:** `scripts/validate_phase61b_production_egie_unified.py`  
**Raw JSON:** `data/validation/phase61b_production_validation.json`

---

## Executive summary

Production PostgreSQL is **healthy** and contains **90 goal_timing prediction rows** and **107 feature snapshots**, but they do **not overlap** with the **56 World Cup 2026** cached Classic predictions used for the backtest. EGIE production cache is **Premier League–scoped** (sample fixture: Sheffield Utd vs Tottenham, `competition_key=premier_league`). Hybrid confidence snapshots are **not persisted** (`hybrid_confidence_rows=0`). Only **4 WC evaluations** exist in SQLite — far below the 20+ needed for a rollout decision.

### Final recommendation: **`NEED_MORE_DATA`**

Public rollout is **not** supported. Continue **admin preview only** with flags unchanged.

---

## Flag state (unchanged — verified)

| Flag | Value |
|------|-------|
| `UNIFIED_ENGINE_ENABLED` | `false` |
| `UNIFIED_ENGINE_PUBLIC` | `false` |
| `UNIFIED_ENGINE_ADMIN_PREVIEW` | `true` |
| `UNIFIED_ENGINE_COMPARE_MODE` | `true` |

**No production output was changed.**

---

## Part A — Production data validation

### PostgreSQL connectivity

| Check | Result |
|-------|--------|
| PostgreSQL configured | ✅ Yes |
| Connection on production | ✅ Success |
| `goal_timing_predictions` | **90 rows** |
| `goal_timing_features` | **107 rows** |
| `goal_timing_evaluations` | **1 row** |
| `goal_timing_agents` table | ❌ Not deployed (undefined table) |
| `hybrid_confidence_snapshot` populated | **0 rows** |
| `active_egie_predictions` (`no_prediction_flag=false`) | **0** (query); rows exist but flagged or WC mismatch |

### SQLite (Classic / archive)

| Check | Result |
|-------|--------|
| Stored predictions (WC 2026) | **56** |
| Stored predictions (all comps) | **56** (only `world_cup_2026`) |
| Evaluations (WC) | **4** |
| Evaluations (all) | **4** |

### Survival dataset

- No survival artifact paths on production server under standard artifact locations.

### Missing / gap analysis

1. **Competition mismatch** — EGIE PG cache is PL-focused; Classic SQLite cache is WC-only → **0 EGIE picks** in WC backtest.
2. **Hybrid confidence** — not stored in PG (`hybrid_confidence_rows=0`).
3. **Evaluations** — only 4 finished WC evaluations; 50+ fixtures still pending.
4. **xG / lineups** — provider hits: odds **50/56**, xG **0**, lineups **0** for WC fixtures.
5. **Survival** — not available on production host.

---

## Part B — Large backtest (`limit=500`, actual n=56)

Fixtures sampled: **56** (all available WC stored predictions).

### Market-by-market comparison

| Market | Classic acc | Classic cov | EGIE acc | EGIE cov | Unified acc | Unified cov | Settled (Classic) |
|--------|-------------|-------------|----------|----------|-------------|-------------|-------------------|
| **1X2** | **83.3%** | 100% | — | 0% | **83.3%** | 73.2% | 5/6 correct |
| **BTTS** | — | 78.6% | — | 0% | — | 78.6% | 0 settled |
| **Over/Under** | — | 78.6% | — | 0% | — | 96.4% | 0 settled |
| **First Goal Team** | — | 0% | — | 0% | — | 0% | — |
| **Goal Range** | — | 0% | — | 0% | — | 0% | — |
| **Goal Minute Soft** | — | 0% | — | 0% | — | 0% | — |

### Calibration / tier performance (Unified)

| Tier | Count (best tip) | Notes |
|------|------------------|-------|
| A | 0 | No tier-A tips in sample |
| B | 9 | ~16% of fixtures |
| C | 43 | Majority bucket |
| D | 4 | Low confidence |

**Confidence buckets:** Most unified picks land in **Tier C** — calibration is conservative but **not validated** against settled multi-market outcomes (insufficient evals).

### Coverage

| Arm | 1X2 pick coverage | EGIE goal markets |
|-----|-------------------|-------------------|
| Classic | 56/56 (100%) | 0 (no FG in classic payload for WC) |
| EGIE | 0/56 | 0 (no WC fixture overlap in PG) |
| Unified | 41/56 classic-sourced 1X2 + hybrid FG markets without EGIE data | Synthetic hybrid only |

### ROI analysis

- **Odds available:** 50/56 fixtures (SQLite odds snapshots).
- **ROI not computed** — fewer than 20 settled evaluations per market; only 1X2 has 6 settled results. Insufficient for meaningful ROI / edge analysis.

---

## Part C — Hybrid contribution analysis

### Source engine by market (fixture counts)

| Market | Classic | EGIE | Hybrid |
|--------|---------|------|--------|
| 1X2 | 41 | 0 | 15 |
| BTTS | 44 | 0 | 12 |
| Over/Under | 54 | 0 | 2 |
| First Goal Team | 0 | 0 | 56 |
| Goal Range | 0 | 0 | 56 |
| Goal Minute Soft | 0 | 0 | 56 |

### Interpretation

| Question | Answer |
|----------|--------|
| Which engine contributed most? | **Classic** for 1X2/BTTS/O/U; **Hybrid layer only** for goal markets (no real EGIE data for WC) |
| Did Unified outperform Classic? | **No meaningful difference** on 1X2 (same 83.3% on 6 settled); unified has lower 1X2 coverage (73%) |
| Did Unified outperform EGIE? | **Cannot measure** — EGIE coverage 0% for WC sample |
| Provider improved results? | **Odds** present on 50 fixtures; **xG/lineups absent** for WC — no measurable lift |
| Provider added noise? | Goal-market hybrid picks without EGIE cache are **low-confidence (Tier C)** — potential noise if shown publicly |

---

## Part D — GO / NO-GO decision

### **`NEED_MORE_DATA`**

| Gate | Status |
|------|--------|
| Unified ≥ Classic accuracy | ⚠️ Tied on 1X2 (n=6 only) — **not statistically valid** |
| No major regression | ✅ No regression detected on tiny sample |
| Confidence calibration acceptable | ❌ Tier C dominant; hybrid confidence not in PG |
| Coverage acceptable | ❌ EGIE 0% on WC; goal markets unvalidated |
| Evaluations ≥ 20 | ❌ Only **4** WC evaluations |

**Not eligible:** `READY_FOR_PUBLIC_ROLLOUT`  
**Appropriate now:** `ADMIN_PREVIEW_ONLY` (flags already set for admin preview)

---

## Part E — Recommended deployment flags

Keep exactly as-is until WC EGIE cache + evaluations mature:

```env
UNIFIED_ENGINE_ENABLED=false
UNIFIED_ENGINE_PUBLIC=false
UNIFIED_ENGINE_ADMIN_PREVIEW=true
UNIFIED_ENGINE_COMPARE_MODE=true
```

### Required before re-validation (61C suggestion)

1. Run EGIE prefetch for **world_cup_2026** fixtures (or backtest on **premier_league** where 90 EGIE rows exist).
2. Persist **hybrid_confidence_snapshot** on goal_timing predictions.
3. Accumulate **≥100 settled evaluations** across 1X2 + goal markets.
4. Backfill **xG/lineups** for WC fixtures in provider feature store.
5. Re-run: `PHASE61B_BACKTEST_LIMIT=500 .venv/bin/python scripts/validate_phase61b_production_egie_unified.py` on production.

---

## Rollback / safety

- No code deployed to production API (validation script + `unified_hybrid` copied for read-only analysis only).
- No flags toggled.
- Public users remain on **Classic/WDE production output**.

---

**STOP — public unified engine NOT enabled. Awaiting more production data before re-validation.**
