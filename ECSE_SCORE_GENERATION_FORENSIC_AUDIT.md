# ECSE Score Generation Forensic Audit

**SHA:** b621195fa7b711a4c1d07803d418eda8b731d2e8 | **Vienna:** 2026-07-13 19:27 CEST

## Answers

1. **Lambdas derived:** O/U 2.5 (40%), O/U 1.5 (20%), O/U 3.5 (15%), team totals (25%); split by 1X2 share; blended with team O/U.
2. **lambda_home markets:** O/U totals, team home O/U 0.5/1.5, 1X2 home share, BTTS gentle scale.
3. **lambda_away markets:** Same for away side.
4. **Covariance:** Not in canonical Poisson; Dixon–Coles τ only on 0-0/1-0/0-1/1-1.
5. **Overdispersion:** Not modeled in canonical path.
6. **Score dependence:** Independent Poisson margins; optional DC low-score correction.
7. **Grid truncated:** 0–7 per team (8×8) + OTHER bucket.
8. **OTHER mass:** Remainder above grid, renormalized.
9. **High-score tails compressed:** high_score_tail calibration gap n/a
10. **Weak-team goals underestimated:** underdog suppression mean -0.1113
11. **Clean sheets overproduced:** clean_sheet calibration n/a
12. **BTTS Yes underrepresented in Top5:** confirmed when canonical Top5 clusters clean sheets.
13. **League-specific variance:** Not in canonical; research league_variance method only.
14. **Same distribution family:** Yes — Poisson for all leagues.
15. **Extreme odds asymmetry:** underdog_floor research addresses λ_away suppression when home fav <1.55.

## Canonical path
`odds → extract_lambdas → generate_score_distribution → sort by probability → Top1/3/5/10`

**Confirmed:** Canonical Top5 is pure probability ranking. WDE/Last8/xG do not rerank.
