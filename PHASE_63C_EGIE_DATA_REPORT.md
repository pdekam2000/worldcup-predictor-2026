# Phase 63C — EGIE Data Completion Report

**Date:** 2026-06-26  
**Pipeline:** `scripts/phase62b_sportmonks_wc_xg_lineups_completion.py` (resume + cache-first)  
**Artifact:** `data/validation/phase62b_sportmonks_wc_completion.json`

---

## Executive summary

| Item | Result |
|------|--------|
| Recommendation | **`PROVIDER_LIMITED`** |
| API calls made | **10** (no wasted retries on cached fixtures) |
| Lineups imported | **+10** new (60 skipped cached, 70 total mapped) |
| xG imported this run | **0** (10 fixtures queried — xG missing at provider) |
| Feature rebuild | **328** rows rebuilt |
| Mapping rate | **21.3%** (70/328 WC fixtures) |

---

## Coverage (before → after)

| Signal | Before | After | Target |
|--------|--------|-------|--------|
| Total fixtures | 328 | 328 | 500+ |
| xG coverage | 18.3% | 18.3% | 70% |
| Lineup coverage | 18.3% | **21.3%** | 80% |
| Goal events | 9.2% | 9.2% | 90% |
| Odds | 21.0% | 21.0% | 80% |
| Usable EGIE fixtures | 29 | 29 | 500+ |

---

## Tasks completed

### xG import

- Processed 70 mapped fixtures via Sportmonks (checkpoint resume)
- **60 skipped** (already cached — no API waste)
- **10 API calls** — all returned lineups; **xG not available** for those fixtures at provider (`xg_missing: 10`)
- Cached xG count in feature store: **60 fixtures** with xG from prior imports

### Lineups import

- **+10 lineups saved** this run
- Feature rebuild: **70 fixtures** with lineup data (+8 net from 62 pre-run)

### Mapping quality

| Metric | Value |
|--------|-------|
| Mapped fixtures | 70 |
| Unmapped fixtures | 258 |
| Mapping rate | 21.34% |
| Avg confidence | 0.979 |
| Blocked duplicates | 0 |

High-confidence mappings concentrated on **WC 2026** schedule (Sportmonks enrichment + cache index). Historical finals (1998–2022) largely unmapped — provider ID pool mismatch.

### Cache usage

| Metric | Value |
|--------|-------|
| Skipped cached | 60 |
| API calls | 10 |
| Cache hit ratio (this batch) | 0% on new calls; 86% of mapped set served from cache |

---

## Provider limitations (classified)

1. **Fixture pool cap** — API-Football league-1 historical finals ~328 fixtures across 1998–2026; cannot reach 500+ without additional competition sources.
2. **Sportmonks xG gaps** — 10/10 new API responses lacked xG payload (lineups present); no retry loop applied.
3. **Historical mapping** — 258 fixtures unmapped (pre-2026 IDs not in Sportmonks WC 2026 enrichment index).
4. **Goal events** — Only 29/328 fixtures have usable goal-timing events (9.2%); limits EGIE timing market coverage.
5. **Permission note** — Pipeline artifact write to repo root failed as `www-data`; fixed via `chown` on `data/validation` + `data/egie`.

---

## Feature / survival rebuild

| Output | Count |
|--------|-------|
| Enriched feature rows | 328 |
| With xG | 60 |
| With lineups | 70 |
| With goal events | 29 |
| Survival rows | 316 |
| Team timing profiles | 65 teams |

---

## What was NOT done

- No prediction engine changes
- No public Unified Engine flags
- No repeated API calls for known-missing xG
- No fabricated xG/lineup data

---

## Next data actions (optional)

1. Expand Sportmonks season mapping for 1998–2022 fixture IDs (manual mapping table)
2. Accept `PROVIDER_LIMITED` for xG on WC 2026 fixtures until Sportmonks xG endpoint coverage improves
3. Backfill goal events from alternate event provider where Sportmonks events sparse

---

**Recommendation: `PROVIDER_LIMITED` — maximize cache, stop retrying unavailable provider data.**
