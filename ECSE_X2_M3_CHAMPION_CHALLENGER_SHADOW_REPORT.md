# ECSE-X2-M3 — Champion/Challenger Shadow Report

**Phase:** ECSE-X2-M3  
**Mode:** Shadow-only — no production prediction changes  
**Equation:** `log_home_prob_phi` — log(home_prob) / log(1.618)  
**Recommendation:** **KEEP_SHADOW_MORE_DATA**  

## X2-M2 Context

ECSE-X2-M2 identified `log_home_prob_phi` as best market algebra equation
(Top-1 +1.08pp, Top-3 +1.63pp on original 70/30 split).

## Sample

- Eligible fixtures (home odds): **55,005**
- Shadow rows written: **0**
- Shadow rows skipped (idempotent): **16,502**
- Baseline table rows unchanged: **10,935,145**

## Overall Champion vs Challenger (70/30 temporal test)

| Metric | Champion | Challenger | Δ |
|--------|----------|------------|---|
| Top-1 hit % | 9.4534 | 10.5381 | 1.0847 |
| Top-3 hit % | 26.7604 | 28.3905 | 1.6301 |
| Top-5 hit % | 39.268 | 42.5645 | 3.2965 |
| Top-10 hit % | 63.8832 | 67.2343 | 3.3511 |
| Log loss | 7.913794 | 7.737804 | -0.17599 |
| Brier | 0.742323 | 0.744699 | 0.002376 |

- Pick disagreement rate: **49.7212%**

## Fold-by-fold (temporal)

| Fold | n | Top-1 Δ | Top-3 Δ | Top-5 Δ | LogLoss Δ |
|------|---|---------|---------|---------|-----------|
| 1 | 11,001 | +1.3726 | +1.6271 | +3.2179 | -0.172858 |
| 2 | 11,001 | -0.0364 | +0.7635 | +1.9998 | -0.170857 |
| 3 | 11,001 | +1.0090 | +1.6544 | +3.0815 | -0.175443 |
| 4 | 11,001 | +1.0453 | +1.5544 | +3.5088 | -0.178656 |

## Breakdown highlights

### League
- **Championnat National U19** (n=116): top3 Δ=+0.0000, logloss Δ=-0.098177
- **Championship** (n=158): top3 Δ=-0.6329, logloss Δ=+0.145584
- **Club Friendlies 3** (n=162): top3 Δ=+5.5556, logloss Δ=-0.758668
- **Enterprise National League North** (n=100): top3 Δ=+5.0000, logloss Δ=-0.712399
- **Enterprise National League South** (n=103): top3 Δ=-6.7961, logloss Δ=-0.369521
- **League One** (n=120): top3 Δ=+2.5000, logloss Δ=+0.256086
- **Liga Nacional** (n=116): top3 Δ=-6.0345, logloss Δ=-0.983298
- **Ligue 1** (n=150): top3 Δ=+4.0000, logloss Δ=+0.030287

### Match state
- **away_favorite** (n=207): top3 Δ=+6.2801, logloss Δ=-1.025322
- **balanced** (n=955): top3 Δ=-1.5707, logloss Δ=+0.261706
- **home_favorite** (n=15,340): top3 Δ=+1.7666, logloss Δ=-1.061811

### Home prob bucket
- **home_40_55** (n=3,477): top3 Δ=-4.2278, logloss Δ=+1.033296
- **home_ge_55** (n=12,457): top3 Δ=+3.2271, logloss Δ=-1.567570
- **home_lt_40** (n=568): top3 Δ=+2.4648, logloss Δ=-0.556418

### Odds liquidity
- **low** (n=6,366): top3 Δ=+2.8904, logloss Δ=-1.461032
- **medium** (n=3,936): top3 Δ=+1.7022, logloss Δ=-1.125930
- **normal** (n=6,200): top3 Δ=+0.2903, logloss Δ=-0.406114

## Rank movement examples

- Lithuania U19 vs Latvia U19 — actual `1-2`: rank 2 → 1 (Δ1); top1 1-1 → 1-2
- Leiston vs Bishop's Stortford — actual `0-1`: rank 4 → 3 (Δ1); top1 1-1 → 1-2
- Austria vs Bosnia and Herzegovina — actual `1-1`: rank 2 → 3 (Δ-1); top1 2-1 → 2-1
- Haiti vs Nicaragua — actual `2-0`: rank 4 → 1 (Δ3); top1 1-1 → 2-0
- Panama vs El Salvador — actual `3-0`: rank 5 → 1 (Δ4); top1 2-1 → 3-0

## Overfit risk

- Folds with positive Top-3 Δ: **4**
- Risk flags: `partial_odds_coverage`

## Safety

- No public API / UI exposure
- No WDE / EGIE / baseline ECSE table changes
- Shadow artifact append-only

## Artifacts

- `artifacts/ecse_x2_m3_champion_challenger_shadow.jsonl`
- `C:/Users/kaman/Desktop/Footbal/artifacts/ecse_x2_m3_champion_challenger_summary.json`
