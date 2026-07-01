# Provider Truth Audit Report

**Generated:** 2026-06-30T13:53:32Z
**Phase:** PROVIDER-TRUTH-AUDIT
**Sample fixtures:** 10

## Part A — Provider credential/config

| Provider | Token configured | Base URL | Client | Odds endpoint | Fixture endpoint |
|----------|------------------|----------|--------|---------------|------------------|
| api_football | yes | https://v3.football.api-sports.io | yes | yes | yes |
| sportmonks | yes | https://api.sportmonks.com/v3/football | yes | yes | yes |
| oddalerts | yes | https://data.oddalerts.com/api | yes | yes | yes |

## Part B — Fixture mapping

| fixture_id | competition | kickoff | home vs away | AF id | SM id | OA id | OA status |
|------------|-------------|---------|--------------|-------|-------|-------|-----------|
| 1564789 | world_cup_2026 | 2026-06-30T17:00:00 | Ivory Coast vs Norway | 1564789 | 19606955 | — | ODDALERTS_MAPPING_MISSING |
| 1565177 | world_cup_2026 | 2026-06-30T21:00:00 | France vs Sweden | 1565177 | 19606956 | — | ODDALERTS_MAPPING_MISSING |
| 1567306 | world_cup_2026 | 2026-07-01T01:00:00 | Mexico vs Ecuador | 1567306 | 19606954 | — | ODDALERTS_MAPPING_MISSING |
| 1554361 | champions_league | 2026-07-07T16:00:00 | Ararat-Armenia vs Riga | 1554361 | 19719903 | — | ODDALERTS_MAPPING_MISSING |
| 1554366 | champions_league | 2026-07-07T16:00:00 | Kauno Å½algiris vs Drita | 1554366 | 19719901 | — | ODDALERTS_MAPPING_MISSING |
| 1554368 | champions_league | 2026-07-07T16:00:00 | Lincoln Red Imps FC vs Inter Club d'Escaldes | 1554368 | — | — | ODDALERTS_MAPPING_MISSING |
| 1554444 | europa_league | 2026-07-09T16:00:00 | Qarabag vs Vestri | 1554444 | — | — | ODDALERTS_MAPPING_MISSING |
| 1554442 | europa_league | 2026-07-09T17:00:00 | Dynamo Kyiv vs Universitatea Cluj | 1554442 | 19719403 | — | ODDALERTS_MAPPING_MISSING |
| 1554410 | conference_league | 2026-07-07T17:15:00 | UNA Strassen vs La Fiorita | 1554410 | 19719435 | — | ODDALERTS_MAPPING_MISSING |
| 1554389 | conference_league | 2026-07-07T18:00:00 | AF Elbasani vs Bate Borisov | 1554389 | — | — | ODDALERTS_MAPPING_MISSING |

## Part E — Provider truth table

| Fixture | Provider | Mapped? | 1X2 | O/U 2.5 | BTTS | Correct Score | Raw odds? | Parser OK? | Store OK? | Final blocker |
|---------|----------|---------|-----|---------|------|---------------|-----------|------------|-----------|---------------|
| Ivory Coast vs Norway | api_football | yes | yes | no | yes | yes | yes | yes | yes | OK |
| Ivory Coast vs Norway | sportmonks | yes | yes | yes | yes | yes | yes | yes | yes | OK |
| Ivory Coast vs Norway | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| France vs Sweden | api_football | yes | yes | no | yes | yes | yes | yes | yes | OK |
| France vs Sweden | sportmonks | yes | yes | yes | yes | yes | yes | yes | yes | OK |
| France vs Sweden | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Mexico vs Ecuador | api_football | yes | yes | no | yes | yes | yes | yes | yes | OK |
| Mexico vs Ecuador | sportmonks | yes | yes | yes | yes | yes | yes | yes | yes | OK |
| Mexico vs Ecuador | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Ararat-Armenia vs Riga | api_football | yes | no | no | no | no | no | no | no | PROVIDER_EMPTY |
| Ararat-Armenia vs Riga | sportmonks | yes | yes | no | no | no | yes | yes | yes | OK |
| Ararat-Armenia vs Riga | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Kauno Å½algiris vs Drita | api_football | yes | no | no | no | no | no | no | no | PROVIDER_EMPTY |
| Kauno Å½algiris vs Drita | sportmonks | yes | yes | no | no | no | yes | yes | yes | OK |
| Kauno Å½algiris vs Drita | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Lincoln Red Imps FC vs Inter Club d'Escaldes | api_football | yes | no | no | no | no | no | no | no | PROVIDER_EMPTY |
| Lincoln Red Imps FC vs Inter Club d'Escaldes | sportmonks | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Lincoln Red Imps FC vs Inter Club d'Escaldes | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Qarabag vs Vestri | api_football | yes | no | no | no | no | no | no | no | PROVIDER_EMPTY |
| Qarabag vs Vestri | sportmonks | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Qarabag vs Vestri | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| Dynamo Kyiv vs Universitatea Cluj | api_football | yes | no | no | no | no | no | no | no | PROVIDER_EMPTY |
| Dynamo Kyiv vs Universitatea Cluj | sportmonks | yes | yes | no | no | no | yes | yes | yes | OK |
| Dynamo Kyiv vs Universitatea Cluj | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| UNA Strassen vs La Fiorita | api_football | yes | no | no | no | no | no | no | no | PROVIDER_EMPTY |
| UNA Strassen vs La Fiorita | sportmonks | yes | no | no | no | no | no | no | yes | PROVIDER_EMPTY |
| UNA Strassen vs La Fiorita | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| AF Elbasani vs Bate Borisov | api_football | yes | no | no | no | no | no | no | no | PROVIDER_EMPTY |
| AF Elbasani vs Bate Borisov | sportmonks | no | no | no | no | no | no | no | no | MAPPING_MISSING |
| AF Elbasani vs Bate Borisov | oddalerts | no | no | no | no | no | no | no | no | MAPPING_MISSING |

## Part H — Answers

1. **Does API-Football return odds for the sample fixtures?** Yes (partial or full on most fixtures)
2. **Does Sportmonks return odds for the sample fixtures?** Yes (where mapped)
3. **Does OddAlerts return odds for the sample fixtures?** No / mapping missing or empty
4. **Which provider has 1X2?** api_football, sportmonks
5. **Which provider has O/U 2.5?** sportmonks
6. **Which provider has BTTS?** api_football, sportmonks
7. **Which provider has Correct Score?** api_football, sportmonks
8. **Root cause:** See truth table blockers — distinguishes PROVIDER_EMPTY vs MAPPING_MISSING vs PARSER_GAP vs STORAGE_GAP.
9. **Next fix:** `PROVIDERS_EMPTY_WAIT_CLOSER_TO_KICKOFF`

## Artifacts

- `artifacts/provider_truth_audit_summary.json`
- `artifacts/provider_truth_audit_fixture_table.json`
- `logs/provider_truth_audit_calls_20260630.jsonl`
- Raw payloads: `artifacts\provider_truth_audit_raw/`

## Validation — unchanged systems

- `predictions`: unchanged
- `worldcup_stored_predictions`: unchanged
- `ecse_live_snapshots`: unchanged
- `odds_snapshots`: unchanged
- `billing_subscriptions`: unchanged

**Quota used:** {"api_football": 10, "sportmonks": 7, "oddalerts": 1}

## Final recommendation: `PROVIDERS_EMPTY_WAIT_CLOSER_TO_KICKOFF`