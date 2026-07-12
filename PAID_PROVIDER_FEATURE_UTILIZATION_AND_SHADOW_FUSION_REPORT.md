# Paid Provider Feature Utilization and Shadow Fusion Report

Date: 2026-07-12

## Final recommendation

**FEATURE_COVERAGE_BACKFILL_REQUIRED**

---

## Executive answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Features fetched? | API-Football (broad), SportMonks (enrichment/xG/pressure), OddAlerts (CSV+API), The Odds API, RapidAPI, Weather |
| 2 | Features stored? | `odds_snapshots`, `fixture_enrichment`, CSV staging (77k rows), OddAlerts 8.7M rows, sparse xG/pressure |
| 3 | Affect WDE? | Form, H2H, injuries, lineups, odds implied probs (primary) |
| 4 | Affect ECSE? | Odds lambdas (production); OddAlerts shadow only |
| 5 | Affect BTTS/O-U? | Implied odds + Poisson extended markets |
| 6 | Unused? | Pressure, post-match stats, provider prediction models, most SportMonks xG |
| 7 | Historical coverage? | Odds: high in CSV (77k); SQLite odds 100% of 868 completed w/ odds; xG 2.8% |
| 8 | Leakage risk? | CSV realized xG, post-match stats, closing odds, live pressure |
| 9 | Improved WDE? | Full safe fusion Δ1x2 accuracy = **0.0003** |
| 10 | Improved calibration? | See ablation calibration_error per family |
| 11 | Improved BTTS? | See holdout BTTS accuracy per variant in experiments JSON |
| 12 | Improved O/U? | See holdout O/U accuracy per variant |
| 13 | Improved ECSE? | Odds-proxy Top1/Top3/Top5 in experiments JSON |
| 14 | Harmed performance? | Lineup/pressure proxies (no data) = baseline equivalent |
| 15 | Highest-value provider? | **API-Football odds** (primary, highest coverage) |
| 16 | Not worth API cost? | Live pressure fetches, redundant post-match stats for pre-match models |
| 17 | Full fusion vs baseline? | Holdout 1X2: baseline **0.506** vs full **0.5063** |
| 18 | Stable by competition? | See `by_league` in experiments JSON |
| 19 | Stable by Tier? | Tier B shadow only; Tier A uses same odds path — no Tier-specific lift proven |
| 20 | Ready for longer shadow? | Odds-derived features only, if Δ > 0 and calibration stable |
| 21 | Additional data required? | Pre-match SportMonks xG snapshots, timestamped lineup/injury snapshots |
| 22 | Next phase? | Coverage backfill for safe prematch xG + 30-day live shadow of odds-enhanced fusion |

---

## Experiment summary (chronological holdout)

| Variant | 1X2 accuracy | Δ vs baseline | Log loss | Cal error |
|---------|--------------|---------------|----------|-----------|
| A baseline | 0.506 | — | 1.0024393699241971 | 0.0127 |
| H full safe | 0.5063 | 0.0003 | 1.001998286329863 | 0.0038 |
| C xG diagnostic | 0.5063 | 0.0003 | 0.9980372840908035 | *non-promotable* |

**Provider calls this phase:** 0  
**Production modified:** false  
**Shadow storage:** `production_visible=false`

---

## Artifacts

- `artifacts/provider_feature_fusion/coverage_audit.json`
- `artifacts/provider_feature_fusion/fusion_experiments.json`
- `artifacts/provider_feature_fusion/ablation_report.json`
- `artifacts/provider_feature_fusion/feature_importance.json`
- `artifacts/provider_feature_fusion/shadow_dataset.parquet`

**STOP** — No model deployment. No production promotion.
