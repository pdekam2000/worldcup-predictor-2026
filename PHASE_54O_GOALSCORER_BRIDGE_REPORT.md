# PHASE 54O — API-Football Goalscorer Odds Bridge

**Date:** 2026-06-24  
**Mode:** Data Bridge → Mapping Expansion → Revalidation → Report  
**Status:** Complete — research only  
**API calls:** 0

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Part A — Fixture bridge

| Metric | Value |
|--------|-------|
| API-Football GS fixtures | **72** |
| Mapped (HIGH) | **43** |
| Partial (MEDIUM/LOW) | 4 |
| Unmapped | 25 |
| With Sportmonks lineups | 47 |

Artifact: `artifacts/phase54o_goalscorer_bridge/fixture_bridge.json`

## Part B — Team resolution

Home/away teams resolved via Sportmonks WC cache + `team_names_match` aliases.

## Part C — Player mapping expansion

| Metric | Value |
|--------|-------|
| Selections processed | 19941 |
| **Mapping rate** | **93.7%** |
| HIGH confidence | 17949 |
| MEDIUM confidence | 744 |
| Unmapped | 1248 |

## Part D — Goalscorer dataset v2

| Metric | Value |
|--------|-------|
| Rows | 1416 |
| Fixtures | 47 |
| Rows with anytime odds | 1346 |

Artifact: `artifacts/phase54o_goalscorer_bridge/goalscorer_dataset_v2.parquet`

## Part E — Revalidation (Anytime)

| Signal | Top-1 | Top-3 | Top-5 |
|--------|-------|-------|-------|
| ML only | 0.4571 | 0.7143 | 0.8 |
| Odds only | 0.6286 | 0.7714 | 0.8571 |
| ML + Odds blend | 0.5429 | 0.8 | 0.8571 |

### Calibration

| Track | Brier | ECE |
|-------|-------|-----|
| ml_only | 0.2212 | 0.3961 |
| odds_only | 0.0702 | 0.1261 |
| ml_odds_blend | 0.1352 | 0.2879 |

## Part F — Edge analysis

| Metric | Value |
|--------|-------|
| Agreement % | 0.8857 |
| Disagreement % | 0.1143 |
| Disagree-group hit rate | 0.75 |
| **Edge value** | **MEDIUM** |

## Part G — Decision questions

1. **WC fixtures bridged:** 47 of 72 (HIGH=43)
2. **Mapping rate:** 93.7%
3. **ML+Odds beats ML alone (top-3):** True
4. **Bookmaker adds value:** odds top-3=0.7714
5. **Calibration improved by blend:** blend Brier 0.1352 vs ML 0.2212
6. **Goalscorer HIGH_VALUE:** True
7. **Build next:** fixture-lineup bridge for unmapped 29 fixtures; expand beyond WC; production shadow capture

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Constraints honored

- No production integration
- No WDE / SaaS / deploy changes
- No live prediction changes
- No EGIE scoring changes
