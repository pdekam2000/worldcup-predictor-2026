# CORRECT SCORE ODDS — PROVIDER CAPABILITY AUDIT

**Generated:** 2026-07-16 04:25:46 UTC  
**Phase status (ingestion):** `CORRECT_SCORE_ODDS_INGESTION_COMPLETE`

## Providers

| Provider | CS available | Prematch | Historical | Bookmaker-level | Preferred rank |
|---|---|---|---|---|---|
| api_football | yes | yes | partial_via_cached_snapshots | yes | 1 |
| sportmonks | yes | yes | partial_via_premium_odds_include | yes | 2 |
| manual_owner_import | yes_with_confirmation | yes | owner_provided_only | yes | 3 |
| oddalerts | no | n/a | no | n/a | 99 |
| the_odds_api | no | h2h_totals_only | no_for_cs | yes_for_h2h | 99 |
| historical_csv_odds | no | 1x2_ou_btts_only | no_cs | yes_for_non_cs | 99 |


## Preferred ingestion order

1. **api_football** — Correct Score in bookmaker bets (confirmed)
2. **sportmonks** — Correct Score when premium odds include available
3. **manual_owner_import** — confirmed transcription only
4. OddAlerts / The Odds API / CSV — **not used for CS** (unsupported)

## Canonical market

- Market: `CORRECT_SCORE_90_MINUTES`
- Selection: `home_goals-away_goals` (e.g. `1-0`)
- Separate: `ANY_OTHER_HOME_WIN` / `ANY_OTHER_DRAW` / `ANY_OTHER_AWAY_WIN`
- Reject: 1st/2nd half, AET, penalties, combo result+score markets

## Cache-first extraction result

- Snapshots scanned: 0
- Fixtures scanned: 136
- Lines inserted: 0
- Deduped: 0
- Rejected: 0
- API calls: **0** (this run)

## Historical

Legitimate CS odds extracted from existing append-only odds_snapshots. OddAlerts/CSV historical CS unavailable. Provider historical CS archive not claimed.

Fixtures with prematch CS locally: **136**

## Forward collection

Planned rows: 1000  
Upcoming fixtures: 200  
Stops at kickoff: **yes**  
Target portfolios: 100–500

## Completeness (sample)

Average exact scores quoted (best odds map): **119.2**

## Constraints

- No fabricated odds
- No synthetic-as-real
- No freeze/ECSE/WDE changes
- No automatic betting
