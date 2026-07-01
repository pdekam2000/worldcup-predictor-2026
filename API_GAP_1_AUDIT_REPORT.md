# API-GAP-1 — ECSE Data Gap Audit Report

**Generated:** 2026-06-29 13:06:44 UTC  
**Mode:** Read-only (no API calls during audit)

## Executive summary

ECSE historical odds are dominated by **Bet365 CSV exports**. **FT draw** and **correct score** markets are absent at source. **xg_snapshots** has **0** rows while Sportmonks disk cache has **1634** JSON files. Only **241** of **217,518** ECSE fixtures map to production `fixture_id`.

## ECSE table fingerprints (unchanged baseline)

| Table | Rows |
|-------|------|
| `ecse_training_dataset` | 217,518 |
| `ecse_lambda_features` | 168,233 |
| `ecse_score_distributions` | 10,935,145 |
| `ecse_score_distributions_dc` | 10,935,145 |

## Odds gaps

- ECSE fixtures missing `ft_draw_closing`: **217,518** (100.0%)
- Prematch clean `ft_result` draw rows: **0**
- Prematch `ft_result` home/away: **64,571** / **22,766**
- Correct score markets in prematch clean: **0**
- Root cause tag: **SOURCE_EXPORT_GAP**

### Bookmakers (prematch clean)

- Bet365: 1,908,702 rows

## xG gaps

- `xg_snapshots`: **0** rows
- Sportmonks cache files: **{"data\\feature_store\\sportmonks_xg\\raw": 1554, "data\\egie\\uefa_club\\raw": 80, "total_unique_files": 1634}**
- `sportmonks_fixture_enrichment`: **28** rows

## Fixture intelligence gaps

- `fixture_enrichment` coverage: {"lineups_json": 1531, "statistics_json": 1531, "events_json": 1532, "odds_json": 72}
- `fixture_goal_events`: **6,198**
- `odds_snapshots`: **1,443**
- API cache statistics rows: **161**
- Registry → production mapped: **242** / **223,215**
- ECSE fixtures production-mapped: **241** (unmapped **217,277**)

## OddAlerts staging

- `oddalerts_odds_history`: **902** rows, draw **24**, correct score **0**

## Targeted harvest queue (post-audit)

- Sportmonks xG import candidates: **28**
- OddAlerts draw refetch candidates: **0**
- API-Football stats gap candidates (production fixtures): **500**

---

*Audit only. No API calls. ECSE tables not modified.*