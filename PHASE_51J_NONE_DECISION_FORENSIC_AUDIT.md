# PHASE 51J — NONE Decision Forensic Audit

**Status:** completed  
**Mode:** READ ONLY — no code changes, no deploy, no database writes  
**Source:** `artifacts/phase51h_egie_backtest.jsonl` + leakage-safe feature replay (349/349 engine alignment)  
**Machine-readable output:** `artifacts/phase51j_none_decision_audit.json`

---

## Executive Summary

The `|home_rate − away_rate| < 0.04` abstention rule is **not hiding high-quality predictions**. It is **correctly filtering coin-flip matches**.

| Finding | Evidence |
|---------|----------|
| Forced picks on 152 abstains | **49.3%** win rate (below current 50.8% picked pool) |
| Removing abstention entirely (threshold 0.00) | **49.6%** on all 349 fixtures — **worse** than current 50.8% on 197 picks |
| Abstention is working as designed | Mean home/away rates in abstain pool: **0.371 vs 0.369** (near-identical) |
| Optimal threshold for pick accuracy | **0.04** (current) — highest picked-only win rate |
| Odds / xG counterfactuals | **Not evaluable** — no per-fixture odds or xG in current pipeline |

**Verdict:** The 0.04 threshold is **conservative for coverage** but **appropriate for accuracy**. Replacing `none` with forced directional picks would increase volume but **reduce** trust and headline accuracy. The highest-ROI path is **Survival Analysis** to output team probabilities instead of a binary abstain — not lowering the threshold.

---

## Part A — Counterfactual Analysis (152 NONE Cases)

All 152 cases had a goal; all are `first_goal_team = none` under current engine.

| Scenario | Correct | Wrong | Win Rate |
|----------|---------|-------|----------|
| **A — Always HOME** | 81 | 71 | **53.3%** |
| **B — Always AWAY** | 71 | 81 | 46.7% |
| **C — Highest rate side** | 75 | 77 | **49.3%** |
| **D — Bookmaker favorite** | — | — | **N/A** |
| **E — xG favorite** | — | — | **N/A** |
| **Current abstain (Policy A)** | 0 scored | 152 pending | 0% scored |

### Interpretation

- **Scenario C** (what the engine would pick if forced) achieves **49.3%** — below coin-flip on this pool and **below the 50.8%** win rate on the 197 fixtures where the engine did commit.
- **Scenario A** (always home) at 53.3% exploits the **home first-goal base rate** (53% of abstain outcomes were home), not model skill. This is not a viable replacement for `none`.
- **Scenarios D & E** cannot be evaluated: `has_reliable_goal_odds = False` for all 349 fixtures; per-fixture xG is not in the feature vector.

### What would have happened without abstention?

If the engine had published Scenario C picks on all 152 abstains:

- Combined pool: **175/349 = 50.1%** (vs **50.8%** on current 197 picks only)
- Net effect: **+152 picks, −0.7pp accuracy** on the full published set

**Abstention is helping, not hurting**, by withholding ~49% accuracy picks from the directional product.

---

## Part B — Threshold Sweep

Replayed using exact baseline rate logic (`gap < threshold → none`) on all 349 published fixtures.

| Threshold | Picks | Abstains | Coverage | Picked-Only WR | All-Fixture WR† | Commercial Score‡ |
|-----------|-------|----------|----------|----------------|-----------------|-------------------|
| **0.00** | 349 | 0 | 100.0% | 49.6% | 49.6% | **0.496** |
| 0.01 | 337 | 12 | 96.6% | 49.6% | 47.9% | 0.479 |
| 0.02 | 213 | 136 | 61.0% | 49.3% | 30.1% | 0.301 |
| 0.03 | 213 | 136 | 61.0% | 49.3% | 30.1% | 0.301 |
| **0.04** | **197** | **152** | **56.5%** | **50.8%** | 28.7% | 0.287 |
| 0.05 | 99 | 250 | 28.4% | 49.5% | 14.0% | 0.140 |
| 0.06 | 98 | 251 | 28.1% | 49.0% | 13.8% | 0.138 |
| 0.07 | 98 | 251 | 28.1% | 49.0% | 13.8% | 0.138 |
| 0.08 | 98 | 251 | 28.1% | 49.0% | 13.8% | 0.138 |
| 0.10 | 0 | 349 | 0.0% | — | 0.0% | 0.000 |

† All-fixture WR = correct / 349 (abstains count as non-correct)  
‡ Commercial score = picked-only WR × coverage (proxy for volume × quality)

### Optimal threshold

| Objective | Optimal | Value |
|-----------|---------|-------|
| **Picked-only accuracy** | **0.04 (current)** | **50.8%** |
| **Maximum coverage** | 0.00 | 100% at 49.6% |
| **Commercial score (volume × accuracy)** | 0.00 | 0.496 |

**Recommendation:** Keep **0.04** for directional pick quality. Lowering the threshold trades accuracy for coverage without reaching commercially viable hit rates (>52%).

> Note: No fixtures fall in the 0.02–0.03 gap bucket — abstain gaps are bimodal at ~0.01 and ~0.04, so thresholds 0.02 and 0.03 produce identical results to each other.

---

## Part C — Gap Distribution Analysis (152 Abstains)

| Gap Bucket | Count | % of Abstains | Actual Home FG% | Actual Away FG% | Forced-Pick WR |
|------------|-------|---------------|-----------------|-----------------|----------------|
| 0.00–0.01 | 12 | 7.9% | 33.3% | 66.7% | 66.7% |
| **0.01–0.02** | **124** | **81.6%** | 56.5% | 43.5% | **50.0%** |
| 0.02–0.03 | 0 | 0.0% | — | — | — |
| 0.03–0.04 | 16 | 10.5% | 43.8% | 56.3% | 31.3% |

**Gap range:** 0.000 – 0.040 (strictly less than 0.04)

### Are abstained fixtures predictable?

**Mostly no.**

- **81.6%** of abstains sit in the 0.01–0.02 gap band with **exactly 50.0%** forced-pick accuracy — pure coin-flip.
- The 0.03–0.04 band (10.5%) performs worst at **31.3%** when forced — actively harmful to publish.
- The small 0.00–0.01 band (n=12) shows 66.7% but is **not statistically reliable** at this sample size.

Abstained fixtures are **not** a hidden high-edge pool waiting to be unlocked by removing the threshold.

---

## Part D — Feature Analysis

### Rate features (abstain pool)

| Variable | Mean (abstains) | Mean (picked) | Signal |
|----------|-----------------|---------------|--------|
| home_rate | 0.371 | — | Near-zero separation |
| away_rate | 0.369 | — | Near-zero separation |
| rate_gap | 0.000–0.040 | ≥0.040 | By construction |
| DQ | 0.5714 | 0.5714 | No difference |
| confidence | 0.645 | 0.646 | No difference |

### Signed lean (when forced to pick)

| Lean | Count | Forced-Pick WR | Actual Home FG% |
|------|-------|----------------|-----------------|
| home_lean | 76 | 51.3% | 51.3% |
| away_lean | 70 | 45.7% | 54.3% |
| exact_tie | 6 | 66.7% | 66.7% |

Home lean slightly outperforms away lean when forced (51.3% vs 45.7%), but both are near coin-flip. **Away lean actually predicts the wrong direction more often than home** (actual home FG 54.3% when model leans away).

### History depth

| Metric | Abstains (avg) | Picked (avg) |
|--------|----------------|--------------|
| Home match samples | 17.6 | 19.2 |
| Away match samples | 17.6 | 19.2 |
| Home goal-event samples | 17.1 | — |
| Away goal-event samples | 17.1 | — |

Abstain fixtures have **slightly thinner history** (~1.6 fewer matches per team) but the difference is small — not the primary driver.

### Odds & xG

| Source | Available |
|--------|-----------|
| Bookmaker odds | **0 / 349** |
| Per-fixture xG | **0 / 349** |

No external signal can currently rescue abstain decisions.

### Teams most involved in abstentions

Sheffield Utd (24), Fulham (18), West Ham (17) — overlaps with Phase 51I thin-history / promoted-team findings.

---

## Part E — Survival Analysis Readiness

| Market | Impact | Evidence |
|--------|--------|----------|
| **First Goal Team** | **Medium** | Forced abstain picks = 49.3%; survival can output P(home first) / P(away first) instead of binary `none` |
| **Goal Range** | **High** | 72.4% range wrong even on abstain fixtures where range is still published |
| **Goal Minute** | **High** | Minute is bucket midpoint; survival gives full time-to-goal distribution |

### Convertible abstain cases (estimate)

| Tier | % of 152 abstains | Basis |
|------|-------------------|-------|
| Low | 5% | ~8 fixtures potentially above 52% with better model |
| Medium | 15% | ~23 fixtures |
| High | 25% | ~38 fixtures |

Commercial value requires **>52%** hit rate; current forced pool is **49.3%**.

---

## Part F — Commercial Impact

### Current system (threshold 0.04)

| Metric | Value |
|--------|-------|
| Abstain rate | 43.6% (152/349) |
| Directional picks | 197 |
| Directional win rate | **50.8%** |
| Policy A headline | 50.8% |
| Policy B headline | 28.7% |

### Zero-threshold (no abstention)

| Metric | Value | Delta |
|--------|-------|-------|
| Additional picks | +152 | — |
| Picked-only win rate | 49.6% | **−1.2pp** |
| Combined win rate | 50.1% | +0.3pp vs Policy B, −0.7pp vs current picks |

### Dashboard impact if abstention removed

- Published picks: 197 → **349** (+77%)
- Evaluated team picks: +152
- Expected accuracy on former abstains: **49.3%**
- User trust: **negative** — more picks at lower quality dilutes the 50.8% directional product

---

## Part G — Final Recommendations

### 1. Is the 0.04 threshold too conservative?

**For coverage: yes** (43.6% abstain).  
**For accuracy: no** — it produces the highest picked-only win rate (50.8%) in the sweep.

### 2. Should hard NONE remain?

**Not as a published binary field.** Abstention logic is sound, but the product should expose it as **"no directional edge"** (Policy C from Phase 51I), not a silent `none` with range/minute still published.

### 3. Should NONE become Home Lean / Away Lean / Probability Split / Confidence Reduction?

| Option | Verdict |
|--------|---------|
| Home Lean | **Reject** — exploits base rate, not model (53.3% on abstains) |
| Away Lean | **Reject** — 46.7%, worse than home |
| **Probability Split** | **Recommend** — show P(home first) / P(away first) |
| **Confidence Reduction** | **Recommend** — lower display confidence when gap < threshold |

### 4. Would replacing NONE likely increase coverage / accuracy / business value?

| Dimension | Effect |
|-----------|--------|
| Coverage | **Yes** (+43.6%) |
| Accuracy | **No** (49.3% forced vs 50.8% current picks) |
| Business value | **No** — unless reframed as separate abstain product |

### 5. Should Survival Analysis happen before or after NONE redesign?

**Before NONE redesign.** Survival provides the probabilistic output needed to replace the binary cut. Redesigning `none` without survival risks publishing more 49% picks.

### 6. Highest ROI next step?

**Survival Analysis** for goal range + minute (High impact) and probabilistic team output (Medium impact) — **before** lowering abstention threshold, adding leagues, or Multi-LLM layer.

---

## Artifacts

| File | Description |
|------|-------------|
| `artifacts/phase51j_none_decision_audit.json` | Full structured audit with 152 fixture IDs |
| `artifacts/phase51h_egie_backtest.jsonl` | Source backtest per-fixture records |
| `PHASE_51I_EGIE_BACKTEST_CALIBRATION_AUDIT.md` | Prior evaluation policy audit |

---

**Phase 51J complete. No implementation. No deploy. No code changes.**
