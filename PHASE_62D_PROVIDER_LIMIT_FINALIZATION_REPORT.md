# PHASE 62D — Provider-Limit Finalization Report

**Generated:** 2026-06-26 (production finalization)  
**Mode:** Finalize → Validate → Diagnose Provider Limits → Report  
**Constraints honored:** No model, UI, public flag, or prediction logic changes.

---

## Executive summary

Phase 62C background run (PID **389056**) completed successfully on production. Finalization validation passed **12/13** checks. Pipeline recommendation remains **`PROVIDER_LIMITED`**.

**Decision:** **`PROVIDER_LIMITED_USE_CLASSIC_FOR_WC`**

World Cup EGIE cannot reach training/evaluation thresholds. Use the classic engine for WC until provider/data gaps are resolved. **Do not rerun Phase 61B** at this time.

---

## Part A — Run finalization

### Command

```bash
cd /opt/worldcup-predictor && bash scripts/phase62c_finalize_and_validate.sh
```

### Validation result

| Check | Result |
|-------|--------|
| Overall | **12/13 PASS** |
| `flags:unified_off` | **FAIL** (validator expects literal `UNIFIED_ENGINE_PUBLIC=false` in `settings.py`; flags remain off in practice — false negative) |
| All other checks | PASS |

### Background job completion

- Log: `/tmp/phase62b.log`
- Final line: `recommendation: PROVIDER_LIMITED`
- Processed **60/60** mapped fixtures with **0 API calls** (all `skipped_cached`)
- Progress counters `xg=0/0`, `lineups=0/0` reflect resume skip path (no re-parse); existing DB/cache rows retained

### Output files (production)

| File | Size | Status |
|------|------|--------|
| `PHASE_62B_SPORTMONKS_WC_XG_LINEUPS_COMPLETION_REPORT.md` | 1.5K | present |
| `data/validation/phase62b_sportmonks_wc_completion.json` | 13K | present |
| `data/validation/phase62b_mapping_audit.json` | 6.9K | present |
| `data/validation/phase62b_progress.json` | 1.2K | present (`status: completed`, 60 fixture IDs) |
| `data/validation/phase62b_validation_summary.json` | 1.4K | present |
| `data/egie/world_cup/raw/goal_timing_features_enriched/` | **328** JSON rows | present |
| `data/validation/phase62d_provider_diagnosis.json` | — | generated this phase |

### Final counts (production SQLite + pipeline)

| Metric | Value |
|--------|-------|
| Total WC fixtures | **328** |
| Finished fixtures | **316** |
| Usable EGIE (goal events on finished finals) | **29** (9.2%) |
| Sportmonks mapped | **60** (18.3%) |
| Sportmonks unmapped | **268** (81.7%) |
| xG snapshots | **60** (18.3%) |
| Lineup enrichment rows | **60** (18.3%) |
| Odds snapshots | **69** (21.0%) |
| Pressure coverage (pipeline) | **21.9%** |
| Enriched feature rows rebuilt | **328** |
| Survival rows | **316** |
| Team profiles | **65** |
| Sportmonks API calls (this run) | **0** |
| xG/lineups newly saved (this run) | **0** |
| **Final recommendation** | **`PROVIDER_LIMITED`** |

### Per-season fixture distribution

| Season | Fixtures | API-Football import (62B) |
|--------|----------|---------------------------|
| 1998 | 0 | 0 imported |
| 2002 | 0 | 0 imported |
| 2006 | 0 | 0 imported |
| 2010 | 64 | 64 upserted |
| 2014 | 64 | 64 upserted |
| 2018 | 64 | 64 upserted |
| 2022 | 64 | 64 upserted |
| 2026 | 72 | 60 upserted |

---

## Part B — Phase 62B report extraction

Source: `PHASE_62B_SPORTMONKS_WC_XG_LINEUPS_COMPLETION_REPORT.md` + `phase62b_sportmonks_wc_completion.json`

| Signal | Before | After | Target | Met? |
|--------|--------|-------|--------|------|
| Total fixtures | 328 | 328 | 500+ | No |
| Usable EGIE (goal events) | 29 | 29 | 500+ | No |
| xG coverage | 18.3% | 18.3% | 70% | No |
| Lineup coverage | 18.3% | 18.3% | 80% | No |
| Goal events | 9.2% | 9.2% | 90% | No |
| Odds | 21.0% | 21.0% | 80% | No |
| Pressure | 21.9% | 21.9% | — | — |

### Mapping quality

- Mapped: **60** (avg confidence **0.975**, source: `cache_index`)
- Unmapped: **268**
- Blocked duplicates: **0**
- Sportmonks cache index size: **60** files (league 732, season 26618 — WC 2026 group fixtures)

### Sportmonks import (this run)

- API calls: **0**
- Cache hits: **0** (resume treated all as already imported)
- Cache hit ratio: **0.0%** (denominator not incremented on skip path)
- xG snapshots saved: **0** (already present from prior partial run)
- Lineups saved: **0** (already present)

### Cache verification (sample)

All 60 Sportmonks cache files inspected contain **real** premium data:

- `has_lineups: true` (49–52 players per fixture)
- `has_xg_fixture: true`
- `league_id: 732`, `season_id: 26618`

Subscription is **working** for the **2026 WC fixtures already cached**. The gap is coverage breadth, not parse failure on cached payloads.

### Missing reasons (aggregate)

| Category | Count | Share of 328 |
|----------|-------|--------------|
| No Sportmonks mapping | 268 | 81.7% |
| Mapped + xG/lineup available | 60 | 18.3% |
| Goal events missing (finished) | 287 | 90.8% of finished |
| API-Football seasons 1998–2006 | 0 fixtures | 100% missing |

### PostgreSQL cross-check

- `egie_raw_wc`: **298** rows (PG has raw EGIE artifacts)
- `goal_timing_features_wc`: **0**
- `goal_timing_predictions_wc`: **0**
- SQLite `fixture_goal_events`: only **29** fixtures — production goal-event backfill is severely incomplete vs local dev (~289). This is a **separate operational gap** from Sportmonks limits.

---

## Part C — Provider limitation matrix

Classification per feature. **Do not retry blindly** where reason is provider/subscription or architectural (cache-index-only mapping).

| Feature | Coverage | Affected fixtures | Primary missing reason | Secondary / notes | Retry blindly? |
|---------|----------|-------------------|------------------------|-------------------|----------------|
| **xG** | 18.3% (60/328) | 268 unmapped; 0 mapped-without-xG | `fixture_not_mapped` | Mapping uses **cache index only** (`mapping_audit._load_sportmonks_index`); no live season fetch for 2010–2022 finals. 60 mapped fixtures have `xg_available` in DB. | **No** — need live SM season import or support confirmation |
| **Lineups** | 18.3% (60/328) | Same 268 | `fixture_not_mapped` | Cached 2026 payloads include lineups (49–52 players). Historical finals never entered cache index. | **No** |
| **Pressure** | 21.9% (72/328) | ~256 without pressure | `fixture_not_mapped` + `provider_no_data` | Pressure tied to `sportmonks_fixture_enrichment` / SM cache; same mapping ceiling as xG. Enriched rows show `pressure_available: false` for unmapped fixtures. | **No** |
| **Odds** | 21.0% (69/328) | 259 | `provider_no_data` / API-Football partial | API-Football odds import saved 0 new odds in 62B run; existing 69 snapshots only. Historical + quota limits likely. | **No** — separate odds provider pass needed |
| **Player stats** | 0% (not in WC EGIE scope) | 328 | `endpoint_not_available` | Phase 62/62B pipeline does not ingest player-level stats for WC EGIE; no table/builder wired. | **N/A** |

### Root-cause summary

1. **API-Football league 1 ceiling** — ~328 fixtures total; seasons 1998/2002/2006 return **zero** fixtures. Hard pool limit near 330–400 across 1998–2026.
2. **Sportmonks mapping is cache-index-only** — Only fixtures already present under `data/egie/world_cup/raw/sportmonks/` (60 × WC 2026) get mapped. **256 historical finals (2010–2022)** were never in the index, so they cannot gain xG/lineups/pressure without a **new import strategy** (live `/fixtures` by season, not cache-only audit).
3. **Goal events on production** — Only **29/316** finished fixtures have `fixture_goal_events` despite 298 PG `egie_raw_wc` rows. EGIE usable overlap for Phase 61B remains **~0%** until goal-event backfill runs on production.
4. **This 62C run added no new provider data** — Correct behavior given resume + full cache; not a failure, but confirms we hit a **plateau**.

---

## Part D — Decision

### Options evaluated

| Option | Verdict | Rationale |
|--------|---------|-----------|
| 1. `READY_FOR_PHASE_61B_RERUN` | **Rejected** | 29 usable EGIE vs 500 target; xG 18.3% vs 70%; lineups 18.3% vs 80%; goal events 9.2% vs 90%. No meaningful WC EGIE overlap for unified evaluation. |
| 2. `PROVIDER_LIMITED_USE_CLASSIC_FOR_WC` | **Selected** | WC cannot support EGIE/unified training at required depth. Classic engine is the correct production path for World Cup pages. |
| 3. `SWITCH_EGIE_TRAINING_TO_UEFA_PLUS_WC` | Deferred | Valid follow-on for **unified engine training** (UEFA club has richer Sportmonks cache from Phase 22 work), but does not fix WC page provider limits. Recommend as **Phase 63** after support questions answered. |
| 4. `NEED_PROVIDER_SUPPORT_QUESTIONS` | Partial — embed in next phase | Required before any historical WC Sportmonks retry, but not sufficient alone; operational fixes (mapping + goal backfill) also needed. |

### Recommended next phase

**`PROVIDER_LIMITED_USE_CLASSIC_FOR_WC`**

### Phase 61B rerun meaningful?

**No.** Criteria for `READY_FOR_PHASE_61B_RERUN` (from `pipeline_62b.recommend_phase_62b`):

- `all_targets_met` → **False**
- `usable_finals >= 500` → **29**

Rerunning Phase 61B now would reproduce `NEED_MORE_DATA` / `ADMIN_PREVIEW_ONLY` with no new signal.

### Actions explicitly not taken (per scope)

- Phase 61B **not** rerun
- No public unified engine flags enabled
- No model / UI / prediction logic changes

---

## Part E — Sportmonks support questions

Before spending API budget on historical WC retries, confirm with Sportmonks support:

1. **Historical World Cup coverage** — For league ID **732** (FIFA World Cup), which seasons (2010, 2014, 2018, 2022) include **xGFixture**, **lineups**, and **pressure** includes on our current subscription tier?
2. **Season-based bulk access** — What is the recommended endpoint/workflow to list all fixtures for a past WC season (e.g. season ID for Russia 2018, Qatar 2022) with premium includes, without per-fixture discovery?
3. **1998–2006 availability** — Are xG and expected lineups available for WC tournaments before 2010, or is coverage post-2010 only?
4. **Rate limits vs historical depth** — Given ~64 fixtures per tournament × 4 tournaments = 256 API calls minimum for mapping alone, are there bulk/historical packs that avoid per-fixture premium include charges?
5. **Team name normalization** — API-Football uses names like `"Cape Verde Islands"` / `"Congo DR"` while Sportmonks may differ; is there a stable `external_id` or fixture ID crosswalk for WC we should use instead of fuzzy name+date matching?
6. **Pressure metric scope** — Is `pressure` (or equivalent) included for international tournaments on our plan, or club-only?

---

## Appendix — Validation checklist

| Criterion | Target | Actual | Pass |
|-----------|--------|--------|------|
| Fixtures | 500+ | 328 | No |
| xG | ≥70% | 18.3% | No |
| Lineups | ≥80% | 18.3% | No |
| Goal events | ≥90% | 9.2% | No |
| Odds | ≥80% | 21.0% | No |
| SM mapping rate | — | 18.3% | Low |
| Phase 62C job completed | yes | yes | Yes |
| Unified public flags | off | off | Yes (operational) |

---

## Suggested follow-up phases (not executed)

1. **Production goal-event backfill** — Raise `fixture_goal_events` from 29 toward local-dev levels (~289) using existing API-Football ingest; no model change.
2. **Phase 63 — Live Sportmonks season import** — Replace cache-index-only mapping with season-scoped SM fixture pull for 2010–2022 (after support confirms availability).
3. **Phase 63B — UEFA + WC EGIE training set** — Train/evaluate unified engine on UEFA club (high xG coverage) plus limited WC slice for tournament generalization.

---

*Phase 62D complete. Stopped after report per scope. Phase 61B not rerun. Public unified flags not enabled.*
