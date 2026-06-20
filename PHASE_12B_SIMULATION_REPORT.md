# Phase 12B — Specialist Lambda Bridge Simulation Report

Generated: 2026-06-19T16:17:05.265756Z

## Mode

- **Bridge mode:** SHADOW (simulation only)
- **Production pipeline:** unchanged
- **Deploy:** NO

## Summary

| Metric | Production | Shadow |
|--------|------------|--------|
| Fixtures simulated | 82 | 82 |
| Evaluated (with results) | 72 | 72 |
| Conflict rate | 75.6% | 70.7% |
| 1X2 accuracy | 43.1% | 40.3% |
| Draw prediction rate | 73.2% | 68.3% |
| Home win rate | 21.9% | 24.4% |
| Away win rate | 4.9% | 7.3% |

**Conflict improved:** 4 fixtures  
**Conflict worsened:** 0 fixtures  
**Global cap applied:** 0.0% of fixtures  
**DQ scaling applied:** 93.9% of fixtures  

## Bridge contribution analysis

### Strongest specialist λ signals (avg |Δλ|)

- `market_consensus_agent`: 0.1668
- `injury_suspension_intelligence_agent`: 0.0357
- `lineup_intelligence_agent`: 0.0322
- `tournament_intelligence_agent`: 0.0135

### Weakest specialist λ signals

- `tournament_intelligence_agent`: 0.0135
- `lineup_intelligence_agent`: 0.0322
- `injury_suspension_intelligence_agent`: 0.0357
- `market_consensus_agent`: 0.1668

## Success criteria

- Conflict reduction: YES (75.6% → 70.7%)
- Accuracy preserved: NO (43.1% → 40.3%)

## Verdict: **FAIL — RECALIBRATE**

## Recommendation: **Recalibrate (accuracy degradation detected)**

## Safety

- Bridge runs in parallel shadow path only
- Production λ, scoreline, harmonization unchanged
- Fail-closed: bridge errors do not affect production
- No API/UI/deploy changes in this phase

## Sample conflicts resolved

- Fixture 1489376 (Netherlands vs Japan): WDE `home_win` → prod `draw` → shadow `home_win` (λ 1.16/1.01 → 1.2127/0.9848)
- Fixture 1489379 (Saudi Arabia vs Uruguay): WDE `away_win` → prod `draw` → shadow `away_win` (λ 1.06/1.5 → 0.961/1.5236)
- Fixture 1539003 (Portugal vs Congo DR): WDE `home_win` → prod `draw` → shadow `home_win` (λ 1.18/1.05 → 1.2623/0.9951)
- Fixture 1539016 (Iraq vs Norway): WDE `away_win` → prod `draw` → shadow `away_win` (λ 1.01/1.9 → 0.9346/1.9823)
