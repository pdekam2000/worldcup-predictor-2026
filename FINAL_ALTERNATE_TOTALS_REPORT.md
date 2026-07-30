# Alternate totals provider audit

## API-Football
- Endpoint: odds by fixture (bookmakers → bets)
- Lines: O/U 2.5 commonly; 3.5 often; 4.5 intermittent by league/book
- Mapping: `api_football_odds_to_ecse_row` now captures 2.5/3.5/**4.5**
- Timestamps: fetch time; freshness via odds age gates
- Rate limit: quota-sensitive — capture only on existing prematch fetch

## OddAlerts / CSV history
- Markets include over_under over_25/35/45 in historical clean table
- Live OddAlerts history mapper now includes 4.5 when market string contains 4.5
- Historical CSV ends ~2026-06-28 — forward July freezes had 0 joins

## Sportmonks
- Enrichment path exists; totals coverage league-dependent
- Do not invent lines when absent

## Staging external odds
- Has ft_goals_over_2_5 / under_2_5 / under_3_5 / over_1_5
- **Missing** over_3_5 and any 4.5 — provider/export gap

## Root cause of missing O/U 3.5/4.5 on eval freezes
1. Freeze schema does not persist alternate totals columns
2. `build_odds_feature_row` previously omitted 4.5 (now fixed additively)
3. `extract_lambdas` still ignores 4.5 (canonical unchanged)
4. Eval kickoffs lack staging/CSV multi-line rows

## Future expected coverage
After this capture path: whenever providers return 3.5/4.5 on live prematch fetches,
shadow table `totals_market_shadow_snapshots` + `alternate_totals_capture_status` record
PRESENT or explicit MISSING — never synthesized.


Retrospective MISSING status rows written in smoke: 15.
