# OU25 Regime Mining Report

**Status:** `OU25_REGIME_MINING_PARTIAL_ODDS_LIMITED`  
**Program:** `TRUE_FORWARD_OU25_REGIME_MINING_AND_ECSE_DIRECTION_FILTERING`

## Dataset

| Cohort | N |
|---|---|
| True-forward O/U | 168 |
| Historical prematch O/U | 52 |
| Combined unique | 220 |

## Raw O/U performance

- Combined accuracy: **53.2%**
- Over-only: n=98 acc=59.2%
- Under-only: n=122 acc=48.4%
- Official priced N: **0**

## Best rules

### N≥30
- Name: `over_lambda_ge_2_5_prob_ge_60`
- Side: over_2_5
- Conditions: ['total_lambda>=2.5', 'over_probability>=0.60', 'selected=over_2_5']
- N / coverage / accuracy: 54 / 24.5% / 66.7%
- Wilson: {'low': 0.5336071462745029, 'high': 0.7775875647984964, 'center': 0.6555973555364997}
- Priced N / ROI / DD: 0 / n/a / 0.0
- Worst fold: 0.42857142857142855
- Label: OU25_DIAGNOSTIC_RULE

### N≥50
- `over_lambda_ge_2_5_prob_ge_60` — n=54 acc=66.7% label=OU25_DIAGNOSTIC_RULE

### N≥100
- `None` — n=None acc=n/a label=None

## Robust edge?

`False` — program label `OU25_PROMISING_RESEARCH_RULE` — promising count `5`

## ECSE Direction filtering

- Raw: 53.0%
- Best filter: `home_only_agree` n=62 acc=72.6% coverage=36.9%

## Exact Top5 segments

- Overall TF Top5: 45.2% (n=168)

## Odds limitation

Official O/U priced rows are sparse on true-forward freezes. ROI claims require OFFICIAL_PRICED only; screenshot/research prices are separated.

## Safety

NOT DEPLOYED · CANONICAL UNCHANGED · WDE UNCHANGED · ECSE UNCHANGED · FREEZES UNCHANGED · NO PREDICTIONS REGENERATED · NO AUTO-PROMOTION · NO RESULT LEAKAGE
