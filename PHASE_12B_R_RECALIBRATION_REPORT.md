# Phase 12B-R — Lambda Bridge Recalibration Report

Generated: 2026-06-19T16:27:52.404735+00:00

## Mode

- Simulation only — no deploy, no production changes

## Production baseline (unchanged)

| Metric | Value |
|--------|-------|
| Fixtures | 82 |
| Evaluated | 72 |
| Conflict rate | 74.4% |
| Accuracy | 43.1% |
| Draw rate | 73.2% |

Grid combinations tested: **2880**
Candidates passing all gates: **0**

## Success gates

- Shadow accuracy ≥ production baseline
- Shadow conflict rate < production
- Shadow draw rate < production
- No single signal > 55% of total |Δλ|
- Global cap applied ≤ 40% of fixtures

## Top candidates

| Rank | Name | Accuracy | Conflict | Draw | Avg |Δλ| | Cap% | Dominance | Pass |
|------|------|----------|----------|------|---------|------|-----------|------|
| 1 | B_injury_only | 43.1% | 74.4% | 73.2% | 0.001 | 0.0% | 100.0% | ✗ |
| 2 | A_market_only | 41.7% | 72.0% | 70.7% | 0.012 | 0.0% | 100.0% | ✗ |
| 3 | D_market_injury | 41.7% | 72.0% | 70.7% | 0.011 | 0.0% | 93.8% | ✗ |
| 4 | E_market_lineup | 41.7% | 72.0% | 70.7% | 0.013 | 0.0% | 77.0% | ✗ |
| 5 | G_market_injury_lineup | 41.7% | 72.0% | 70.7% | 0.013 | 0.0% | 73.3% | ✗ |
| 6 | H_no_tournament | 41.7% | 72.0% | 70.7% | 0.013 | 0.0% | 73.3% | ✗ |
| 7 | C_lineup_only | 41.7% | 75.6% | 74.4% | 0.005 | 0.0% | 100.0% | ✗ |
| 8 | F_injury_lineup | 41.7% | 75.6% | 74.4% | 0.007 | 0.0% | 81.8% | ✗ |

## Best candidate

**B_injury_only**

```json
{
  "global_cap": 0.08,
  "market_cap": 0.04,
  "injury_cap": 0.04,
  "lineup_cap": 0.04,
  "tournament_cap": 0.02,
  "dq_disable_below": 45.0,
  "active_agents": [
    "injury_suspension_intelligence_agent"
  ]
}
```

- Accuracy: 43.1% (baseline 43.1%)
- Conflict: 74.4% (baseline 74.4%)
- Draw rate: 73.2% (baseline 73.2%)
- Home/Away: 21.9% / 4.9%
- Avg |Δλ|: 0.0013
- Global cap applied: 0.0%
- Max agent share: 100.0%
- Conflicts improved/worsened: 0/0

### Why safer

- Near-miss: conflict 74.4% not below 74.4%, draw rate 73.2% not below 73.2%, single signal dominance 100.0% > 55%

## Ablation summary (best grid caps)

| Scenario | Accuracy | Conflict | Draw | Pass |
|----------|----------|----------|------|------|
| A_market_only | 41.7% | 72.0% | 70.7% | ✗ |
| B_injury_only | 43.1% | 74.4% | 73.2% | ✗ |
| C_lineup_only | 41.7% | 75.6% | 74.4% | ✗ |
| D_market_injury | 41.7% | 72.0% | 70.7% | ✗ |
| E_market_lineup | 41.7% | 72.0% | 70.7% | ✗ |
| F_injury_lineup | 41.7% | 75.6% | 74.4% | ✗ |
| G_market_injury_lineup | 41.7% | 72.0% | 70.7% | ✗ |
| H_no_tournament | 41.7% | 72.0% | 70.7% | ✗ |

## Verdict: **PAUSE BRIDGE**

## Recommendation: **Pause bridge activation — recalibration cannot satisfy accuracy + conflict gates simultaneously on this replay set**

### Key finding

Across **2,880** parameter combinations and **8** ablation scenarios:

- **0** candidates achieved shadow accuracy ≥ production (**43.1%**) while also reducing conflict below **74.4%**.
- Any configuration that materially reduces conflict (best **72.0%**, −2.4 pp) drops accuracy to **41.7%** (−1.4 pp).
- **Injury-only** ablation preserves accuracy but applies negligible |Δλ| (no conflict/draw change).
- **Market-led** stacks (market, market+injury, market+lineup, no-tournament) all share the same conflict/draw profile and fail the accuracy gate.

### Best Pareto tradeoff (if research continues)

| Parameter | Value |
|-----------|-------|
| `GLOBAL_LAMBDA_CAP` | 0.08 |
| `market_consensus_agent` cap | 0.04 |
| `injury` cap | 0.02 |
| `lineup` cap | 0.02 |
| `tournament` cap | 0.00 |
| `DQ_DISABLE_BELOW` | 45 |

| Metric | Production | This candidate |
|--------|------------|----------------|
| Accuracy | 43.1% | 41.7% |
| Conflict | 74.4% | 72.0% |
| Draw rate | 73.2% | 70.7% |
| Avg \|Δλ\| | 0 | ~0.012 |

**Why not 12C-safe:** accuracy gate fails; market signal still dominates total |Δλ| (>55%).

### Phase 12C shadow production

**Not safe to proceed** until a new bridge design (e.g. asymmetric draw guard, scoreline-aware cap, or WDE-aligned λ mapping) is tested.

## Safety

- No deployment performed
- Production predictions unchanged
- Recalibrated params are simulation-only until explicit 12C config update

