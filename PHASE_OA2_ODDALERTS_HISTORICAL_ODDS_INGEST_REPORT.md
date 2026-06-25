# PHASE OA-2 — OddAlerts Historical Odds Ingest

**Generated:** 2026-06-23T12:32:38.232771+00:00  
**Mode:** Ingest → Store → Validate → Report  
**Production / prediction engine:** UNCHANGED  

---

## Summary

- **API key configured:** True
- **API calls used (test runs):** 28
- **SQLite DB:** `data/football_intelligence.db`
- **Fixture map rows:** 3 (pipeline smoke — world_cup)
- **Odds history rows:** 902
- **Internal mapping rows:** 0 (no internal WC fixtures in DB)

## Test Runs

### champions_league season 2024
- Discovered: **0** | Processed: **0** | API calls: **26**
- Mapping: exact=0, fuzzy=0, unmatched=0
- Odds rows stored: **0**
- Internal fixtures in DB: 25
- Message: Zero OddAlerts fixtures discovered for requested league/season on trial token
### premier_league season 2023
- Discovered: **0** | Processed: **0** | API calls: **1**
- Mapping: exact=0, fuzzy=0, unmatched=0
- Odds rows stored: **0**
- Internal fixtures in DB: 380
- Message: Zero OddAlerts fixtures discovered for requested league/season on trial token
### bundesliga season 2023
- Discovered: **0** | Processed: **0** | API calls: **1**
- Mapping: exact=0, fuzzy=0, unmatched=0
- Odds rows stored: **0**
- Internal fixtures in DB: 308
- Message: Zero OddAlerts fixtures discovered for requested league/season on trial token

### Pipeline smoke — world_cup season 2022 (storage verification)
- Discovered: **32** | Processed: **3** | API calls: **6**
- Odds rows stored: **902**
- Mapping: unmatched=3 (no internal WC fixtures in SQLite)

## Validation

- Checks passed: **11/12**

- ✓ api_key_present
- ✓ tables_exist
- ✓ fixtures_mapped
- ✓ odds_rows_stored
- ✓ opening_odds_stored
- ✓ closing_odds_stored
- ✓ peak_odds_stored
- ✓ bookmakers_stored
- ✓ markets_stored
- ✓ no_duplicate_rows
- ✓ resume_state_rows
- ✗ internal_fixture_mapping (expected — no PL/CL/BL OA fixtures in trial pool)

## Coverage

- Opening odds rows: **902**
- Closing odds rows: **902**
- Peak odds rows: **902**
- Bookmakers: 1xBet, Bet365, Kambi Group, Pinnacle, WilliamHill, Betfair Exchange, Betano, FanDuel
- Markets: total_corners, total_goals, asian_handicap, ft_result, btts, home_goals, away_goals, …
- Mapping confidence: {"unmatched": 3}

## PostgreSQL / SQLite Status

OddAlerts tables live in **SQLite** intelligence DB (`oddalerts_fixture_map`, `oddalerts_odds_history`, `oddalerts_ingest_state`, `oddalerts_ingest_runs`). PostgreSQL SaaS DB untouched. API-Football and Sportmonks tables unchanged.

## Recommendation for Full Backfill

Trial token **did not expose** England PL / UEFA CL / Germany Bundesliga finished fixtures in the `value/results` pool (~4.4k rows scanned; competition IDs 423/51/477 absent). Target league test runs stored **0** odds rows.

**Pipeline smoke test (world_cup):** 3 fixtures ingested, **902** odds history rows stored (opening/closing/peak + bookmakers). Confirms DB schema, cache-first fetch, resume state, and `odds/history` parsing work end-to-end.

Before full backfill for PL/CL/BL: confirm OddAlerts plan unlocks competition-scoped `fixtures/results` or filtered historical lists; then re-run with higher `--max-api-calls` and `--discovery-pages`.

---

**STOP — No deploy. No production prediction changes.**
