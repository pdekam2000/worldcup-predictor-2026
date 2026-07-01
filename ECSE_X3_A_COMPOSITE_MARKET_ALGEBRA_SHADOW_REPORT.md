# ECSE-X3-A — Composite Market Algebra Shadow Report

**Phase:** ECSE-X3-A  
**Mode:** Research/shadow only — no public prediction changes  
**Recommendation:** **USE_ONLY_HI_J2_G_SLOPE**  

## Accepted ECSE-X2 signals (used in X3)

- H = (ph + p_o25 + p_btts) / 3
- I = (pd + p_u25 + p_btts_no) / 3
- ZZ2 = p_btts > 0.56 AND p_u25 > 0.52
- J2 = p_o25 / p_btts
- G = abs(ph - pa) / p_o25
- OU_slope = p_o15 / p_o25

## Rejected ECSE-X2 signals (excluded)

- Equation A raw odds
- Fibonacci / phi / 1.618
- Equation D redundant with p_ht_o15
- Mystical / non-probabilistic patterns

## Coverage

| Metric | Value |
|--------|-------|
| Eligible fixtures | 55,005 |
| Test holdout (30%) | 16,502 |
| ft_home coverage | 100.0% |
| Missing odds rate | 0.0% |
| ZZ2 flag rate | 0.0509% |
| ≥4 signal families | 0.0073% |
| Baseline table rows (unchanged) | 10,935,145 |

## Challenger comparison (overall test)

| Method | Top-1 Δ | Top-3 Δ | Top-5 Δ | Top-10 Δ | LogLoss Δ | MRR Δ | Accepted |
|--------|---------|---------|---------|----------|-----------|-------|----------|
| hi_only | -0.0606 | -0.0121 | +0.2545 | +0.0000 | -0.252902 | +0.000171 | False |
| zz2_only | +0.0000 | +0.0000 | +0.0000 | +0.0000 | -0.000168 | +0.000000 | False |
| j2_g_slope | +0.3515 | -0.0970 | +1.4483 | +0.0000 | -0.252689 | +0.013439 | True |
| composite_full | +0.3030 | -0.0788 | +1.6664 | +0.0000 | -0.253810 | +0.013362 | True |
| conservative_composite | +0.0000 | +0.0000 | +0.0000 | +0.0000 | +0.000000 | +0.000000 | False |
| segment_aware | +0.3515 | -0.1091 | +1.8967 | +0.0000 | -0.254248 | +0.013789 | True |

## Fold stability (j2_g_slope)

| Fold | n | Top-1 Δ | Top-3 Δ | Top-5 Δ |
|------|---|---------|---------|---------|
| 1 | 11,001 | +0.1818 | +0.1454 | +1.7544 |
| 2 | 11,001 | +0.1818 | +0.0818 | +1.4271 |
| 3 | 11,001 | +0.1546 | +0.0818 | +1.3180 |
| 4 | 11,001 | +0.3817 | -0.1636 | +1.4999 |

## Segment analysis (Top-5 Δ vs champion)

### all_eligible (n=16,502)
- **hi_only**: top1 Δ=-0.0606, top5 Δ=+0.2545
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.3515, top5 Δ=+1.4483
- **composite_full**: top1 Δ=+0.3030, top5 Δ=+1.6664
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.3515, top5 Δ=+1.8967

### home_favorite (n=15,340)
- **hi_only**: top1 Δ=-0.0847, top5 Δ=+0.2673
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.3521, top5 Δ=+1.6558
- **composite_full**: top1 Δ=+0.2804, top5 Δ=+1.9361
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.3325, top5 Δ=+2.1839

### away_favorite (n=207)
- **hi_only**: top1 Δ=+0.0000, top5 Δ=-0.4831
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.4831, top5 Δ=-2.4154
- **composite_full**: top1 Δ=+0.4831, top5 Δ=-2.8985
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.4831, top5 Δ=-2.8985

### balanced_match (n=955)
- **hi_only**: top1 Δ=+0.3141, top5 Δ=+0.2095
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.3141, top5 Δ=-1.0471
- **composite_full**: top1 Δ=+0.6282, top5 Δ=-1.6754
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.6282, top5 Δ=-1.6754

### home_ge_55 (n=12,457)
- **hi_only**: top1 Δ=+0.0321, top5 Δ=+0.3452
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.4254, top5 Δ=+1.9186
- **composite_full**: top1 Δ=+0.4014, top5 Δ=+2.2879
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.4014, top5 Δ=+2.4886

### home_ge_60 (n=10,569)
- **hi_only**: top1 Δ=+0.1040, top5 Δ=+0.3217
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.4541, top5 Δ=+2.1194
- **composite_full**: top1 Δ=+0.4730, top5 Δ=+2.4790
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.4920, top5 Δ=+2.8007

### btts_high (n=2,080)
- **hi_only**: top1 Δ=-0.8173, top5 Δ=+1.1539
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=-0.1923, top5 Δ=-0.1442
- **composite_full**: top1 Δ=-0.8173, top5 Δ=+0.9615
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=-0.6250, top5 Δ=+1.6346

### under_25_high (n=2,594)
- **hi_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.2698, top5 Δ=+1.0023
- **composite_full**: top1 Δ=+0.2698, top5 Δ=+1.0023
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.2698, top5 Δ=+1.0023

### over_25_high (n=11,190)
- **hi_only**: top1 Δ=-0.0626, top5 Δ=+0.3217
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.3217, top5 Δ=+1.6979
- **composite_full**: top1 Δ=+0.2770, top5 Δ=+1.9660
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.3217, top5 Δ=+2.2699

### world_cup_group (n=43)
- **hi_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+2.3255, top5 Δ=+2.3256
- **composite_full**: top1 Δ=+2.3255, top5 Δ=+2.3256
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+2.3255, top5 Δ=+2.3256

### odds_liquidity_high (n=6,200)
- **hi_only**: top1 Δ=-0.1129, top5 Δ=+0.6774
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.3064, top5 Δ=+0.3548
- **composite_full**: top1 Δ=+0.1935, top5 Δ=+0.9516
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.3064, top5 Δ=+1.4516

### odds_liquidity_low (n=9,535)
- **hi_only**: top1 Δ=+0.0000, top5 Δ=-0.0105
- **zz2_only**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **j2_g_slope**: top1 Δ=+0.4090, top5 Δ=+2.1185
- **composite_full**: top1 Δ=+0.4195, top5 Δ=+2.1080
- **conservative_composite**: top1 Δ=+0.0000, top5 Δ=+0.0000
- **segment_aware**: top1 Δ=+0.4300, top5 Δ=+2.1290


## Missing odds analysis

- `pd`: 55,005
- `pa`: 55,005
- `p_btts_no`: 47,208
- `p_u25`: 44,404
- `p_btts`: 43,070
- `p_o15`: 24,356
- `p_o25`: 11,806

## Examples — composite improved rank

- Fixture 155773: actual 2-1, baseline rank 3 → 2
- Fixture 155781: actual 2-1, baseline rank 5 → 4
- Fixture 155878: actual 2-0, baseline rank 4 → 3
- Fixture 155844: actual 2-0, baseline rank 8 → 6
- Fixture 155860: actual 2-1, baseline rank 6 → 5

## Examples — composite worsened rank

- Fixture 155816: actual 1-2, baseline rank 2 → 3
- Fixture 155765: actual 0-1, baseline rank 4 → 5
- Fixture 155777: actual 0-0, baseline rank 8 → 10
- Fixture 155782: actual 0-2, baseline rank 7 → 8
- Fixture 155881: actual 2-2, baseline rank 5 → 6

## Safety

- No public prediction output changes
- No ECSE baseline table changes
- Phi/Fibonacci logic not used (archived X2 research only)
- Shadow artifact only

## Artifacts

- `artifacts/ecse_x3_a_composite_shadow.jsonl`
- `artifacts/ecse_x3_a_composite_shadow_summary.json`
