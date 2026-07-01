# EURO-C — UEFA Odds Import for ECSE Enablement

**Phase:** EURO-C  
**Mode:** Odds import only · Owner/internal · No ECSE generation  
**Generated:** 2026-06-30 UTC  

---

## Executive summary

EURO-C implemented the full odds scan → import → validate pipeline for 121 canonical UEFA fixtures previously wired in EURO-B (`generated_by = owner_euro_b`). The import infrastructure is operational (cache-first, API-capped, normalized snapshots, ECSE readiness flags), but **API-Football returned empty odds** for all fixtures queried in this run. No fake or placeholder odds were stored.

**Final recommendation:** `PROVIDER_NO_ODDS_AVAILABLE`

EURO-D ECSE generation **must not proceed** until provider odds appear for these fixtures (or a high-confidence Sportmonks crosswalk odds path is added).

---

## Odds provider used

| Priority | Provider | Result |
|----------|----------|--------|
| 1 | API-Football (`GET /odds?fixture=`) | Primary — 100 live calls + cache re-checks |
| 2 | Sportmonks odds | Not attempted (no high-confidence crosswalk-only fixtures in target set) |
| 3 | Existing cache (`api_response_cache`, disk `.cache/api_football`, `odds_snapshots`) | 0 hits for target fixture IDs |

API-Football is configured and reachable. Responses were valid but **empty arrays** (`response_count = 0`) for early UEFA qualifying fixtures (CL Q1, EL Q1, UECL Q1).

---

## Fixtures scanned

| Metric | Count |
|--------|------:|
| Target fixtures (owner_euro_b WDE, canonical API-Football) | 121 |
| Champions League | 36 |
| Europa League | 16 |
| Conference League | 69 |
| Sportmonks-only excluded | 0 |
| Duplicate-risk excluded | 0 |

---

## Odds coverage before / after

| Metric | Before | After |
|--------|-------:|------:|
| Fixtures with parseable odds (1X2 + O/U 2.5) | 0 | 0 |
| Odds snapshots imported | — | 0 |
| ECSE-ready fixtures | 0 | 0 |

---

## Market coverage by competition (after import)

| Competition | 1X2 | O/U 2.5 | BTTS | O/U 1.5 | O/U 3.5 | Correct Score | ECSE-ready |
|-------------|----:|--------:|-----:|--------:|--------:|--------------:|-----------:|
| champions_league | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| europa_league | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| conference_league | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

---

## API usage

| Metric | Value |
|--------|------:|
| `--max-api-calls` cap | 100 |
| Live API calls used | 100 |
| Cache hits (pre-import) | 0 |
| Fixtures skipped (cap reached) | 21 |
| Provider empty responses | 100 |

Call log: `logs/euro_c_odds_import_20260630_130206.jsonl`

---

## Skipped fixtures / reasons

| Reason | Count |
|--------|------:|
| `provider_no_odds_available` (empty API response) | 100 |
| `max_api_calls_reached` | 21 |

No fixtures were skipped for duplicate risk, fake odds, or Sportmonks-only mapping gaps.

---

## Deliverables created

| Part | Artifact |
|------|----------|
| A | `scripts/scan_uefa_odds_availability.py` → `artifacts/euro_c_odds_availability_scan.json` |
| B | `scripts/import_uefa_odds.py` |
| C | Normalization in `worldcup_predictor/owner/euro_c_odds_import.py` |
| D | ECSE readiness via `assess_ecse_readiness()` |
| E | `logs/euro_c_odds_import_*.jsonl` |
| F | `scripts/validate_euro_c_odds_import.py` → `artifacts/euro_c_odds_import_validation.json` |
| G | `artifacts/euro_c_odds_import_summary.json` |
| H | This report |

Core module: `worldcup_predictor/owner/euro_c_odds_import.py`

---

## Validation results

**Status: PASSED**

- 121 canonical UEFA API-Football fixtures selected (owner_euro_b WDE present)
- No Sportmonks-only low-confidence imports
- API call cap respected (100/100)
- No fake / placeholder odds stored
- No duplicate odds snapshots created
- Implied probability validation N/A (no imports)
- ECSE readiness computed for all fixtures
- WDE unchanged (121 `owner_euro_b` rows)
- ECSE snapshots unchanged (0 UEFA ECSE)
- EGIE / billing / public output unchanged

---

## ECSE readiness criteria (not generated)

A fixture is **ECSE-ready** when:

1. Parseable **1X2** implied probabilities
2. Parseable **Over/Under 2.5** implied probabilities
3. **Lambda inputs** derivable via `build_odds_feature_row` + `extract_lambdas`

BTTS is tracked but optional for ECSE lambda extraction (partial readiness flagged when 1X2 or O/U 2.5 missing).

**Current ECSE-ready count: 0 / 121**

---

## Can EURO-D ECSE generation proceed?

**No.** ECSE was explicitly not generated in EURO-C. All 121 EURO-B ECSE attempts would still skip on `missing_odds`.

### Recommended next steps

1. **Re-run import** closer to kickoff when API-Football publishes qualifying-round odds:
   ```bash
   python scripts/import_uefa_odds.py --competitions champions_league europa_league conference_league --days-ahead 30 --max-api-calls 150
   ```
2. If API-Football continues to omit early qualifying odds, evaluate **Sportmonks odds crosswalk** for high-confidence fixtures (`NEED_SPORTMONKS_ODDS_CROSSWALK`).
3. After `ecse_ready_count > 0`, proceed to **EURO-D** owner ECSE snapshot generation only.

---

## Final recommendation

```
PROVIDER_NO_ODDS_AVAILABLE
```

The odds import pipeline is ready and validated. The blocker is upstream provider coverage, not schema or wiring.
