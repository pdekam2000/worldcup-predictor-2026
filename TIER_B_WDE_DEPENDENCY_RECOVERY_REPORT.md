# Tier B WDE Dependency Recovery Report

**Final status:** `TIER_B_WDE_EXECUTION_RECOVERED`

## SHA Record

| Location | Before | After |
|---|---|---|
| LOCAL HEAD | a0dbdc0 | 01d08d2 |
| ORIGIN/main | a0dbdc0 | 01d08d2 |
| PRODUCTION HEAD | a0dbdc0 | 01d08d2 |

## Answers (25)

1. **Exact dependency failed:** `API_FOOTBALL_KEY` not loaded because `APP_ENV=production` was unset in direct script/worker paths → `settings.api_football_configured=false`.
2. **Why ECSE ran but WDE did not:** ECSE path bypasses API credentials gate; WDE gate in `run_daily_wde()` blocks before `PredictPipeline`.
3. **Competition-specific?** No — eliteserien and urvalsdeild both recover with bootstrap.
4. **Urvalsdeild normalization wrong?** No — `urvalsdeild` / `league_164` normalize correctly.
5. **Eliteserien routing wrong?** No — `eliteserien` / `league_103` route correctly.
6. **API cache involved?** Indirectly — cache/DB sufficient for pipeline; missing env prevented WDE entry.
7. **History coverage missing?** No — pipeline succeeds when credentials load.
8. **Optional treated as mandatory?** No — API key is legitimately mandatory for WDE gate.
9. **Valid payload lost in serialization?** No — payload never generated when gate blocked.
10. **Minimal fix:** `bootstrap_gpt_actions_runtime()` auto-sets `APP_ENV=production`, clears settings cache; worker + MCP runtime call bootstrap; precise failure codes.
11. **WDE formulas unchanged:** Yes.
12. **ECSE formulas unchanged:** Yes.
13. **BTTS recovered:** Yes (via WDE payload).
14. **O/U recovered:** Yes (via WDE payload).
15. **Five fixtures:** All WDE executed post-fix (see E2E JSON).
16. **Jobs completed fully:** 5/5 `completed`.
17. **Partial jobs:** 0 after fix.
18. **Generic code replaced:** Yes — `WDE_API_CREDENTIALS_MISSING` with structured provenance fields.
19. **New Top 3:** 1508805, 1494698, 1508803 (see `OWNER_1700_TOP3_AFTER_WDE_RECOVERY.md`).
20. **Tier B non-public:** Yes — `public_visible=false` on all five.
21. **Regressions:** New tests 18/18 pass; recovery validator 18/18 pass.
22. **Services active:** worldcup-api + worldcup-gpt-actions active post-restart.
23. **Production source clean:** Tracked source at 01d08d2; local data/shadow modifications pre-existing.
24. **Local = Origin = Production:** Yes at 01d08d2.
25. **Result backfill untouched:** Yes.

## E2E Summary (production)

| fixture_id | job_status | WDE | BTTS | O/U | ECSE Top1 | Top3 mass |
|---:|---|---|---|---|---|---:|
| 1494698 | completed | away_win | no | over_2_5 | 0-2 | 0.273 |
| 1508803 | completed | home_win | no | over_2_5 | 3-0 | 0.368 |
| 1508804 | completed | away_win | yes | over_2_5 | 1-1 | 0.281 |
| 1508805 | completed | home_win | no | over_2_5 | 2-0 | 0.383 |
| 1508806 | completed | away_win | no | over_2_5 | 1-1 | 0.280 |

Artifact: `/opt/worldcup-predictor/artifacts/tier_b_wde_recovery/five_fixture_e2e.json`
