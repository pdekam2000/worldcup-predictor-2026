# ECSE-X2-M2 — Market Algebra Equation Miner

**Phase:** ECSE-X2-M2  
**Method:** `ECSE-X2-M2-v1`  
**Equations tested:** 24  
**Equations accepted:** 10  

## Goal

Search hidden mathematical relationships between prematch odds markets that improve
ECSE exact-score ranking via quantile-conditioned reorder rules (train 70% / test 30%).

## Baseline (temporal test slice)

- Fixtures: **50,470**
- Top-1: **10.7926%**
- Top-3: **28.8151%**
- Top-5: **43.4734%**
- Log loss: **6.969037**

## Top 20 equations (ranked)

| Rank | Equation | Test n | Top-1 Δ | Top-3 Δ | Top-5 Δ | LogLoss Δ | Status |
|------|----------|--------|---------|---------|---------|-----------|--------|
| 1 | `log(home_prob) / log(1.618)` | 16,502 | +1.0847 | +1.6301 | +3.2965 | -0.175990 | accepted |
| 2 | `under25_prob / btts_no_prob` | 5,761 | +0.1389 | +0.6249 | -0.1389 | -0.091652 | accepted |
| 3 | `fh_home_prob - ft_home_prob` | 3,757 | -0.0266 | -0.2395 | +1.2510 | -0.177353 | accepted |
| 4 | `-abs(over25_prob - 0.618)` | 34,233 | +0.0818 | -0.3563 | -0.0585 | -0.162131 | single_league_concentration |
| 5 | `corners_o85_prob / over25_prob` | 9,669 | -0.2482 | -0.3723 | -0.3516 | -0.171778 | accepted |
| 6 | `corner_over95_prob - over25_prob` | 5,407 | -0.3329 | -0.4069 | -0.3329 | -0.181910 | accepted |
| 7 | `-abs(over25_prob - 1.618)` | 34,233 | -0.0497 | -0.6572 | -0.3331 | -0.154745 | single_league_concentration |
| 8 | `-abs(over25_prob - 2.618)` | 34,233 | -0.0497 | -0.6572 | -0.3331 | -0.154745 | single_league_concentration |
| 9 | `log(over25_prob) / log(1.618)` | 34,233 | -0.0497 | -0.6572 | -0.3331 | -0.154745 | single_league_concentration |
| 10 | `over25_prob / btts_yes_prob` | 10,649 | -0.3287 | -0.7043 | -0.1221 | -0.171545 | accepted |
| 11 | `btts_yes_prob * over25_prob` | 10,649 | -0.4883 | -0.5916 | -0.9860 | -0.160745 | accepted |
| 12 | `log(btts_yes_prob) / log(1.618)` | 13,953 | -0.3010 | -0.6880 | -1.1396 | -0.151893 | accepted |
| 13 | `(home_prob + over25_prob + btts_yes_prob) / 3` | 3,296 | +0.4248 | -1.8507 | +0.0910 | -0.169863 | accepted |
| 14 | `over15_prob / under35_prob` | 29,127 | -0.6729 | -0.8583 | -1.1948 | -0.112727 | single_league_concentration |
| 15 | `home_team_o15_prob - away_team_o05_prob` | 3,705 | +0.9177 | -2.2402 | -0.8098 | -0.175296 | accepted |
| 16 | `(home_prob + away_prob) / draw_proxy` | 0 | +0.0000 | +0.0000 | +0.0000 | +0.000000 | train_sample_too_small |
| 17 | `abs(home_prob - away_prob) / over25_prob` | 0 | +0.0000 | +0.0000 | +0.0000 | +0.000000 | train_sample_too_small |
| 18 | `fh_draw_prob / draw_proxy` | 0 | +0.0000 | +0.0000 | +0.0000 | +0.000000 | train_sample_too_small |
| 19 | `(draw_proxy + under25_prob + btts_no_prob) / 3` | 0 | +0.0000 | +0.0000 | +0.0000 | +0.000000 | train_sample_too_small |
| 20 | `(home_prob / away_prob) * draw_proxy` | 0 | +0.0000 | +0.0000 | +0.0000 | +0.000000 | train_sample_too_small |

## Rejection rules

- Train sample < 5,000
- Test sample < 3,000
- Log loss worsens by > 0.005
- No OOS top-3 lift when log loss worsens
- Improvement concentrated in < 3 leagues (n≥800)

## Safety

- Baseline `ecse_score_distributions` rows unchanged: **10,935,145**
- No API calls, no retraining, no deployment
- Prematch odds only in reorder (results used for evaluation only)

## Artifact

- `C:/Users/kaman/Desktop/Footbal/artifacts/ecse_x2_m2_equation_rankings.json`
