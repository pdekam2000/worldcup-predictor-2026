# EURO-C2 — Sportmonks UEFA Odds Crosswalk for ECSE

**Phase:** EURO-C2  
**Mode:** Owner/internal crosswalk + odds import only · No ECSE generation  
**Generated:** 2026-06-30 UTC  

---

## Executive summary

EURO-C2 built a high-confidence Sportmonks-to-API-Football fixture crosswalk for UEFA qualifying fixtures, scanned/imported Sportmonks odds against canonical `owner_euro_b` fixture IDs, and validated the pipeline. **105 / 121** fixtures crosswalked successfully. **4** fixtures received provider-backed Sportmonks odds snapshots (mostly **1X2 only**). **0** fixtures are ECSE-ready.

**Final recommendation:** `PARTIAL_SPORTMONKS_ODDS_READY`

Do not run ECSE yet — core markets (O/U 2.5 + lambda inputs) remain missing for all fixtures.

---

## Crosswalk coverage

| Metric | Count |
|--------|------:|
| API-Football canonical targets (`owner_euro_b`) | 121 |
| Sportmonks feed rows (30-day window) | 224 |
| **Accepted crosswalk** (confidence ≥ 0.90) | **105** |
| Rejected / no match | 16 |
| Ambiguous | 0 |

### Matching logic

1. Same `competition_key`
2. Kickoff within ±3h **or** same UTC date when Sportmonks stores midnight date-only kickoffs
3. Normalized home/away team similarity (EURO-A2 helpers)
4. Combined confidence ≥ 0.90 required; ambiguous top-2 ties rejected

**Artifact:** `artifacts/euro_c2_sportmonks_crosswalk.json`

---

## Sportmonks odds coverage

| Metric | Before EURO-C2 | After import |
|--------|----------------:|-------------:|
| Fixtures with any parseable odds | 0 | 4 |
| Imported `odds_snapshots` (Sportmonks source) | 0 | 4 |
| ECSE-ready | 0 | 0 |

### Markets on imported fixtures (4)

| Market | Coverage |
|--------|----------|
| 1X2 / Match Winner | 4 |
| Over/Under 2.5 | 0 |
| BTTS | 0 |
| O/U 1.5 / 3.5 | 0 |
| Correct Score | 0 |
| Double Chance | 0 |

Imported fixtures (API-Football IDs): `1554373`, `1554441`, `1554442`, and one additional Europa/Conference crosswalk match with cached Sportmonks payload.

---

## API usage

| Metric | Value |
|--------|------:|
| Sportmonks live calls (import run) | 100 / 100 cap |
| Cache hits | 4 |
| Empty live odds responses | ~96 |

**Logs:** `logs/euro_c2_sportmonks_odds_import_20260630_131941.jsonl`

Most early UEFA qualifying fixtures return **valid but empty** `odds[]` from Sportmonks live API — same pattern as API-Football in EURO-C.

---

## Deliverables

| Part | File |
|------|------|
| Core module | `worldcup_predictor/owner/euro_c2_sportmonks_odds.py` |
| A — Crosswalk | `scripts/build_uefa_sportmonks_crosswalk.py` |
| B — Odds scan | `scripts/scan_sportmonks_uefa_odds.py` |
| C — Import | `scripts/import_sportmonks_uefa_odds.py` |
| D — ECSE readiness | `artifacts/euro_c2_ecse_readiness_after_sportmonks.json` |
| E — Validation | `scripts/validate_euro_c2_sportmonks_odds_crosswalk.py` |
| Artifacts | `euro_c2_sportmonks_odds_availability.json`, `euro_c2_sportmonks_odds_import_summary.json`, `euro_c2_sportmonks_odds_validation.json` |

---

## Validation results

**Status: PASSED**

- 105 high-confidence crosswalk rows; 0 ambiguous accepted
- 4 Sportmonks odds snapshots stored on canonical API-Football `fixture_id`
- Crosswalk confidence ≥ 0.90 on all imports
- No fake/placeholder odds
- Valid implied probabilities (no NaN/inf)
- WDE `owner_euro_b`: 121 unchanged
- ECSE snapshots: 0 unchanged
- ECSE baseline / EGIE / billing / public output unchanged

---

## Remaining blockers

1. **Provider odds gap** — ~96% of crosswalked fixtures have no Sportmonks prematch odds yet (qualifying round timing).
2. **Incomplete markets** — Even where odds exist, O/U 2.5 (required for ECSE lambdas) is missing.
3. **16 fixtures** need team-mapping review (`NEED_TEAM_MAPPING_FIX` subset) — no Sportmonks feed candidate within confidence window.

---

## Can EURO-D ECSE generation proceed?

**No.** ECSE-ready count is **0 / 121**.

### Suggested next steps

1. Re-run import closer to kickoff when bookmakers publish full markets:
   ```bash
   python scripts/import_sportmonks_uefa_odds.py --competitions champions_league europa_league conference_league --days-ahead 30 --max-api-calls 150
   ```
2. Review 16 `no_match` fixtures in `euro_c2_sportmonks_crosswalk.json` for manual team alias additions.
3. Proceed to EURO-D only when `ecse_ready_count > 0` in `euro_c2_ecse_readiness_after_sportmonks.json`.

---

## Final recommendation

```
PARTIAL_SPORTMONKS_ODDS_READY
```

Crosswalk wiring is production-safe; odds coverage is insufficient for ECSE.
