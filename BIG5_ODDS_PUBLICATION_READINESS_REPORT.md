# BIG5 Odds Publication Readiness Report

**Generated:** 2026-07-10  
**Onboarding status:** READY_WITH_ODDS_LIMITATION (Tier B leagues)

## Tier B watch — Serie A, La Liga, Ligue 1

| League | Prematch scheduled (60d) | API odds | DB odds | Bookmakers | Freshness | Odds-qualified |
|--------|-------------------------:|---------:|--------:|------------|-----------|----------------|
| Serie A | 30 | 0 | 0 | 0 | n/a | 0 |
| La Liga | 40 | 0 | 0 | 0 | n/a | 0 |
| Ligue 1 | 27 | 0 | 0 | 0 | n/a | 0 |

**Classification:** `PRESEASON_ODDS_NOT_YET_AVAILABLE` for all three — seasonal, not structural.

## Detection path (no forced polling)

1. Daily owner discovery and broad listing fetch fixtures via API-Football (cache-first).
2. Odds ingested on prediction path and Tier B `controlled_owner_odds_lookup` when automation runs.
3. Gates classify `ODDS_MISSING` until authentic bookmaker odds appear.
4. Listing still shows fixtures independently of odds (`listTodayMatches`).

## Expected transition

When bookmakers publish season markets (typically 1–14 days before opening matchdays), existing automation will:
- Populate DB odds on next discovery/prediction cycle
- Pass odds gates without policy change
- Enable prematch freeze for forward evaluation

**Status:** ODDS_PUBLICATION_PATH_READY — monitoring via existing cache/automation; no gate relaxation required.
