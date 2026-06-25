# PHASE 54R — Team Context Enrichment for Goalscorer Engine

**Date:** 2026-06-24  
**Mode:** Research → Feature Expansion → Revalidation  
**Status:** Complete — research only  
**API calls:** 0

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Part A — Team context features

Built **14** team-level features joined to player rows.

| Feature | Non-zero rows |
|---------|---------------|
| team_attack_strength | 40,827 |
| team_defensive_weakness | 40,698 |
| team_recent_goals_scored | 40,164 |
| team_recent_goals_conceded | 39,553 |
| team_rolling_xg | 35,471 |
| team_rolling_xga | 35,223 |
| team_league_position | 47,029 |
| team_elo_strength | 47,029 |
| team_home_attack | 38,943 |
| team_away_attack | 37,644 |
| is_home | 23,659 |
| is_favorite | 24,780 |
| is_underdog | 21,545 |
| team_attacking_share | 21,840 |

Artifact: `artifacts/phase54r_team_context_goalscorer/goalscorer_dataset_v4.parquet`

## Part B — Dataset v4

| Metric | Value |
|--------|-------|
| Rows | 47,029 |
| Fixtures | 1541 |

## Part C — Feature group test (test split)

| Group | Top-1 | Top-3 | Top-5 | MRR |
|-------|-------|-------|-------|-----|
| player_only | 0.3175 | 0.6296 | 0.7619 | 0.5106 |
| player_lineup | 0.3386 | 0.672 | 0.7884 | 0.5381 |
| player_team | 0.3386 | 0.6667 | 0.8042 | 0.5392 |
| player_team_odds | 0.3386 | 0.6667 | 0.8042 | 0.5392 |

## Part D — Team feature importance

Baseline player+team top-3: **0.6667**

| Feature | Top-3 drop when removed | Verdict |
|---------|-------------------------|---------|
| is_home | +0.0053 | positive |
| team_defensive_weakness | +0.0000 | neutral |
| team_recent_goals_scored | +0.0000 | neutral |
| team_elo_strength | +0.0000 | neutral |
| team_home_attack | +0.0000 | neutral |
| team_away_attack | +0.0000 | neutral |
| team_attack_strength | -0.0053 | harmful |
| team_recent_goals_conceded | -0.0053 | harmful |
| team_rolling_xg | -0.0053 | harmful |
| team_rolling_xga | -0.0053 | harmful |
| team_league_position | -0.0053 | harmful |
| is_underdog | -0.0053 | harmful |
| team_attacking_share | -0.0053 | harmful |
| is_favorite | -0.0105 | harmful |

**Positive:** is_home  
**Neutral:** 5 features  
**Harmful:** team_attack_strength, team_recent_goals_conceded, team_rolling_xg, team_rolling_xga, team_league_position, is_favorite, is_underdog, team_attacking_share

## Part E — UEFA impact (test split)

| League | Lineup Top-3 | Team Top-3 | Δ pp |
|--------|--------------|------------|------|
| **UEFA overall** | 0.6623 | 0.6429 | -0.0194 |
| champions_league | 0.78 | 0.76 | -0.02 |
| europa_league | 0.623 | 0.623 | 0.0 |
| conference_league | 0.5814 | 0.5349 | -0.0465 |

54Q baseline UEFA composite: **0.5658**

## Part F — Elite recheck

| Check | Value |
|-------|-------|
| UEFA player+team top-3 | 0.6429 |
| Elite threshold | 0.65 |
| Reaches elite | **False** |
| Best test group | player_lineup (0.672) |

## Part G — Decision questions

1. **Does team context help?** True (lift 0.0371 pp test; UEFA +-0.0194 pp)
2. **Which team features matter?** 1 positive — top: is_home
3. **Does UEFA improve?** False
4. **Still HIGH_VALUE?** True
5. **Elite realistic?** False

### Final recommendation: **`GOALSCORER_HIGH_VALUE`**

---

## Constraints honored

- No production, deploy, WDE, SaaS, or live prediction changes
- No EGIE scoring changes
