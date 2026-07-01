# EURO-A2 — UEFA Result Backfill Repair Report

**Phase:** EURO-A2 (data repair only)  
**Date:** 2026-06-30  
**Scope:** No WDE/ECSE predictions, no public UI, no prediction logic changes.

---

## Executive summary

EURO-A2 repaired UEFA historical `fixture_results` by adding deterministic provider matching (API-Football feed crosswalk, league+date team matching, ±3h window, fuzzy names ≥0.88, Sportmonks cached payloads), confidence gating (≥0.88), and legacy-row result mirroring when API-Football IDs differ from Sportmonks fixture IDs.

**Before EURO-A2 (post EURO-A):** 58 UEFA cup results, **220** finished fixtures still missing results.  
**After EURO-A2:** **284** `fixture_results` rows, **78** finished fixtures still missing results.

**Final recommendation:** `PARTIAL_BACKFILL_ACCEPTABLE`

---

## Root cause of remaining missing results (EURO-A)

1. **Legacy Sportmonks `fixture_id` values** stored in `fixtures` (e.g. `19135227`) — API-Football `fixtures?id=` returns no goals.
2. **Invalid `season` values** (Sportmonks season IDs like `23619`) broke early date+season API queries.
3. **Team-name normalization gaps** — accents, suffixes (`FK`, `FC`), and alternate spellings blocked exact matches.
4. **Dual fixture rows** — same match exists as Sportmonks and API-Football rows; results on API IDs did not clear Sportmonks missing scans until A2 legacy mirroring.

---

## Matching logic (EURO-A2)

Module: `worldcup_predictor/data_import/uefa_result_matching.py`

| Priority | Method | Min confidence |
|----------|--------|----------------|
| 1 | Raw payload cache (`artifacts/euro_a2/`, `euro_a/`) | 1.0 |
| 2 | `euro_fixture_feed` API-Football crosswalk (date + normalized teams) | 0.99 |
| 3 | Exact `provider_fixture_id` via API | 1.0 |
| 4 | League + date + exact normalized teams | 0.98 |
| 5 | League + ±3h window + exact/fuzzy teams | 0.95 / ≥0.88 |
| 6 | Full season scan filtered by date + teams | 0.98 |
| 7 | Sportmonks `euro_fixture_raw_payload` with scores (high-confidence feed row) | 0.94 |

**Team normalization:** lowercase, accent strip, punctuation removal, common suffix strip (`FC`, `FK`, `CF`, `SC`, `SK`, `AC`, `AS`, …).  
**Fuzzy:** `SequenceMatcher` ≥0.88 on both teams; ambiguous multi-candidate matches are **not** persisted.  
**Persistence tag:** `outcome_source = euro_a2|{provider}|{id}|{confidence}|{method}`

---

## Before / after counts

| Competition | Results before | Results after | Newly backfilled | Finished | Unresolved |
|-------------|----------------|---------------|------------------|----------|------------|
| champions_league | 24 | 116 | +92 | 148 | 32 |
| europa_league | 8 | 50 | +42 | 90 | 40 |
| conference_league | 26 | 118 | +92 | 124 | 6 |
| **Total** | **58** | **284** | **+226 rows** | **362** | **78** |

*Note: `fixture_results` row count includes mirrored results on legacy Sportmonks IDs and API-Football IDs for the same match.*

**Missing scan improvement:** 220 → **78** (−64%, 142 fixtures repaired).

**Finished-fixture coverage:** 284 / 362 = **78.5%** of finished UEFA cup fixtures now have `fixture_results`.

---

## Unresolved examples (sample)

Typical unresolved rows (from audit):

- **Champions League** — qualifying ties with alternate club names vs API-Football (`KÍ`, `Şamaxı FK`, `Rīgas FS`).
- **Europa League** — 2021–2022 early rounds with sparse API date coverage or team variants.
- **Conference League** — 6 rows including two-legged ties with reversed home/away on return leg (`Laçi` vs `FK Podgorica`).

---

## Skipped low-confidence

- Ambiguous multi-candidate matches within ±3h window: **not persisted**.
- Fuzzy score &lt; 0.88: **not persisted**.
- No provider goals in payload: logged as `unresolved_provider_match`.

---

## Artifacts

| Path | Purpose |
|------|---------|
| `artifacts/euro_a2_missing_uefa_results_audit.json` | Part A missing-result audit with candidates |
| `artifacts/euro_a2_result_backfill_repair_summary.json` | Per-competition repair summary |
| `artifacts/euro_a2/raw_payloads/{comp}/{id}.json` | Provider payload references |

---

## Validation

**Script:** `scripts/validate_euro_a2_result_backfill_repair.py`  
**Result:** **PASSED**

Verified: no fake/null-goal results, no duplicate `fixture_id` result groups, PL/Bundesliga samples intact, competition keys preserved, no `international` mislabels, `euro_a2` outcome tags present, confidence ≥0.88 on persisted rows, no WDE/ECSE output, baseline tables unchanged.

---

## Enough results for evaluation / backtest?

| Competition | Assessment |
|-------------|------------|
| conference_league | **Yes** — 95% finished coverage; suitable for limited backtest |
| champions_league | **Partial** — 78% coverage; early qualifying gaps remain |
| europa_league | **Partial** — 56% coverage; needs team mapping for older rounds |

Overall: **partial evaluation possible** for Conference League; CL/UEL historical learning still gap-heavy.

---

## Remaining blockers for EURO-B prediction wiring

1. **78 unresolved finished fixtures** — `NEED_TEAM_MAPPING_TABLE` or `NEED_PROVIDER_ID_MAPPING` for stubborn Sportmonks-only rows.
2. **Upcoming fixtures** (142 from EURO-A) are separate — result backfill does not block owner WDE/ECSE on upcoming canonical API-Football rows.
3. **Odds import** for upcoming UEFA fixtures still a separate phase.

---

## Files created / updated

| Path | Change |
|------|--------|
| `worldcup_predictor/data_import/uefa_result_matching.py` | **New** — normalization, feed index, confidence scoring |
| `worldcup_predictor/data_import/european_result_backfill.py` | EURO-A2 matching, audit, legacy mirroring |
| `scripts/backfill_european_fixture_results.py` | `--explain-matches`, audit output |
| `scripts/validate_euro_a2_result_backfill_repair.py` | **New** validation |
| `worldcup_predictor/database/repository.py` | `outcome_source` on `upsert_fixture_result` |

---

## Final recommendation

### `PARTIAL_BACKFILL_ACCEPTABLE`

UEFA result backfill is substantially repaired (78 missing vs 220; Conference League ~95% finished coverage). Remaining gaps are concentrated in early qualifying rounds with team-name / provider-ID mismatches — address via a dedicated team mapping table before relying on CL/UEL historical evaluation. **Upcoming fixture prediction wiring (EURO-B) can proceed on canonical API-Football rows** without waiting for full historical closure.

---

*EURO-A2 complete. No prediction generation. No public changes.*
