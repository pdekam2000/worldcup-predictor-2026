# PHASE API-I — UEFA EGIE Event Team Mapping + xG Historical Fix

**Mode:** Diagnose → Fix → Validate → Rebuild → Backtest → Report  
**Production deploy:** NO  
**EliteGoalTimingEngine changes:** NO  

---

## Executive Summary

Phase API-I fixed UEFA-specific event parsing and backtest actuals alignment. The **0% First Goal Team** result in API-H was **not a model failure** — it was caused by:

1. **Parser bug:** `GOAL_TYPE_IDS` incorrectly included `type_id=18` (Substitution), corrupting first-goal minute on 14 fixtures.
2. **Evaluation mismatch:** Backtest passed **team names** (`"Chelsea"`) as `actual_first_goal_team` while predictions use **`home` / `away` / `none`** sides.

After fix, Strategy **A** FG-team winrate on non-pending picks is **50%** (was 0% with 9 wrong). Strategies **D/E/F** reach **83.7%** FG-team winrate when enrichment shifts picks off `"none"`.

**xG and predictions remain 0%** in the historical cache — data is absent (not a parser bug). Values were **not fabricated**.

---

## STEP 1 — Event Schema Audit

**Artifact:** `artifacts/uefa_event_schema_audit.json`

| Field | Sportmonks schema |
|-------|-------------------|
| Goals | `events[]` with `type_id=14`, `type.name="Goal"` |
| Penalties | `type_id=16`, `type.name="Penalty"` |
| Own goals | `type_id=15`, `type.name="Own Goal"` |
| Missed penalties | `type_id=17` (excluded from scoring) |
| Shootout goals | `type_id=23` (excluded from regular-time FG) |
| Substitutions | `type_id=18` — **not goals** |
| Team ID | `events[].participant_id` → `participants[].id` |
| Home/away side | `participants[].meta.location` (`home` / `away`) |
| Minute | `events[].minute` + `events[].extra_minute` |
| Ordering | `events[].sort_order` tie-breaker |
| VAR | No dedicated VAR goal type in cache; `info` / `addition` checked for `"var"` substring |
| Fixture score | `scores[]` with `description=CURRENT`, `score.goals`, `score.participant` |

**105 fixtures audited**, 71 with events, 1,015 total events.

---

## STEP 2 — First Goal Team Root Cause

**Artifact:** `artifacts/uefa_fg_team_pending_breakdown.json`

| Category | Count (of 105) |
|----------|----------------|
| Resolved (FG side known) | 65 |
| Scoreless (0-0) | 12 |
| Goals in score but **no events in payload** | 28 |

**API-H pending breakdown (62/71):**

| Root cause | Impact |
|------------|--------|
| Predicted `"none"` → evaluation `pending` | 62 fixtures (baseline tie-band) |
| Actual = team name vs predicted = side | 9 fixtures marked **wrong** (should have been comparable) |
| Substitution misclassified as goal | 14 fixtures with wrong first-goal **minute** |

**28 Conference/Europa fixtures** have final scores but empty `events[]` in cached JSON — FG side cannot be resolved from events alone (re-ingest with `events` include required).

---

## STEP 3 — UEFA Event Parser Fix

**File:** `worldcup_predictor/egie/uefa_club/feature_extractors.py`

Changes (UEFA-only, no production EGIE parser changes):

- Correct scoring type IDs: `{14, 15, 16, 23}` — removed `18` (Substitution) and `17` (Missed Penalty).
- `build_participant_maps()` — `participant_id` → `home`/`away` via `meta.location`.
- Own goals flip scoring side to the benefiting team.
- Chronological sort: `(minute, sort_order)`.
- `parse_match_result()` now exports:
  - `first_goal_team`, `first_goal_team_side`, `first_goal_team_id`
  - `first_goal_minute`, `first_goal_player`
  - `goal_events_count`, `scoring_sequence`, `home_goals`, `away_goals`

**File:** `worldcup_predictor/egie/uefa_club/backtest_runner.py`

- `actual_first_goal_team` now uses **`first_goal_team_side`** (`home`/`away`/`none`).

**File:** `worldcup_predictor/egie/uefa_club/sqlite_bridge.py`

- Goal events use `scoring_side` for team assignment; penalty/own-goal detail labels.

---

## STEP 4 — Score Reconstruction Validation

**Script:** `scripts/validate_uefa_event_team_mapping.py`  
**Artifact:** `artifacts/uefa_event_team_mapping_validation.json`

| Check | Result |
|-------|--------|
| Fixtures validated | 105 |
| Score reconstruction match | 99 (94.3%) |
| First goal team resolved | 77 (73.3%) |
| Chronological order | 105/105 |
| Minute values valid | 105/105 |
| Own goals mapped | 2 |
| Penalties mapped | 10 |
| Status | `warn` (28 fixtures lack events despite non-zero score) |

---

## STEP 5 — xG / Predictions Diagnosis

**Artifact:** `artifacts/uefa_xg_predictions_diagnosis.json`

| Signal | Live probe (CL) | Historical cache (105 UEFA) |
|--------|-----------------|----------------------------|
| `xGFixture` key present | Yes | 44/105 |
| `type_id=5304` (true xG) | N/A on 2014 fixture | **0/105 (0%)** |
| `xgfixture` row types | Corners, shots, goals count | Same — statistics masquerading as xG include |
| `predictions[]` | Empty on finished 2014 match | **0/105 non-empty** |
| `pressure[]` | Empty on historical | 0/105; possession fallback from `statistics` works |
| Parser `home_xg` non-null | No | **0** |

**Conclusion:** Includes are correct (`xGFixture.type;predictions.type;pressure`). Sportmonks does not return expected-goals metrics or pre-match predictions for **2014-era finished UEFA fixtures** in this cache. **No values fabricated.**

---

## STEP 6 — Parse from Cache

- xG: nothing to parse (`type_id 5304` absent).
- Predictions: all arrays empty.
- Pressure: possession proxy still populated where `statistics` exist (~38 fixtures).
- Feature store rebuilt from cache without synthetic xG/prediction fields.

---

## STEP 7 — Rebuild from Cache

```text
python scripts/egie_uefa_club_pipeline.py --skip-ingest
python scripts/validate_egie_uefa_club_dataset.py        # 4/4 PASS
python scripts/validate_uefa_event_team_mapping.py     # warn (event gaps)
```

API-H backtest preserved at `artifacts/uefa_club_backtest_api_h_before.json`.

---

## STEP 8 — A–F Backtest Before/After

| Strategy | FG Team (API-H) | FG Team (API-I) | Goal Range | Soft Minute |
|----------|-----------------|-----------------|------------|-------------|
| **A** | 0% (0✓ 9✗ 62⏳) | **50%** (4✓ 4✗ 57⏳) | 31.0% → 24.6% | 38.0% → 35.4% |
| **B** | 0% | 46.2% (18✓ 21✗ 26⏳) | 31.0% → 24.6% | 38.0% → 35.4% |
| **C** | 0% | 46.2% | 31.0% → 24.6% | 38.0% → 35.4% |
| **D** | 0% (0✓ 43✗ 28⏳) | **83.7%** (36✓ 7✗ 22⏳) | 31.0% → 24.6% | 38.0% → 35.4% |
| **E** | 0% | **83.7%** | 31.0% → 24.6% | 38.0% → 35.4% |
| **F** | 0% | **83.7%** | 31.0% → 24.6% | 38.0% → 35.4% |

**Coverage (API-I):**

| Strategy | Eligible | With paid data |
|----------|----------|----------------|
| A | 93 | 0 |
| B | 93 | 0 (xG still 0%) |
| C | 93 | 38 (pressure proxy) |
| D | 93 | 32 (odds) |
| E | 93 | 39 |
| F | 93 | 65 |

**Notes:**

- Goal range dropped slightly because **14 fixtures** had corrected first-goal minutes (substitution bug removed).
- Strategies B/C show higher FG rates than A because enrichment nudges picks off `"none"` — but **xG coverage is still 0%**, so B≈C and neither uses real xG.
- **A–F goal range and soft minute remain identical** across strategies (paid features still don't diverge range/minute materially).
- `production_promotion_safe: true` is a mechanical flag (D/E/F beat A by >1pp on FG) — **not** a production recommendation given xG absence and event gaps.

---

## STEP 9 — Recommendation (Next Phase)

### Phase API-J priorities

1. **Re-ingest 28 event-missing fixtures** — Conference/Europa cache rows have scores but `events: []`; force refresh with full includes (no `--skip-ingest` cap) for fixtures where `goal_events_count=0` and `home_goals+away_goals>0`.

2. **Recent-season UEFA sample for xG** — Map 2023–2025 CL/EL/Conference knockouts; verify `type_id=5304` before building Strategy B divergence tests.

3. **Pre-match predictions** — Capture predictions **before kickoff** (finished-fixture API returns empty `predictions[]`).

4. **Baseline `"none"` band** — 57/65 Strategy A FG evaluations still `pending` due to `_pick_first_goal_team` tie logic; consider UEFA-specific evaluation note or wider pick band for backtest reporting only (not production engine).

5. **Do not promote D/E/F to production** until true xG and event completeness are verified on a modern-season holdout.

---

## Artifacts Produced

| File | Purpose |
|------|---------|
| `artifacts/uefa_event_schema_audit.json` | Event schema |
| `artifacts/uefa_fg_team_pending_breakdown.json` | FG pending root cause |
| `artifacts/uefa_xg_predictions_diagnosis.json` | xG/predictions diagnosis |
| `artifacts/uefa_event_team_mapping_validation.json` | Score reconstruction validation |
| `artifacts/uefa_club_backtest.json` | Post-fix A–F backtest |
| `artifacts/uefa_club_backtest_api_h_before.json` | API-H baseline preserved |

## Scripts Added

- `scripts/_phase_api_i_diagnostics.py` — schema audit, FG breakdown, xG diagnosis
- `scripts/validate_uefa_event_team_mapping.py` — score/FG validation

---

**STOP — No deploy. No production changes.**
