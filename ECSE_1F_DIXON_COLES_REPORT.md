# ECSE-1F — Dixon–Coles Low Score Correction Report

**Method:** `ECSE-1F-v1`  
**Table:** `ecse_score_distributions_dc`  
**ρ (rho):** `-0.13`  
**Corrected scorelines:** 0-0, 1-0, 0-1, 1-1 (renormalized)  
**Generated:** 2026-06-29 12:53:22 UTC  

## Build summary

- Fixtures built: **168,233**
- Distribution rows: **10,935,145** (expected 10,935,145)
- Avg low-score mass (0-0/1-0/0-1/1-1): **0.2940**
- Avg OTHER mass: **0.000000**
- Poisson table unchanged: **True** (10,935,145 rows)

## Side-by-side: ECSE-1E baseline vs Poisson vs Dixon–Coles

Poisson column = same ECSE-1E backtest engine on current `ecse_score_distributions` (ECSE-1D-B 8×8).

| Metric | ECSE-1E (frozen) | Poisson (current) | Dixon–Coles | DC − Poisson |
|--------|------------------|-------------------|-------------|--------------|
| Top-1 hit % | 11.0674 | 10.6335 | 10.4795 | -0.154 (↓ worse) |
| Top-3 hit % | 28.8665 | 28.4332 | 27.5398 | -0.8934 (↓ worse) |
| Top-5 hit % | 43.2394 | 42.7009 | 41.4092 | -1.2917 (↓ worse) |
| Log loss | 3.043873 | 3.122161 | 3.129174 | +0.007013 (↑ worse) |
| Brier score | 0.938625 | 0.94031 | 0.941235 | +0.000925 (↑ worse) |

*ECSE-1E frozen baseline: `ECSE-1D-v1` from 2026-06-29 12:37:45 UTC.*

## Backtest comparison (DC − Poisson, current grid)

| Metric | Poisson | Dixon–Coles | Δ |
|--------|---------|-------------|---|
| Top-1 hit % | 10.6335 | 10.4795 | -0.154 (↓ worse) |
| Top-3 hit % | 28.4332 | 27.5398 | -0.8934 (↓ worse) |
| Top-5 hit % | 42.7009 | 41.4092 | -1.2917 (↓ worse) |
| Avg prob on actual | 0.058996 | 0.059022 | +2.6e-05 (↑ better) |
| Log loss | 3.122161 | 3.129174 | +0.007013 (↑ worse) |
| Brier score | 0.94031 | 0.941235 | +0.000925 (↑ worse) |

## Low-score actuals (0-0, 1-0, 0-1, 1-1)

- Poisson avg prob on actual: **0.08622** (n=55,613)
- Dixon–Coles avg prob on actual: **0.086296** (n=55,613)
- Δ avg prob on actual: **+0.000076**
- Δ top-1 hit %: **+1.1760**

## Verdict

**DEGRADED** — 1/6 headline metrics favor Dixon–Coles vs current Poisson.

Dixon–Coles raises low-score Top-1 (+1.18 pp on 0-0/1-0/0-1/1-1 actuals) but degrades overall Top-3/Top-5 and calibration.

### Miss analysis (low-score underestimation)

- Poisson underestimate rate: 38.7468%
- Dixon–Coles underestimate rate: 51.4052%

---

*Research only. Original `ecse_score_distributions` table untouched. No deployment.*