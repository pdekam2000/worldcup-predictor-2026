# PHASE OA-3 — Advanced Plan Deep Validation

**Generated:** 2026-06-23T16:11:42.786046+00:00  
**Mode:** Deep audit — no deploy, no production changes  
**API key fingerprint (sha256/16):** `477361cf28af4afe`  
**API calls:** 86  

---

## Executive Answers

1. **Did Advanced unlock PL/UCL/Bundesliga historical data?** **No** — PL finished=0, CL=0, BL=0. Catalogue entries exist; `fixtures/results` returns 0.

2. **Can we backfill 2023→present?** **No** for major leagues on this token. Internal PL fixtures 2023+: 380; OA pool: 0.

3. **First Team To Score historically?** **No direct market** — proxy `home_goals`/`away_goals`: True.

4. **Pinnacle historical coverage?** **Yes on pool fixtures**.

5. **Total fixtures available (target leagues, finished pool):** 12 (World Cup: 12 finished, 28 upcoming).

6. **Worth permanent integration?** **Conditional** — odds/history quality is good on accessible fixtures; major European leagues still absent from data pools.

7. **Recommended role:** **Shadow / odds-only enrichment** — not primary over Sportmonks for UEFA FG.

8. **Material improvement vs API-Football + Sportmonks?** **Marginal** — Sportmonks retains measured FG edge (78.7% sharp MW); OddAlerts adds opening/closing/peak on pool fixtures only.

---

## League Access Summary

| League | ID | Finished pool | Upcoming pool | fixtures/results |
|--------|-----|---------------|---------------|------------------|
| premier_league | 423 | 0 | 0 | 0 |
| bundesliga | 477 | 0 | 0 | 0 |
| la_liga | 419 | 0 | 0 | 0 |
| serie_a | 499 | 0 | 0 | 0 |
| ligue_1 | 200 | 0 | 0 | 0 |
| champions_league | 51 | 0 | 0 | 0 |
| europa_league | 32 | 0 | 0 | 0 |
| conference_league | 976 | 0 | 0 | 0 |
| world_cup | 1690 | 12 | 28 | 0 |

## Artifacts

- `artifacts/oa3_token_capabilities.json`
- `artifacts/oa3_league_access.json`
- `artifacts/oa3_historical_depth.json`
- `artifacts/oa3_odds_history_coverage.json`
- `artifacts/oa3_bookmaker_coverage.json`
- `artifacts/oa3_first_goal_markets.json`
- `artifacts/oa3_backfill_readiness.json`
- `artifacts/oa3_provider_comparison.json`

---

**STOP — No deploy. No production changes.**

