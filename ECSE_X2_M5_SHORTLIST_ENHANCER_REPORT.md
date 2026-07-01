# ECSE-X2-M5 — Shortlist Enhancer Report

**Phase:** ECSE-X2-M5  
**Mode:** Research/shadow only — no production changes  
**Recommendation:** **PROMOTE_SHORTLIST_SHADOW_LIVE**  

## Hypothesis

Market algebra may improve exact-score shortlist quality (Top-5/Top-10)
even when too weak for full ranking promotion (M4 Top-3 +0.02pp).

## Sample

- Eligible fixtures (ft_home odds): **55,005**
- Test fixtures (30% holdout): **16,502**
- Shadow rows written: **16,502**
- Baseline table unchanged: **10,935,145**

## Best method: **shortlist_enhancer**

## Method comparison (overall test)

| Method | Top-1 Δ | Top-3 Δ | Top-5 Δ | Top-10 Δ | LogLoss Δ | MRR Δ | Volatility |
|--------|---------|---------|---------|----------|-----------|-------|------------|
| m3_full_reorder | +1.0847 | +1.6301 | +3.2965 | +3.3511 | -0.984760 | +0.012173 | 1.5423 (rej) |
| m4_weight_005 | +0.2121 | +0.0121 | +1.3998 | +1.4240 | -0.472906 | +0.004995 | 0.3151 (ok) |
| shortlist_enhancer | +0.9938 | +1.3574 | +2.3876 | +0.0000 | -0.247775 | +0.022036 | 1.281 (ok) |
| tie_breaker | +0.5151 | +0.7757 | +2.1270 | +0.0000 | +0.000000 | +0.016129 | 0.571 (ok) |

## Rejection summary

- **m3_full_reorder**: accepted=False — balanced_degrades
- **m4_weight_005**: accepted=True — none
- **shortlist_enhancer**: accepted=True — none
- **tie_breaker**: accepted=True — none

## Segment breakdown (Top-5 Δ vs champion)

### all_eligible (n=16,502)
- m3_full_reorder: top5 Δ=+3.2965, top3 Δ=+1.6301
- m4_weight_005: top5 Δ=+1.3998, top3 Δ=+0.0121
- shortlist_enhancer: top5 Δ=+2.3876, top3 Δ=+1.3574
- tie_breaker: top5 Δ=+2.1270, top3 Δ=+0.7757

### home_ge_55 (n=12,457)
- m3_full_reorder: top5 Δ=+6.5827, top3 Δ=+3.2271
- m4_weight_005: top5 Δ=+1.8865, top3 Δ=+0.1365
- shortlist_enhancer: top5 Δ=+4.6560, top3 Δ=+2.7695
- tie_breaker: top5 Δ=+2.8177, top3 Δ=+1.0275

### home_ge_60 (n=10,569)
- m3_full_reorder: top5 Δ=+7.8153, top3 Δ=+4.1347
- m4_weight_005: top5 Δ=+2.2330, top3 Δ=+0.1609
- shortlist_enhancer: top5 Δ=+5.5634, top3 Δ=+3.5481
- tie_breaker: top5 Δ=+3.3210, top3 Δ=+1.2111

### home_favorite (n=15,340)
- m3_full_reorder: top5 Δ=+3.7484, top3 Δ=+1.7666
- m4_weight_005: top5 Δ=+1.5124, top3 Δ=+0.0456
- shortlist_enhancer: top5 Δ=+2.5098, top3 Δ=+1.3820
- tie_breaker: top5 Δ=+2.2882, top3 Δ=+0.8344

### strong_home_favorite (n=10,569)
- m3_full_reorder: top5 Δ=+7.8153, top3 Δ=+4.1347
- m4_weight_005: top5 Δ=+2.2330, top3 Δ=+0.1609
- shortlist_enhancer: top5 Δ=+5.5634, top3 Δ=+3.5481
- tie_breaker: top5 Δ=+3.3210, top3 Δ=+1.2111

### balanced_control (n=955)
- m3_full_reorder: top5 Δ=-4.5026, top3 Δ=-1.5707
- m4_weight_005: top5 Δ=-0.1047, top3 Δ=-0.7330
- shortlist_enhancer: top5 Δ=+0.0000, top3 Δ=+0.0000
- tie_breaker: top5 Δ=+0.0000, top3 Δ=+0.0000


## Fold results (shortlist_enhancer)

| Fold | n | Top-5 Δ | Top-3 Δ | LogLoss Δ |
|------|---|---------|---------|-----------|
| 1 | 11,001 | +2.7907 | +1.3908 | -0.246932 |
| 2 | 11,001 | +1.5362 | +0.4545 | -0.240432 |
| 3 | 11,001 | +2.4907 | +1.6726 | -0.252583 |
| 4 | 11,001 | +2.2816 | +1.0454 | -0.246235 |

## Safety

- No public API / UI exposure
- No WDE / EGIE / baseline ECSE table changes
- Balanced control reported separately

## Artifacts

- `artifacts/ecse_x2_m5_shortlist_enhancer.jsonl`
- `artifacts/ecse_x2_m5_shortlist_enhancer_summary.json`
