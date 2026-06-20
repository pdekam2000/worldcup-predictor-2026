# Phase 30E — Data Coverage Repair Report

**Status:** Implementation complete — validated locally. **Not deployed** (per instructions).

**Fixture validation target:** `1539007` — Netherlands vs Sweden

---

## Summary

Phase 30E fixes false “Missing lineups” / “No odds data” UI flags, adds “Official lineup pending” for projected XI pre-kickoff, persists fixture identity fields in SQLite, and awards partial data-quality credit for projected lineups when official API lineups are intentionally skipped.

| Goal | Result |
|------|--------|
| Remove false **Missing lineups** | **Fixed** — `data_signals.missing_lineups = false` when lineup/expected agents have data |
| Remove false **No odds data** | **Fixed** — `odds_available = true` when `odds_market_agent` partial or `market_consensus_agent` available |
| Show **Official lineup pending** | **Fixed** — new badge via `official_lineup_pending` / `lineup_coverage: "pending"` |
| SQLite `home_team_id`, `away_team_id`, `league_id`, `season` | **Fixed** — `upsert_fixture` + `update_fixture_identity` + parser/schedule fields |
| Projected lineups DQ partial score | **Fixed** — **10/15** when `skipped=far_from_kickoff` or projected XI items exist |

---

## 30E-1 — Display truth fix (P0)

### Root cause (from Phase 30D)

`data_signals_from_specialist_summary()` looked up agent keys `"lineup"`, `"injury"`, `"odds"` while the orchestrator registers `"lineup_agent"`, `"injury_suspension_agent"`, `"odds_market_agent"`. Empty lookups always produced false negatives.

### Changes

**`worldcup_predictor/api/display_helpers.py`**

- Resolve agents via canonical keys + legacy aliases.
- New fields:
  - `lineup_coverage`: `"official" | "pending" | "missing"`
  - `official_lineup_pending`: bool
- `odds_available`: true when any of `odds_market_agent`, `market_consensus_agent`, `odds_control_agent` is `available` or `partial`.
- `missing_lineups`: true only when `lineup_coverage == "missing"`.

**`base44-d/src/components/match/DataQualityBadge.jsx`**

- New sky badge: **Official lineup pending** when `official_lineup_pending && !missing_lineups`.
- **Missing lineups** / **No odds data** unchanged structurally but now driven by corrected signals.

### Validation (fixture 1539007 specialist snapshot)

```
missing_lineups: False
official_lineup_pending: True
lineup_coverage: pending
odds_available: True
```

Live local predict (`PredictPipeline`, API configured): same signal outcome confirmed.

---

## 30E-2 — SQLite fixture persistence (P1)

### Root cause

Schema had `home_team_id`, `away_team_id`, `league_id`, `season` columns but `upsert_fixture()` never wrote them. `sync_service` and `league_history_importer` already passed `league_id`/`season` kwargs that were previously ignored.

### Changes

| File | Change |
|------|--------|
| `worldcup_predictor/domain/schedule.py` | Optional `home_team_id`, `away_team_id`, `league_id`, `season` on `TournamentFixture` |
| `worldcup_predictor/database/repository.py` | Extended `upsert_fixture()`; new `update_fixture_identity()` |
| `worldcup_predictor/integrations/fixture_api_parser.py` | Parse team IDs + league/season from API items |
| `worldcup_predictor/schedule/worldcup_schedule_service.py` | Same fields in `_parse_api_fixture` / `_from_domain_fixture` |
| `worldcup_predictor/quota/local_first.py` | Hydrate IDs from DB rows into `TournamentFixture` |
| `worldcup_predictor/quota/smart_prediction_fetch.py` | After intelligence build, persist resolved IDs via `update_fixture_identity()` |

### Behaviour

- New/updated fixtures from import or schedule sync store full identity.
- Each successful predict with resolved team IDs patches the SQLite row (fixes stale NULL rows like 1539007 over time).
- `COALESCE` on update avoids wiping IDs with NULL on partial writes.

### Note

Existing rows remain NULL until the next predict or re-import. Bulk backfill was **out of scope** (30E-4 skipped).

---

## 30E-3 — Data quality projected lineups (P1)

### Root cause

Official lineups API is skipped >4 h pre-kickoff (`should_fetch_lineups`), yielding `lineups.available=false` and **0/15** DQ points despite `expected_lineup_agent` and projected XI being available.

### Changes

**`worldcup_predictor/data_quality/intelligence_scoring.py`**

- `_projected_lineups_score()`: awards **10 of 15** when:
  - `lineups.skipped == "far_from_kickoff"`, or
  - lineup `items` contain `startXI`, or
  - Sportmonks supplemental lineups present.

**`worldcup_predictor/data_quality/transparency.py`**

- Reason text uses “projected lineups (official pending)” when partial lineups credit applied.

### DQ impact (fixture 1539007 pattern)

| Scenario | Before | After |
|----------|--------|-------|
| Synthetic report (far_from_kickoff + odds + form) | 55 | **65** |
| Live predict (local, 2026-06-20) | 55 | **60** |

Live run reached **60** (+5): partial lineups applied; full **65** requires all core components (e.g. standings) — synthetic path confirms **+10 lineups** logic.

---

## Validation

**Script:** `scripts/validate_phase30e_data_coverage_repair.py`

```
Phase 30E validation — fixture 1539007

30E-1 display_helpers .............. 4/4 PASS
30E-3 projected lineups DQ ......... 2/2 PASS (display_total 65 synthetic)
30E-2 SQLite persistence ........... 7/7 PASS
Live predict 1539007 (optional) .... signals PASS, DQ 60 (>= 58 threshold)

All Phase 30E validation checks passed.
```

Run:

```bash
python scripts/validate_phase30e_data_coverage_repair.py
```

---

## Files changed

| File | Phase |
|------|-------|
| `worldcup_predictor/api/display_helpers.py` | 30E-1 |
| `base44-d/src/components/match/DataQualityBadge.jsx` | 30E-1 |
| `worldcup_predictor/domain/schedule.py` | 30E-2 |
| `worldcup_predictor/database/repository.py` | 30E-2 |
| `worldcup_predictor/integrations/fixture_api_parser.py` | 30E-2 |
| `worldcup_predictor/schedule/worldcup_schedule_service.py` | 30E-2 |
| `worldcup_predictor/quota/local_first.py` | 30E-2 |
| `worldcup_predictor/quota/smart_prediction_fetch.py` | 30E-2 |
| `worldcup_predictor/data_quality/intelligence_scoring.py` | 30E-3 |
| `worldcup_predictor/data_quality/transparency.py` | 30E-3 |
| `scripts/validate_phase30e_data_coverage_repair.py` | validation |

**Skipped (per request):** 30E-4 enrichment persistence, 30E-5 extended validation suite / deploy.

---

## Expected UI after deploy (fixture 1539007)

| Badge | Before | After |
|-------|--------|-------|
| Missing lineups | Shown (false) | **Hidden** |
| No odds data | Shown (false) | **Hidden** |
| Official lineup pending | — | **Shown** |
| Odds available | Hidden | **Shown** |
| Medium data ~55–60% | Yes | **~60–65%** (context-dependent) |

---

## Deploy checklist (manual)

1. Deploy backend + frontend (`display_helpers` + `DataQualityBadge`).
2. Restart API service.
3. Re-run predict for 1539007 (or wait for cache TTL) so `data_signals` refresh.
4. Optional: one-time SQL backfill of team IDs for upcoming WC fixtures (future 30E-4).

---

## Stop condition

Implementation and validation complete. **No automatic deploy.**
