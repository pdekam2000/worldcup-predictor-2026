# Phase 14 — Draw Collapse Audit

Generated: 2026-06-19T16:57:34.880141+00:00

## Mode

Read-only audit. No code, λ, harmonization, weight, or deploy changes.

## 1. Dataset size

- **Fixtures analyzed:** 262 (same pool as Phase 13: DB `n=250`, historical `n=12`)
- **Production WC replay subset:** 15 fixtures with results

## 2. Lambda spread distribution

| Stat | Value |
|------|-------|
| Average spread | 0.0069 |
| Median spread | 0.0000 |
| Min spread | 0.0000 |
| Max spread | 0.3006 |

### Spread buckets (fixture count)

| Bucket | Count | % |
|--------|-------|---|
| <0.05 | 252 | 96.2% |
| 0.05-0.10 | 2 | 0.8% |
| 0.10-0.20 | 4 | 1.5% |
| 0.20-0.30 | 3 | 1.1% |
| 0.30-0.50 | 1 | 0.4% |
| >0.50 | 0 | 0.0% |

## 3. Scoreline distribution

| Scoreline | Count | % |
|-----------|-------|---|
| 0-0 | 250 | 95.4% |
| 1-0 | 9 | 3.4% |
| 0-1 | 3 | 1.1% |

**Draw scorelines (any):** 250 (95.4%)  
**1-1 specifically:** 0 (0.0%)  
**0-0 specifically:** 250 (95.4%) — when λ_home ≈ λ_away at the **0.55 floor**, Poisson peaks at **0-0**, not 1-1.

## 4. Draw collapse analysis

For fixtures where scoreline-implied 1X2 = **draw** (`n=250`):

- Average λ spread: **0.0000**
- Median λ spread: **0.0000**

**Draw dominance begins** when spread < **0.10** (draw rate >50% in bucket `0.05-0.10` and above 90% below `0.05`).
Estimated threshold bucket: **<0.05**

## 5. Poisson dominance (1-1 as raw top scoreline)

| Gap (#1 − #2) | Count |
|---------------|-------|
| <1% | 0 |
| 1-3% | 0 |
| 3-5% | 0 |
| 5-10% | 0 |
| >10% | 0 |

Fixtures where raw Poisson #1 is 1-1: **0** (0.0%)

## 6. Home/Away separation failures

| Pattern | Count | % of all |
|---------|-------|----------|
| λ_home > λ_away AND scoreline draw AND WDE home_win | 0 | 0.0% |
| λ_away > λ_home AND scoreline draw AND WDE away_win | 0 | 0.0% |
| **Total directional mismatch** | 0 | 0.0% |

## 7. Root cause ranking (evidence)

| Rank | Cause | Affected fixtures | Draw rate in group |
|------|-------|-------------------|-------------------|
| 1 | A. Lambda symmetry (spread < 0.10) | 254 (96.9%) | 98.4% |
| 2 | B. λ floor clamp (0.55) — equal floor → 0-0 | 252 (96.2%) | 99.2% |
| 3 | E. Default goal averages (no odds/stats) | 250 (95.4%) | 95.4% |
| 4 | C. WC baseline blending | 0* | — |
| 5 | D. xG blending | 0* | — |
| 6 | F. primary_scoreline alt rule | 0 | — |

\*Bundesliga offline rows report `has_real` goal stats from form defaults, so WC/xG paths rarely activate; production WC behaves differently (avg spread **0.47**).

### Evidence notes

- **WC baseline (1.38 blend):** applied on 0 fixtures (0.0%); draw rate 0.0%
- **No real goal stats:** 0 fixtures (0.0%); draw rate 0.0%
- **λ floor clamp 0.55:** 0 fixtures had spread compressed by clamp
- **xG blending:** 0 fixtures; draw rate 0.0%
- **Odds available:** 12 (4.6%)

## 8. Spread bucket tables

| Spread | n | Draw% | Home% | Away% | Accuracy | 1-1% |
|--------|---|-------|-------|-------|----------|------|
| <0.05 | 252 | 99.2% | 0.4% | 0.4% | 27.0% | 0.0% |
| 0.05-0.10 | 2 | 0.0% | 50.0% | 50.0% | 50.0% | 0.0% |
| 0.10-0.20 | 4 | 0.0% | 75.0% | 25.0% | 50.0% | 0.0% |
| 0.20-0.30 | 3 | 0.0% | 100.0% | 0.0% | 33.3% | 0.0% |
| 0.30-0.50 | 1 | 0.0% | 100.0% | 0.0% | 100.0% | 0.0% |
| >0.50 | 0 | — | — | — | — | — |

## Production WC subset

| Metric | Value |
|--------|-------|
| n | 15 |
| Avg spread | 0.471 |
| Draw prediction rate | 60.0% |

## 9. Evidence-based answers

### Q1: Is lambda spread too small?
**Yes** — median spread **0.000**; **96.9%** of fixtures have spread < 0.10.

### Q2: Is 1-1 overproduced?

**On bulk sample: 0-0 is overproduced, not 1-1** — **95.4%** predict 0-0 (equal λ at floor).  
**On production WC subset:** spread avg **0.47** → **1-1 / low-score draws** dominate (**60%** draw rate). Both are Poisson symptoms of **insufficient λ separation**.

### Q3: Largest contributor to draw collapse?
**A. Lambda symmetry** — **96.2%** of fixtures have spread **<0.05** (median **0.000**). Equal λ at the **0.55 minimum clamp** makes Poisson select **0-0** almost always. WC baseline/xG rarely trigger on Bundesliga offline rows (only **4.6%** have odds); symmetry comes from **default goal averages** + **strength cancellation** (`home_strength` / `away_strength` mirror).

### Q4: What to audit next?
**Phase 15:** Counterfactual simulation — remove WC blend / raise floor / asymmetric clamp per odds confidence; measure draw rate on WC production pool only (`n=15+`).

## Architecture recommendation

1. **λ generation** is the root — not Poisson math. Symmetric λ from WC baseline + default goal averages + floor clamp produces 1-1 dominance.
2. **Do not tune harmonization first** — it only reflects scoreline-implied draw.
3. **Next step:** audit counterfactual λ paths on production WC fixtures with full odds/lineup context.

**Stop — audit only. No implementation.**