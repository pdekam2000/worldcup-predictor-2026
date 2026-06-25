# PHASE 54Q-1 — UEFA Goalscorer Odds Coverage Audit

**Date:** 2026-06-24  
**Mode:** Coverage Audit → Impact Analysis → Report  
**Status:** Complete — research only  
**API calls:** 0

### Final recommendation: **`BOTH_LIMITED`**

**Primary limitation:** C_both (A=model, B=odds, C=both)

---

## Part A — UEFA odds coverage

### Sportmonks cache (strict goalscorer markets)

| League | Fixtures | With GS odds | Coverage % | Bookmakers |
|--------|----------|--------------|------------|------------|
| champions_league | 600 | 0 | 0.0% | — |
| europa_league | 578 | 3 | 0.5% | bet365 |
| conference_league | 464 | 0 | 0.0% | — |
| world_cup | 47 | 0 | 0.0% | — |

### Dataset v3 (API-Football WC bridge overlay)

| League | Fixtures | With odds | Coverage % |
|--------|----------|-----------|------------|
| champions_league | 525 | 0 | 0.0% |
| europa_league | 535 | 0 | 0.0% |
| conference_league | 434 | 0 | 0.0% |
| world_cup | 47 | 47 | 100.0% |

**UEFA dataset v3 coverage:** 0.0%

## Part B — WC vs UEFA comparison

| Segment | Fixtures | Composite Top-3 | Top-5 | ML Top-3 | Blend Top-3 |
|---------|----------|-----------------|-------|----------|-------------|
| WC with odds | 47 | 0.7714 | 0.8857 | 0.7143 | 0.8 |
| UEFA without odds | 1494 | 0.5658 | 0.695 | 0.5836 | 0.5836 |
| UEFA all | 1494 | 0.5658 | 0.695 | 0.5836 | 0.5836 |

## Part C — Counterfactual (estimate only)

| Metric | Value |
|--------|-------|
| WC measured odds lift (blend vs ML) | 0.0857 |
| UEFA current ML top-3 | 0.5836 |
| UEFA current composite top-3 | 0.5658 |
| Estimated UEFA top-3 if WC odds lift applied | 0.6693 |
| Plausible range | [0.6407, 0.6693] |
| Would reach 70%? | False |

## Part D — Feature contribution (top-3 drop when removed)

### world_cup

Baseline top-3: 0.7714

- odds: +0.0857
- xg: +0.0571
- lineup: +0.0285
- starter_probability: +0.0285
- form: +0.0000

### uefa

Baseline top-3: 0.5658

- xg: +0.0039
- odds: +0.0000
- lineup: -0.0077
- starter_probability: -0.0077
- form: -0.0162

### overall

Baseline top-3: 0.5712

- xg: +0.0053
- odds: +0.0022
- lineup: -0.0068
- starter_probability: -0.0068
- form: -0.0158

## Part E — Decision

| Question | Answer |
|----------|--------|
| Is engine limited by model quality? | Yes (UEFA ML top-3 = 0.5836) |
| Is engine limited by odds coverage? | Yes (0.0% UEFA coverage) |
| WC vs UEFA top-3 gap | 0.2056 |
| WC odds lift | 0.0857 |

### Final recommendation: **`BOTH_LIMITED`**

---

## Constraints honored

- No modeling changes
- No deploy, production, WDE, SaaS, or live prediction changes
