# Sportmonks xG & Pressure Access Probe Report

**Date:** 2026-06-23  
**Mode:** Live API probe (read-only)  
**Quota used:** 14 API calls (+ 2 fixture-discovery calls during probe setup)  
**Artifact:** `artifacts/sportmonks_xg_pressure_access_probe.json`  
**Script:** `scripts/sportmonks_xg_pressure_access_probe.py`

**No prediction logic, EGIE, or production changes were made.**

---

## Executive Summary

The current `.env` Sportmonks token **is valid** and returns rich fixture data — including **xG Match**, **Pressure Index**, **Odds**, and **Predictions** — on an in-plan Champions League fixture.

**The plan does NOT globally lack xG.** Prior “xG blocked” conclusions from WC-only tests were misleading: this key is subscribed to **“Euro Club Tournaments” (All-in)**, which covers UEFA club competitions but **not** World Cup (league 732) or Premier League (league 8).

| Finding | Verdict |
|---------|---------|
| API key works | Yes |
| xG Match (`xGFixture` include) | **Yes** on CL fixture |
| Pressure Index (`pressure` include) | **Yes** on CL fixture |
| WC fixture (stored SQLite id) | **Out of subscription scope** (not 403) |
| PL fixture | **Not tested** — no mapped `sportmonks_fixture_id` in SQLite |
| Global premium 403 on xG | **Not observed** on in-plan fixture |

---

## 1. Token Source

| Item | Value |
|------|-------|
| Source | `.env` via `get_settings()` |
| Env vars checked | `SPORTMONKS_API_TOKEN`, `SPORTMONKS_API_KEY` |
| Token configured | Yes |
| Base URL | `https://api.sportmonks.com/v3/football` |

Token value is **not** logged in this report.

---

## 2. Subscription (from live API response)

```json
{
  "plan": "Euro Club Tournaments",
  "sport": "Football",
  "category": "All-in"
}
```

**Implication:** League entitlements are **UEFA club tournaments** (Champions League, Europa League, etc.). Domestic leagues (PL `8`, Bundesliga `82`, La Liga `564`) and World Cup (`732`) return:

> `No result(s) found matching your request. Either the query did not return any results or you don't have access to it via your current subscription.`

This is **HTTP 200 with an empty/missing `data` object**, not HTTP 403.

---

## 3. Fixtures Tested

| Label | Sportmonks fixture_id | League | Source | Match |
|-------|----------------------|--------|--------|-------|
| `world_cup_732_stored` | 19609127 | 732 | SQLite enrichment | Stored WC mapping |
| `champions_league_2` | 168925 | 2 | Live `GET /fixtures?filters=fixtureLeagues:2` | Chelsea vs Paris Saint Germain |
| Premier League | — | 8 | — | **Skipped** — 0 rows in `sportmonks_fixture_enrichment` for league 8 |

---

## 4. Component Results

### 4a. World Cup — fixture `19609127` (league 732)

All components returned **HTTP 200** but **no `data` object** and **no target fields**.

| Component | Endpoint | Include | Status | Target data | Likely cause |
|-----------|----------|---------|--------|-------------|--------------|
| xG Match | `/fixtures/19609127` | `xGFixture.type;lineups.xGLineup.type;…` | 200 | No | League not in subscription |
| Pressure Index | `/fixtures/19609127` | `participants;pressure` | 200 | No | League not in subscription |
| Match Centre | `/fixtures/19609127` | `events;statistics;lineups;…` | 200 | No | League not in subscription |
| Lineup | `/fixtures/19609127` | `lineups.player;formations;…` | 200 | No | League not in subscription |
| Team Recent Form | `/fixtures/19609127` | `participants;form` | 200 | No | League not in subscription |
| Odds | `/fixtures/19609127` | `odds.bookmaker;odds.market` | 200 | No | League not in subscription |
| Prediction Model | `/fixtures/19609127` | `predictions.type` | 200 | No | League not in subscription |

**Note:** This is **not** proof that xG is plan-blocked. It proves the **fixture/league is outside the current subscription scope** for this key.

---

### 4b. Champions League — fixture `168925` (league 2)

All components returned **HTTP 200** with a **`data` object** and expected keys.

| Component | Endpoint | Include | Status | Target data | Response keys (sample) |
|-----------|----------|---------|--------|-------------|------------------------|
| **xG Match** | `/fixtures/168925` | `xGFixture.type;lineups.xGLineup.type;…` | 200 | **Yes** | `xGFixture`, `lineups`, `scores`, `participants` |
| **Pressure Index** | `/fixtures/168925` | `participants;pressure` | 200 | **Yes** | `pressure`, `participants` |
| **Match Centre** | `/fixtures/168925` | `events;statistics;lineups;scores;…` | 200 | **Yes** | `events`, `statistics`, `lineups`, `scores` |
| **Lineup** | `/fixtures/168925` | `lineups.player;formations;…` | 200 | **Yes** | `lineups`, `formations` |
| **Team Recent Form** | `/fixtures/168925` | `participants;form` | 200 | **Yes** | `form`, `participants` |
| **Odds** | `/fixtures/168925` | `odds.bookmaker;odds.market` | 200 | **Yes** | `odds` |
| **Prediction Model** | `/fixtures/168925` | `predictions.type` | 200 | **Yes** | `predictions` |

---

## 5. Include / Endpoint Notes

| Component | Correct include | Invalid / rejected |
|-----------|-----------------|-------------------|
| xG Match | `xGFixture` (nested: `xGFixture.type`, `lineups.xGLineup.type`) | — |
| Pressure Index | `pressure` | `pressureIndex` → **404** (“include does not exist”) |
| Odds | `odds.bookmaker;odds.market` | — |
| Predictions | `predictions.type` | — |

Pressure in EGIE is currently derived from **statistics/xG proxies** (`parse_sportmonks_pressure`). The live API supports a dedicated **`pressure` include** on in-plan fixtures.

---

## 6. Root-Cause Matrix (why EGIE shows 0% xG/pressure)

| Layer | Status for PL EGIE backtest |
|-------|----------------------------|
| API key valid | Yes |
| xG technically available on plan | Yes (CL proven) |
| PL league in subscription | **No** (`fixtureLeagues:8` → 0 results) |
| WC league in subscription | **No** (stored ids unreachable) |
| PL Sportmonks fixture mapping | **Missing** (0 SQLite rows) |
| EGIE ingest | Not populated for PL |

**Conclusion:** EGIE’s 0% xG/pressure is primarily **subscription scope + missing PL mapping**, not a broken xG add-on on a capable key.

---

## 7. Recommendations (informational only — no deploy)

1. **Upgrade or add plan** for Premier League (league 8) and/or World Cup (732) if those competitions are required for EGIE PL backtest.
2. **Use in-plan fixtures** (UEFA CL/EL) for Sportmonks integration testing until PL is entitled.
3. **Map PL fixtures** to Sportmonks ids before any PL backfill quota spend.
4. **Update pressure ingest** to use `pressure` include (not `pressureIndex`).
5. **Retire WC-only probe assumptions** — re-test premium includes on an entitled league before marking xG/odds as plan-blocked.

---

## 8. Re-run Command

```bash
python scripts/sportmonks_xg_pressure_access_probe.py
```

Output: `artifacts/sportmonks_xg_pressure_access_probe.json`

---

**STOP — no production deploy, no EGIE changes.**
