# BIG5 Season Start Fixture Readiness

**Generated:** 2026-07-10  
**Anchor:** 2026-07-10  
**Source:** API-Football provider evidence (friendlies excluded)

| League | First fixture | 30d prematch | 45d prematch | 60d prematch | Local DB rows | API-vs-DB gap |
|--------|---------------|-------------:|-------------:|-------------:|--------------:|---------------|
| Premier League | 2026-08-21 | 0 | 9 | 30 | 385 | Tier A historical DB populated; upcoming from API |
| Bundesliga | 2026-08-28 | 0 | 0 | 18 | 1232 | Tier A historical DB populated; upcoming from API |
| Serie A | 2026-08-22 | 0 | 8 | 30 | 0 | API-only until sync ingests season fixtures |
| La Liga | 2026-08-16 | 0 | 20 | 40 | 0 | API-only until sync ingests season fixtures |
| Ligue 1 | 2026-08-22 | 0 | 9 | 27 | 0 | API-only until sync ingests season fixtures |

## Competition identity

All five leagues resolve to canonical keys (`premier_league`, `bundesliga`, `serie_a`, `la_liga`, `ligue_1`) with correct provider league IDs 39, 78, 135, 140, 61.

## Timezone normalization

Kickoffs stored and listed in UTC with `Europe/Vienna` display path via GPT Actions `timezone` parameter.

## Notes

- No fixtures in next 30 days (pre-season window as of 2026-07-10).
- Season openings cluster **2026-08-16** (La Liga) through **2026-08-29** (PL matchday).
- Friendlies excluded by competition normalization and broad-listing filters.

**Status:** FIXTURE_READINESS_PASS — authentic league fixtures scheduled; no fabricated preseason data.
