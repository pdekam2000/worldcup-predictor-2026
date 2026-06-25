# PHASE API-F — Provider Backfill Alignment for EGIE

**Mode:** Audit → Backfill → Validate → Backtest → Report  
**Date:** 2026-06-22  
**Production deploy:** NO (per phase rules)

---

## Executive Summary

Phase API-F implemented cache-first, quota-aware, resumable backfill tooling and ran it against the 380-fixture Premier League EGIE backtest cohort. **Strategies B–E remain identical to baseline A** because the paid features that differentiate them (xG, pressure, PL-aligned odds) still have **0% coverage**. A small partial win was achieved for API-Football lineups/statistics (8 → 12 fixtures, 2.11% → 3.16%), but this is insufficient to change backtest outcomes.

**Promotion decision: NOT SAFE** — Strategy F does not meaningfully beat A; calibration unchanged; paid-feature coverage insufficient; no production change recommended.

---

## 1. Root Cause

| Issue | Evidence | Impact |
|-------|----------|--------|
| **PL odds keyed to wrong fixture_ids** | 85 `odds_snapshots` rows map to World Cup / non-PL ids; **0** overlap with PL `fixture_id`s (e.g. `1035037`) | Strategy D/E/F odds agents never activate |
| **Sportmonks PL mapping missing** | 0/380 fixtures have `sportmonks_fixture_id`; SQLite enrichment is WC-only (league 732, 24 rows) | xG / pressure cannot load |
| **Sportmonks premium includes plan-blocked** | Plan probe: `xg_fixture_include=false`, `odds_include=false`, `predictions_include=false` | Live xG fetch returns 403 even if mapped |
| **API quota cap vs cohort size** | 380 fixtures × 4 resources ≈ 1,520 potential calls; run used `--max-api-calls 80` (20 live in final pass) | Only 4 additional fixtures backfilled per resource |
| **No PL odds in API cache** | `pl_fixtures_with_cached_odds: 0` from cache scan | Cache-first odds path has nothing for PL |

The prior audit conclusion stands: **the framework is wired; the data is not aligned or stored at scale.**

---

## 2. Fixture Mapping Coverage

**Artifact:** `artifacts/egie_provider_fixture_mapping_audit.json`

| Metric | Value |
|--------|-------|
| PL backtest fixtures | 380 |
| Canonical `fixture_id` | API-Football id (same as local SQLite) |
| Sportmonks mapped | 0 (0.0%) |
| PL odds aligned | 0 (0.0%) |
| `api_football_only` | 8 |
| `unmapped` (no SM, partial AF raw) | 372 |

Sample mapped fixture (`1035037` Burnley vs Man City): API-Football raw present for events/lineups/injuries/stats after backfill, but `sportmonks_fixture_id=null`, `has_pl_odds_snapshot=false`.

---

## 3. API Calls Used

**Artifact:** `artifacts/egie_provider_backfill_result.json`

| Provider | Live API calls | Notes |
|----------|----------------|-------|
| Sportmonks | 0 | Lookup/xG not attempted beyond cache; no PL rows in enrichment |
| API-Football | 20 | 4 fixtures × (events, lineups, stats, injuries) + 4 odds attempts |
| **Total** | **20** | Well under cap (80); resume skipped 32 existing rows |

Cache-first behavior confirmed: `skipped_existing_hits: 32`, WC odds preserved (`wc_odds_rows=1055` unchanged).

---

## 4. Data Coverage Before / After

| Feature | Before | After | Source |
|---------|--------|-------|--------|
| Events | 94.47% (359/380) | 94.47% | EGIE PG / SQLite |
| xG | 0% | 0% | Sportmonks |
| Pressure | 0% | 0% | Sportmonks |
| PL odds | 0% | 0% | SQLite `odds_snapshots` |
| Lineups | 2.11% (8) | 3.16% (12) | EGIE PG |
| Injuries | 0% | 0% | EGIE PG |
| Fixture statistics | 2.11% (8) | 3.16% (12) | EGIE PG |
| `xg_snapshots` (SQLite) | 0 | 0 | — |

**Utilization audit:** `artifacts/egie_paid_provider_audit.json`  
**Survival dataset rebuilt:** `data/egie/survival/survival_dataset.parquet`

---

## 5. A–F Backtest Comparison

**Artifact:** `artifacts/egie_paid_provider_backtest.json`  
**Cohort:** 200 PL fixtures scanned, 190 evaluable published

| Strategy | Label | FG Team | Goal Range | Soft Minute | Paid-data fixtures |
|----------|-------|---------|------------|-------------|-------------------|
| A | baseline | **42.86%** | 30.6% | 38.25% | 0 |
| B | + xG | **42.86%** | 30.6% | 38.25% | 0 |
| C | + pressure | **42.86%** | 30.6% | 38.25% | 0 |
| D | + odds | **42.86%** | 30.6% | 38.25% | 0 |
| E | + xG+pressure+odds | **42.86%** | 30.6% | 38.25% | 0 |
| F | full provider | **42.86%** | 30.6% | 38.25% | 183* |

\*Strategy F counts fixtures with **any** provider attachment (mostly goal events), not xG/pressure/odds. Metrics are **identical** to A — paid enrichments did not change picks.

**Calibration:** Unchanged across strategies (mean confidence 0.65 buckets; same hit rates).

---

## 6. Which Paid Features Helped / Did Not Help

| Feature | Helped winrate? | Reason |
|---------|-----------------|--------|
| xG | No | 0% stored → agents no-op |
| Pressure | No | 0% stored → agents no-op |
| PL odds | No | 0 PL-aligned snapshots |
| Lineups / stats | No | 3.16% coverage too sparse to move aggregates |
| Goal events | N/A (baseline) | Already 94% via Phase A ingest |

---

## 7. Quota Notes

- Backfill respects `--max-api-calls` and `--limit-fixtures`.
- Resume skips fixtures already in EGIE PG (`skipped_existing_hits`).
- WC odds and enrichment **not deleted**.
- To complete PL backfill at full depth: estimate **~1,500+ API-Football calls** (380 × 4 resources) plus Sportmonks PL mapping calls — run in batches with higher cap or dedicated ingest job.
- Sportmonks xG requires **plan upgrade** or alternate include path before quota spend is worthwhile.

---

## 8. Deliverables

| Item | Path | Status |
|------|------|--------|
| Fixture mapping audit | `artifacts/egie_provider_fixture_mapping_audit.json` | Done |
| Backfill orchestrator | `worldcup_predictor/egie/backfill/` | Done |
| Backfill CLI | `scripts/egie_provider_backfill.py` | Done |
| Mapping CLI | `scripts/egie_provider_fixture_mapping_audit.py` | Done |
| Validation | `scripts/validate_egie_provider_backfill_alignment.py` | 13/13 PASS |
| Survival rebuild | `data/egie/survival/survival_dataset.parquet` | Done |
| Utilization audit | `artifacts/egie_paid_provider_audit.json` | Done |
| A–F backtest | `artifacts/egie_paid_provider_backtest.json` | Done |

---

## 9. Promotion Decision

| Criterion | Result |
|-----------|--------|
| F improves over A meaningfully | **FAIL** — identical metrics |
| Calibration does not degrade | PASS — unchanged |
| Coverage sufficient | **FAIL** — xG/pressure/odds 0% |
| No leakage | PASS — backtest uses pre-kickoff store |
| No production regression risk | PASS — no deploy |

**Production recommendation:** Keep `EliteGoalTimingEngine` and production prediction path **unchanged**. Do not promote paid-provider strategies until PL odds are keyed to PL `fixture_id`s and Sportmonks xG/pressure are stored for a meaningful fraction of the cohort.

---

## 10. Next Recommended Steps

1. **PL odds alignment (highest leverage for D/E/F):** Run API-Football odds ingest scoped to PL `fixture_id`s only; verify `odds_snapshots` join on `fixtures.competition_key='premier_league'`.
2. **Batch API-Football raw backfill:** Re-run `scripts/egie_provider_backfill.py --providers api_football --max-api-calls 500` in resume mode until lineups/stats/injuries >80%.
3. **Sportmonks PL mapping:** Populate `sportmonks_fixture_enrichment` for league 8 via date+team lookup; bridge to EGIE PG.
4. **Plan audit:** Confirm Sportmonks subscription includes `xGFixture` and Pressure Index for domestic leagues before further SM quota spend.
5. **Re-run A–F** only after xG + PL odds coverage each exceed 50%.

**STOP — no production deploy.**
