# PHASE 56A — Market Behavior Intelligence (MBI)

**Date:** 2026-06-24
**Mode:** Research → Historical Odds Intelligence
**Status:** Complete — research only
**API calls:** 0

### Final recommendation: **`MBI_MEDIUM_VALUE`**

---

## Part A — Odds Inventory

| Metric | Value |
|--------|-------|
| Total snapshot rows | 274074 |
| Normalized market lines | 485949 |
| MBI selections collected | 52842 |
| Selections with outcomes | 14974 |

### Sources

- **sportmonks_cache**: 1689 fixtures, 272117 odds rows
- **odds_snapshots**: 85 fixtures, 1055 odds rows
- **oddalerts_odds_history**: 3 fixtures, 902 odds rows

Artifact: `artifacts/phase56a_market_behavior_intelligence/odds_inventory.json`

## Part B — Odds Buckets

Buckets: 1.10–1.20, 1.20–1.30, … 10.90–11.00, 11.00+

Bucket cells with outcomes: **519**

## Part C — Real Outcomes vs Implied

| Metric | Value |
|--------|-------|
| Global Brier | 0.2077 |
| Global ECE | 0.0433 |
| Scored selections | 14974 |

### Top calibration gaps (n≥30)

| Market | Bucket | Selection | N | Hit% | Implied | Gap |
|--------|--------|-----------|---|------|---------|-----|
| match_winner | 2.40-2.50 | home | 46 | 84.78% | 40.98% | +43.80% |
| over_under | 11.00+ | over_2_5 | 53 | 49.06% | 6.34% | +42.72% |
| match_winner | 1.90-2.00 | home | 51 | 94.12% | 51.51% | +42.61% |
| over_under | 1.10-1.20 | under_2_5 | 164 | 49.39% | 88.64% | -39.25% |
| match_winner | 2.50-2.60 | home | 51 | 76.47% | 39.58% | +36.89% |
| over_under | 7.00-7.10 | over_2_5 | 31 | 48.39% | 14.29% | +34.10% |
| over_under | 1.50-1.60 | under_2_5 | 151 | 31.13% | 64.82% | -33.69% |
| match_winner | 3.80-3.90 | home | 36 | 58.33% | 26.18% | +32.15% |
| over_under | 1.30-1.40 | over_2_5 | 61 | 42.62% | 74.51% | -31.89% |
| match_winner | 2.30-2.40 | home | 41 | 73.17% | 42.85% | +30.32% |

## Part D — Edge Detection

| Threshold | Min N |
|-----------|-------|
| Weak signal | 15 |
| Persistent bias | 30 |
| Strong bias | 50 |

Persistent biases (n≥30, |gap|≥5pp): **84**
Strong biases (n≥50, |gap|≥7pp): **46**

### Persistent overpricing

- over_under 1.10-1.20 under_2_5: gap -39.25% (n=164)
- over_under 1.50-1.60 under_2_5: gap -33.69% (n=151)
- over_under 1.30-1.40 over_2_5: gap -31.89% (n=61)
- match_winner 3.10-3.20 draw: gap -29.39% (n=115)
- match_winner 2.80-2.90 draw: gap -25.66% (n=42)

### Persistent underpricing

- match_winner 2.40-2.50 home: gap +43.80% (n=46)
- over_under 11.00+ over_2_5: gap +42.72% (n=53)
- match_winner 1.90-2.00 home: gap +42.61% (n=51)
- match_winner 2.50-2.60 home: gap +36.89% (n=51)
- over_under 7.00-7.10 over_2_5: gap +34.10% (n=31)

## Part E — Prior Feasibility

| Prior weight | Brier | N |
|--------------|-------|---|
| 0% | 0.1983 | 564 |
| 1% | 0.198 | 564 |
| 5% | 0.197 | 564 |
| 10% | 0.1958 | 564 |

Best prior weight: **10%**
Brier improvement: **0.0025**
Prior feasible: **True**

## Part F — Decision Questions

1. **Do odds buckets contain predictive information?** True
2. **Are there persistent biases?** True
3. **Is MBI worth building?** True
4. **Which markets benefit most?** match_winner

### Final recommendation: **`MBI_MEDIUM_VALUE`**

Detectable calibration gaps; modest prior lift at low blend weights

### Market ranking by signal score

- **match_winner**: signal=649.81, biased_buckets=65, n=8928
- **over_under**: signal=481.53, biased_buckets=19, n=5722
- **anytime_goalscorer**: signal=0.0, biased_buckets=0, n=288
- **first_team_to_score**: signal=0.0, biased_buckets=0, n=36

---

## Constraints honored

- No deploy, production integration, or modeling changes
- Cache-first historical odds intelligence only