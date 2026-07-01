# ECSE-X2-M4 — Internal Weight Test Report

**Phase:** ECSE-X2-M4  
**Mode:** Shadow/internal weight test — no public exposure  
**Equation:** `log_home_prob_phi` — log(home_prob) / log(1.618)  
**Recommendation:** **KEEP_RESEARCH_ONLY**  

## M3 context

M3 full reorder on eligible cohort: Top-3 +1.63pp, log loss −0.176.
M4 applies the same lift signal as a small blend (max weight 0.10) only in the
home-favorite / home_prob≥0.55 segment where M3 was strongest.

## Target segment

Apply adjustment only when:
- `ft_home` / home_prob exists
- home_prob >= 0.55
- classified as home favorite
- valid odds snapshot
- not balanced

## Sample

- Eligible fixtures (any home odds): **55,005**
- Target segment fixtures: **41,455**
- Segment coverage: **75.4%**
- Shadow rows written: **66,330**
- Shadow rows skipped: **0**
- Baseline table unchanged: **10,935,145**

## Best weight: **0.05**

## Per-weight comparison (70/30 test)

| Weight | Top-1 Δ | Top-3 Δ | Top-5 Δ | LogLoss Δ | Volatility | Accepted |
|--------|---------|---------|---------|-----------|------------|----------|
| 0.01 | +0.0364 | +0.0061 | +1.0847 | -0.241740 | 0.1672 | yes |
| 0.03 | +0.0909 | -0.0182 | +1.0362 | -0.303354 | 0.1872 | no |
| 0.05 | +0.1030 | +0.0182 | +1.0604 | -0.348636 | 0.213 | yes |
| 0.07 | +0.1576 | -0.0182 | +1.0786 | -0.386394 | 0.2331 | no |
| 0.1 | +0.2303 | -0.0545 | +1.0301 | -0.422920 | 0.2648 | no |

## Rejection summary

- weight **0.01**: accepted=True — gain_only_some_folds
- weight **0.03**: accepted=False — gain_only_some_folds, top1_only_gain
- weight **0.05**: accepted=True — none
- weight **0.07**: accepted=False — gain_only_some_folds, top1_only_gain
- weight **0.1**: accepted=False — top1_only_gain

## Fold results (best weight)

| Fold | n | Top-3 Δ | LogLoss Δ |
|------|---|---------|-----------|
| 1 | 11,001 | +0.1182 | -0.265844 |
| 2 | 11,001 | +0.0818 | -0.255964 |
| 3 | 11,001 | +0.0272 | -0.332958 |
| 4 | 11,001 | -0.0636 | -0.360958 |

## Segment breakdown (best weight)

- **home_ge_55** (n=12,457): top3 Δ=+0.0241, logloss Δ=-0.461843
- **home_ge_60** (n=10,569): top3 Δ=+0.0568, logloss Δ=-0.530795
- **home_favorite** (n=15,340): top3 Δ=+0.0196, logloss Δ=-0.375044
- **strong_home_favorite** (n=10,569): top3 Δ=+0.0568, logloss Δ=-0.530795
- **balanced_only** (n=955): top3 Δ=+0.0000, logloss Δ=+0.000000
- **non_balanced** (n=15,547): top3 Δ=+0.0193, logloss Δ=-0.370050

## Safety

- No public API / UI exposure
- No WDE / EGIE / baseline ECSE table changes
- Balanced matches excluded from adjustment
- Shadow artifact append-only

## Artifacts

- `artifacts/ecse_x2_m4_internal_weight_test.jsonl`
- `artifacts/ecse_x2_m4_internal_weight_summary.json`
