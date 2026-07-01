# EURO-C3 — UEFA Odds Watch + ECSE Readiness Monitor

**Phase:** EURO-C3  
**Mode:** Owner/internal odds watch only · No ECSE generation · No public changes  
**Generated:** 2026-06-30 UTC  

---

## Executive summary

EURO-C3 deployed a cache-first, API-capped UEFA odds readiness monitor that re-checks API-Football, OddAlerts (if configured), and Sportmonks (accepted crosswalk only) for all canonical `owner_euro_b` UEFA fixtures. The watch imports only provider-backed odds, computes per-fixture ECSE readiness, and writes owner-only artifacts for daily recheck scheduling.

**121** fixtures scanned across Champions League, Europa League, and Conference League. **0** fixtures are ECSE-ready (`READY_FULL` or `READY_PARTIAL`). **5** fixtures have partial **1X2-only** odds. **116** fixtures returned empty provider odds after live checks.

**Final recommendation:** `NEED_SPORTMONKS_MARKET_FIX`

Do not run ECSE yet — O/U 2.5 (and BTTS for full readiness) remain missing on all fixtures.

---

## Fixtures scanned

| Competition | Fixtures | 1X2 | O/U 2.5 | BTTS | READY_FULL | READY_PARTIAL |
|-------------|---------:|----:|--------:|-----:|-----------:|--------------:|
| champions_league | 42 | 2 | 0 | 0 | 0 | 0 |
| europa_league | 58 | 3 | 0 | 0 | 0 | 0 |
| conference_league | 21 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **121** | **5** | **0** | **0** | **0** | **0** |

All 121 targets have **WDE** (`owner_euro_b`) predictions. **0** ECSE snapshots exist for UEFA.

---

## Odds before / after

| Metric | Before EURO-C3 (post EURO-C2) | After EURO-C3 live watch |
|--------|------------------------------:|-------------------------:|
| Fixtures with any odds snapshot | 4 | 5 (1X2 partial) |
| Newly imported this run | — | 5 |
| ECSE-ready (`READY_FULL` / `READY_PARTIAL`) | 0 | 0 |
| Provider-empty after live check | — | 116 |

### Readiness status breakdown (after live watch)

| Status | Count |
|--------|------:|
| `ODDS_PARTIAL_1X2_ONLY` | 5 |
| `PROVIDER_EMPTY` | 116 |
| `READY_FULL` | 0 |
| `READY_PARTIAL` | 0 |
| `ODDS_MISSING` | 0 |
| `MAPPING_MISSING` | 0 |
| `PROVIDER_ERROR` | 0 |

### Newly ECSE-ready fixtures

None. No fixture gained `READY_FULL` or `READY_PARTIAL` status during this run.

### Partial-odds fixtures (1X2 only)

Examples with Sportmonks/API-Football crosswalk accepted:

| fixture_id | Competition | Match | Missing markets |
|-----------:|-------------|-------|-----------------|
| 1554373 | champions_league | Vardar Skopje vs KuPS | O/U 2.5, BTTS |
| 1554366 | champions_league | Kauno Žalgiris vs Drita | O/U 2.5, BTTS |
| 1554441 | europa_league | CSKA Sofia vs Derry City | O/U 2.5, BTTS |
| 1554442 | europa_league | Dynamo Kyiv vs Universitatea Cluj | O/U 2.5, BTTS |
| 1554446 | europa_league | Vojvodina vs Ferencvarosi TC | O/U 2.5, BTTS |

---

## Provider call usage

| Provider | Calls used | Cap |
|----------|----------:|----:|
| API-Football | 13 | 100 |
| Sportmonks | 100 | 100 |
| OddAlerts | 0 | 100 |

Provider fallback order applied per fixture: **local/cache → API-Football → OddAlerts → Sportmonks (accepted crosswalk)**. Sportmonks was consulted when API-Football returned empty and crosswalk confidence ≥ 0.90.

**Logs:** `logs/euro_c3_odds_watch_20260630_134529.jsonl`

---

## Missing markets summary

| Required market | Fixtures with market | Fixtures missing |
|-----------------|--------------------:|-----------------:|
| 1X2 | 5 | 116 |
| Over/Under 2.5 | 0 | 121 |
| BTTS | 0 | 121 |

Preferred markets (O/U 1.5, O/U 3.5, Correct Score, Double Chance): **0** coverage across all fixtures.

---

## Provider empty summary

- **116 / 121** fixtures (95.9%) returned valid but **empty** odds from live provider checks after cache miss.
- Pattern matches EURO-C (API-Football) and EURO-C2 (Sportmonks): early UEFA qualifying windows have fixtures listed but bookmakers not yet publishing full markets.
- No fake or placeholder odds imported (`is_fake_odds_payload` guard enforced).

---

## Validation result

**PASSED** — `scripts/validate_euro_c3_odds_watch.py`

| Check | Result |
|-------|--------|
| Owner-only artifacts only | OK |
| No ECSE snapshots generated | OK (0 UEFA ECSE) |
| WDE predictions unchanged | OK (121 `owner_euro_b`) |
| API call caps respected | OK |
| No fake odds / no NaN·inf | OK |
| Accepted crosswalk only (≥ 0.90) | OK |
| Readiness statuses valid | OK |
| Owner report readiness integration | OK |
| EGIE / billing unchanged | OK |

**Artifact:** `artifacts/euro_c3_odds_watch_validation.json`

---

## Owner report integration (Part E)

`scripts/owner_today_10_exact_scores.py` now shows for UEFA competitions:

- WDE prediction available
- ECSE readiness status
- Odds markets available
- Missing odds reason
- Next recheck priority

ECSE exact-score block remains hidden when no ECSE snapshot exists.

---

## Recommended schedule (Part F — manual only)

**Morning (daily):**

```bash
python scripts/watch_uefa_odds_readiness.py \
  --competitions champions_league europa_league conference_league \
  --days-ahead 30 \
  --max-api-football-calls 100 \
  --max-sportmonks-calls 100 \
  --max-oddalerts-calls 100
```

**Closer to kickoff:** Re-run every **2–4 hours** for fixtures within **48h** (HIGH recheck priority when odds missing).

**Dry-run preview:**

```bash
python scripts/watch_uefa_odds_readiness.py \
  --competitions champions_league europa_league conference_league \
  --days-ahead 30 \
  --dry-run
```

No scheduler installed automatically.

---

## Next recheck window

| Priority | Window | Action |
|----------|--------|--------|
| HIGH | Kickoff &lt; 48h and odds missing | Run watch every 2–4h |
| MEDIUM | Kickoff 2–7 days | Daily morning watch |
| LOW | Kickoff &gt; 7 days | Daily watch sufficient |

Current earliest UEFA qualifying kickoffs are ~7 days out (2026-07-07) — **LOW/MEDIUM** priority until within 48h of first fixtures.

---

## Deliverables

| Part | File |
|------|------|
| A — Watch script | `scripts/watch_uefa_odds_readiness.py` |
| A — Core module | `worldcup_predictor/owner/euro_c3_odds_watch.py` |
| B — Readiness scoring | `compute_ecse_readiness_status`, `next_recheck_priority` in core module |
| D — Summary artifact | `artifacts/euro_c3_uefa_odds_watch_summary.json` |
| D — Readiness JSONL | `artifacts/euro_c3_uefa_ecse_readiness.jsonl` |
| E — Owner report | `scripts/owner_today_10_exact_scores.py` |
| G — Validation | `scripts/validate_euro_c3_odds_watch.py` |
| H — This report | `EURO_C3_UEFA_ODDS_WATCH_REPORT.md` |

---

## Final recommendation

### `NEED_SPORTMONKS_MARKET_FIX`

**Rationale:** Sportmonks (and API-Football) return **1X2-only** markets on a small subset of fixtures. ECSE requires **1X2 + O/U 2.5** minimum (BTTS for `READY_FULL`). Providers are publishing match-winner lines but not totals/BTTS yet for early qualifying.

**Action:** Continue daily odds watch. Re-evaluate when O/U 2.5 appears on any fixture (`READY_PARTIAL` threshold). Do **not** run ECSE until at least one fixture reaches `READY_PARTIAL` or `READY_FULL`.

**Alternate triggers for future runs:**

| Signal | Recommendation |
|--------|----------------|
| Any `READY_FULL` / `READY_PARTIAL` | `UEFA_ECSE_READY_FIXTURES_FOUND` |
| Sustained empty providers | `PROVIDERS_STILL_EMPTY` |
| OddAlerts mapping gap | `NEED_ODDALERTS_MAPPING` |
| Ongoing partial 1X2 | `NEED_SPORTMONKS_MARKET_FIX` |
| No ready fixtures, watch active | `CONTINUE_ODDS_WATCH` |
| Never run ECSE without markets | `DO_NOT_RUN_ECSE_YET` |

---

*Owner/internal phase complete. No ECSE generation. No WDE/ECSE/EGIE/billing/public changes.*
