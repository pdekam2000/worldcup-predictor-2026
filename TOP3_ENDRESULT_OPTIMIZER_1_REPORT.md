# TOP3-ENDRESULT-OPTIMIZER-1 — Final Report

Phase: **TOP3-ENDRESULT-OPTIMIZER-1** | Status: Shadow complete — **DO NOT PROMOTE**

## Final Recommendation

**TOP3_OPTIMIZER_PROMISING_NEEDS_MORE_DATA**

Validation: **32/32 passed** | Sample: **13 finished matches** | 89% target: **NOT achieved (unrealistic on current data)**

---

## Executive Summary

Built a shadow-only **3-candidate End Result portfolio optimizer** with 6 strategy variants. Best performer on current sample:

| Strategy | Top3 Hit Rate | Δ vs raw Top3 |
|----------|---------------|---------------|
| **S5 Conservative high-coverage** | **61.5% (8/13)** | **+7.7 pp** |
| S0 Baseline raw Top3 | 53.8% (7/13) | — |
| S4 Hybrid hedge | 46.2% (6/13) | −7.7 pp |

**89% is not observed and is unrealistic on n=13** (would require 12/13 hits; best achieved 8/13).

---

## Baseline (Part A)

| Metric | Value |
|--------|-------|
| Top 1 exact | 15.4% |
| Raw ECSE Top 3 | 53.8% |
| Raw ECSE Top 5 | 76.9% |
| Correct score at Rank 2–4 | 8/13 (61.5%) |
| In Top5 but outside Top3 | 3/13 |
| Clean-sheet Top 1 | 92.3% |

See `TOP3_ENDRESULT_OPTIMIZER_1_BASELINE.md` for full rank distribution and bias analysis.

---

## Strategy Backtest Results (Part C/D)

All strategies select **exactly 3** candidates per fixture. Evaluation uses **90-minute score** only.

| ID | Strategy | Top3 Hit | Gained | Lost | Notes |
|----|----------|----------|--------|------|-------|
| S0 | Baseline raw Top3 | 53.8% | 0 | 0 | ECSE ranks 1–3 |
| S1 | Top5 market consistency | 53.8% | 2 | 2 | Net zero; swaps within Top5 |
| S2 | Top10 portfolio diversity | 53.8% | 2 | 2 | Net zero |
| S3 | Archetype portfolio | 53.8% | 5 | 5 | High churn; net zero |
| S4 | Hybrid hedge | 46.2% | 1 | 2 | **Worse** than baseline |
| **S5** | **Conservative coverage** | **61.5%** | **2** | **1** | **Best — net +1 hit** |

### Segment notes

- **Knockout:** all 13 finished matches (no group-stage finished ECSE rows yet)
- **Stale odds:** all 13
- **Fresh odds:** 0 matches
- **AET/PEN flagged:** 4 matches (90' score still used)

---

## Match-Level Improvements (S5 vs raw Top3)

| Match | Actual | Raw Top3 | S5 Top3 | Raw | S5 |
|-------|--------|----------|---------|-----|-----|
| Brazil vs Japan | 2-1 | 1-0 · 2-0 · 1-1 | 1-1 · **2-1** · 3-0 | N | **Y** |
| Portugal vs Croatia | 2-1 | 1-0 · 2-0 · 1-1 | 1-0 · 1-1 · **2-1** | N | **Y** |
| Switzerland vs Algeria | 2-0 | 1-0 · 1-1 · 2-0 | 1-0 · 1-1 · 2-1 | Y | N |

**Net:** +2 gained (Brazil, Portugal), −1 lost (Switzerland), **+1 overall**.

Still missing: Belgium 3-2, England 2-1, Germany 1-1, Mexico 2-0 (actual outside optimized Top3 or not in ECSE Top10).

---

## Rank Distribution Insight

Actual correct score ECSE ranks (n=13):

- Rank 1: 15.4%
- Rank 2: 23.1%
- Rank 3: 15.4%
- Rank 4: 23.1%
- Miss: 23.1%

**Top 5 contains enough signal** (76.9% coverage). Optimized Top3 should pull from Rank 2–5 when WDE markets contradict clean-sheet Top1 pattern.

---

## Can Optimized Top3 Reach 89%? (Part E)

| Sample | Required hits for 89% | Best achieved (S5) | Achieved rate |
|--------|----------------------|-------------------|---------------|
| **13 matches** | **12/13** | **8/13** | **61.5%** |
| 30 matches (projected) | 27/30 | — | needs 30+ finished |
| 50 matches (projected) | 45/50 | — | needs 50+ finished |

**Verdict:**
- **89% not observed** on any strategy
- **89% unrealistic** on current 13-match knockout sample
- Even perfect selection from Top5 caps at **~77%** if Top5 coverage holds
- Theoretical ceiling with perfect oracle Top3 from Top10 ≈ depends on rank clustering; current data suggests **65–75%** may be achievable with more tuning — **not 89%**

**Confidence warning:** All rates are unstable below **30–50 finished matches**.

---

## Trade-offs

| Effect | S5 Conservative |
|--------|-----------------|
| Gained hits vs raw Top3 | +2 |
| Lost hits vs raw Top3 | −1 |
| Selected correct outside raw Top3 | Yes (Brazil, Portugal) |
| Lost raw Top3 hits | Yes (Switzerland) |

Strategies S1–S3 show equal gain/loss (net zero) — rearranging without net benefit on this sample.

---

## Deliverables (Part F)

| Artifact | Path |
|----------|------|
| JSON results | `artifacts/top3_endresult_optimizer_1_results.json` |
| CSV | `artifacts/top3_endresult_optimizer_1_results.csv` |
| Match-level MD | `artifacts/top3_endresult_optimizer_1_match_level.md` |
| Baseline audit | `TOP3_ENDRESULT_OPTIMIZER_1_BASELINE.md` |
| Validation | `artifacts/top3_endresult_optimizer_1_validation.json` |

### Code

```
worldcup_predictor/research/top3_endresult_optimizer/
  features.py
  candidate_pool.py
  optimizer.py
  evaluator.py
  runner.py
scripts/run_top3_endresult_optimizer_1.py
scripts/validate_top3_endresult_optimizer_1.py
```

---

## UI / Production Recommendation

| Surface | Recommendation |
|---------|----------------|
| **Public Top 3** | Keep current **End Result Candidates** (OWNER-PREDICTIONS-UI-2) — raw ECSE Top3 framing |
| **Owner/Pro Top 5** | Keep expandable Top 5 — no change |
| **Optimized Top 3 (S5)** | **Shadow / owner preview only** until 30–50 matches validate S5 |
| **Production ECSE ranking** | **DO NOT CHANGE** |
| **ECSE re-rank** | **DO NOT PROMOTE** (still NEED_MORE_DATA) |

Suggested owner preview label:
*"Optimized Top3 portfolio (shadow research) — not production prediction."*

---

## Validation (Part G)

```
TOP3-ENDRESULT-OPTIMIZER-1 validation: 32/32 passed
Recommendation: TOP3_OPTIMIZER_PROMISING_NEEDS_MORE_DATA
```

Confirmed: no DB writes, no provider calls, exactly 3 candidates, 90-minute evaluation, AET/PEN separated, WDE/ECSE production unchanged, timers disabled.

---

## Next Steps (shadow only)

1. Accumulate **30–50 finished WC matches** with ECSE snapshots
2. Re-run `scripts/run_top3_endresult_optimizer_1.py`
3. Compare S5 vs S0 on holdout segment before any owner preview
4. Do **not** promote until net gain holds out-of-sample with fresh odds

---
STOP — Shadow research complete. No production promotion. No timers.
