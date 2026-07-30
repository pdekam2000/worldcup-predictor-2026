# FINAL LAMBDA TEAM STRENGTH FORENSIC REPORT

Status: **LAMBDA_RESEARCH_COMPLETE_SHADOW_PARTIAL**

## 1. Exact lambda generation path

Odds lines → `build_odds_feature_row` / training closing odds → `extract_lambdas` (`ECSE-1C-v1`) → BTTS rescale → clip `[0.15, 6.0]` → `generate_score_distribution` (`ECSE-1D-B`, 7×7 + OTHER) → freeze columns `lambda_home` / `lambda_away`.

Runtime paths: `live_odds`, `registry_precomputed`, prematch bundle — all use the same extractor. **No football attack/defense/form/Elo enters canonical λ.**

## 2. Confirmed upstream causes of lambda underestimation

1. **Odds-only λ** — team attacking/defensive strength never wired into production ECSE.
2. **High-total market under-signal** — O/U 4.5 loaded in SQL but unused; 3.5 only weight 0.15; missing high lines weaken totals.
3. **No surge/collapse/volatility features** in canonical inference (`team_form_snapshots` n=0).
4. **Conditional underestimation** — global mean λ err only +0.27, but **5+ fixtures: +3.11**; history n≈40 on those misses → not primarily identity absence.
5. **Clipping is not the bottleneck** — ceil 6.0 rarely binds.
6. **Shrinkage toward low-scoring football priors** is absent in extractor; research shrink to league averages alone does not recover high-score Top5.
7. **Freeze lacks O/U odds persistence** — market-total forensics limited post-hoc.
8. **WDE does not feed λ** — 66.7% direction agree; disagreement is mostly share allocation, not the +3 goal miss.

## 3. Feature missingness impact

Canonical inference: football λ-relevant features are **100% absent by design**. Research history matching after fix: identity gap **5/168 (3.0%)**. Severe underestimation cohort still has ~40 matches/team → missingness is not the main driver of the tail miss.

## 4. Fallback impact

Production fallback: OU-only / team-only / draw prior 0.26 / registry precomputed. Research league/global fallback rate ~3%. Severe misses are mostly **team-matched**, not fallback-driven.

## 5. Stale-feature impact

Canonical λ uses odds at freeze time (freshness on CSV). Football history in research is kickoff-strict. No evidence stale football ratings caused canonical misses (they were never used).

## 6. Team identity issues

Initial research gap 148/168 due to suffix/normalization mismatch (`Hammarby FF` vs `hammarby`). Fixed via accent-fold + suffix drop + staging history. Residual gap 5/168. Reserve/youth flags rare in this eval set.

## 7. League-prior issues

Extractor has **no league goal-environment prior**. Research league-average baseline does not beat B0 on high-score Top5.

## 8. Shrinkage issues

Extractor blends OU↔team and share↔team; no Bayesian football pooling in production. Research partial pooling helps stability but **overshoots low-score** when aggressive (T7 mean err −0.25).

## 9. Clipping / cap issues

Floor 0.15 / ceil 6.0 — not the high-score failure mode.

## 10. Market-total usage issues

Market **is** the λ source. Residual +3.11 on 5+ means markets+blend still low vs realized extremes, with no football correction layer.

## 11–15. Best models (full n=168)

| Role | Model | Top5 | High Top5 | Total MAE | High MAE | Mean λ err |
|------|-------|------|-----------|-----------|----------|------------|
| Canonical | B0 | 45.2% | 3.2% | 1.429 | 3.106 | +0.273 |
| Best gated | T7_defensive_collapse | 42.9% | 3.2% | 1.542 | 2.727 | −0.254 |
| Team strength | T7_defensive_collapse | 42.9% | 3.2% | 1.542 | 2.727 | −0.254 |
| Market-informed | B7_market_resplit | 45.2% | 3.2% | 1.429 | 3.106 | +0.273 |
| Uncertainty | B0_canonical (gated) | 45.2% | 3.2% | 1.429 | 3.106 | +0.273 |
| Joint | B0_canonical (gated) | 45.2% | 3.2% | 1.429 | 3.106 | +0.273 |

Gate: val Top5 within 5pp of B0 **and** full high-score Top5 ≥ B0. Dixon–Coles joints improve global Top5 but **zero** high-score Top5 → excluded.

## 16–22. Metrics summary

- Canonical Exact Top1 / Top5 / Top10: **14.9% / 45.2% / 75.6%**
- Best gated Exact: Top5 **42.9%**, high Top5 **3.2%** (tie, not lift)
- High-score MAE improved under T7 (**3.11 → 2.73**) without Top5 lift
- WDE↔λ agree rate: **66.7%**
- Low-score remains strong under B0 (Top5 75%); football challengers must stay shadow-only

## 23. Regressions

T7: slight global Top5 drop (~2.4pp) and low-score overshoot. T11 regime boost improved mean calibration but **regressed high Top5 to 0%**.

## 24. Forward-shadow status

Table `lambda_team_strength_shadow_outputs`: **1344** rows (8 families × 168). Canonical freezes untouched. Never exposed as canonical.

## 25. Production eligibility

**NOT eligible.** No high-score Top5 lift; sample below promotion gates.

## 26. Minimum remaining sample

Need: global 250 (have 168), high-score-risk 100, actual 5+ 40 (have 31), low-score 150.

## 27. Remaining blockers

- No challenger materially lifts high-score Exact Top5
- Need production-safe team-strength feature service + O/U line persistence on freezes
- Need larger forward shadow sample
- Tail redistribution previously failed; λ mean correction alone also insufficient so far — need better conditional high-total regime modeling under leakage constraints

Branch: `research/lambda-team-strength-shadow-20260730T134952Z`  
Artifact: `artifacts/lambda_team_strength_research/20260730T134952Z`
