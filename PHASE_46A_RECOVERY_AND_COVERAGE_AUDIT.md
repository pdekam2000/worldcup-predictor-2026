# Phase 46A — Prediction Data Recovery & Coverage Audit

**Mode:** READ ONLY — no import, no deploy, no database modifications  
**Date:** 2026-06-21  
**Purpose:** Prepare for full historical accuracy and advanced market evaluation  
**Environments scanned:** Local workspace + production (`91.107.188.229`)

---

## Executive summary

| Dimension | Production | Local dev |
|-----------|------------|-----------|
| **Global archive (`worldcup_stored_predictions`)** | 12 fixtures | 2 fixtures |
| **Fixtures with artifacts outside archive** | **~44** (56 total tracked − 12 archived) | **~31** |
| **Cache-only recoverable (full payload)** | **~35** cache files, **52** fixtures marked `recoverable=yes` | 3 cache files |
| **JSONL-only (partial payload)** | ~38 fixture appearances | 26 fixtures |
| **Legacy SQLite-only** | 5 fixtures | 5 fixtures |
| **Markets in archive but not WC-evaluated** | HT (11), First Goal (11), Goalscorer (7) | Same pattern |
| **WC-evaluated markets (when FT)** | 1X2, O/U, BTTS, DC only | Same |

**Conclusion:** Recovery value is concentrated in **cache files** (full API payloads not yet in archive). Advanced markets are **generated in predictions** but **not evaluated** in the production WC pipeline — legacy verification agent already has evaluators for HT, scoreline, first goal, and scorer.

---

## 1. Predictions existing only outside global archive

### 1.1 Source overlap (production)

| Source | Fixture appearances* | Full payload? | In archive? |
|--------|---------------------:|---------------|-------------|
| `worldcup_stored_predictions` | 12 | Yes | — (authoritative) |
| `.cache/predictions/` | 35 files | **Yes** | Mostly **no** (~27 cache-only est.) |
| `data/predictions/prediction_history.jsonl` | 101 lines / ~38 fixtures | Partial | Mostly **no** |
| `predictions` + `prediction_markets` (legacy) | 5 fixtures | Reconstructable | **no** |
| `verification_results` | 70 rows / 16 fixtures | Eval metadata only | N/A (audit) |
| `prediction_verification.jsonl` | 542 lines | Per-market audit | N/A |

\*Fixture appearances = rows in unified inventory; fixtures may appear in multiple sources.

### 1.2 Recoverability summary (production inventory scan)

| Recoverable | Count | Meaning |
|-------------|------:|---------|
| **yes** | **52** | Full or near-full payload recoverable (primarily **cache**) |
| **partial** | **4** | JSONL/legacy summary fields only |
| **no** | **0** | (verification-only rows excluded from yes/partial in non-archive set) |

### 1.3 Unified inventory (representative rows)

Production fixtures **not in archive** with **recoverable=yes** (sample):

| fixture_id | source | prediction_date | markets_available | recoverable |
|------------|--------|-----------------|-------------------|-------------|
| 1378969 | cache, jsonl | 2026-06-19* | 1x2, O/U, BTTS, HT, first_goal, goalscorer, top_scorer | **yes** |
| 1378970 | cache, jsonl | 2026-06-19* | same bundle | **yes** |
| 1378971 | cache, jsonl | 2026-06-19* | same bundle | **yes** |
| 1378972 | cache, jsonl | 2026-06-19* | same bundle | **yes** |
| 123 | cache | test epoch | 1x2 | **yes** (test fixture) |

Local fixtures **not in archive** (sample):

| fixture_id | source | prediction_date | markets_available | recoverable |
|------------|--------|-----------------|-------------------|-------------|
| 1489369 | jsonl, legacy_sqlite, verification | 2026-06-11 | 1x2, O/U, HT, correct_score, first_goal | **yes** (legacy reconstruct) |
| 1489370 | jsonl, legacy_sqlite, verification | 2026-06-12 | same | **yes** |
| 719349 | jsonl | 2026-06-17 | 1x2, scorer fields | **partial** |
| 99, 123 | cache | dev test | 1x2 | **yes** |

\*Cache `cached_at` timestamps may appear as Unix floats in some files; JSONL uses ISO `created_at`.

### 1.4 Full inventory export

Read-only scan artifact (local): `artifacts/phase46a_local_inventory.json` (31 rows).  
Production scan: 56 unique fixtures in unified inventory (12 archived + 44 external-only appearances).

### 1.5 Orphans and duplicates

| Type | Finding |
|------|---------|
| **Orphaned JSONL fixtures** | ~26 local / ~30+ prod fixtures in JSONL with no archive row |
| **Cache orphans** | ~27 prod cache files with no matching `worldcup_stored_predictions` row |
| **Legacy orphans** | 5 fixtures in `predictions` table, 0 overlap with archive |
| **Duplicates** | Verification JSONL append-only (448 dedupe keys / 542 lines); archive PK prevents duplicate fixtures |

---

## 2. Evaluation coverage audit

### 2.1 Current WC pipeline (`pick_evaluator.py`)

**Evaluated today (when fixture finished):**

| Market | Data in stored payload (prod n=12) | Evaluator | DB column / summary key |
|--------|--------------------------------------|-----------|---------------------------|
| **1X2** | 12/12 | **Yes** `_eval_1x2` | `market_1x2_status` |
| **Over/Under 2.5** | 12/12 | **Yes** `_eval_ou` | `market_ou_status` |
| **BTTS** | 11/12 | **Yes** `_eval_btts` | `market_btts_status` |
| **Double Chance** | partial | **Yes** `_eval_double_chance` | `market_dc_status` |
| Safe/Value/Aggressive/Caution picks | most rows | **Yes** `_eval_pick_dict` | `detail_json.markets` |

### 2.2 Advanced markets — audit matrix

| Market | Data in stored payload (prod) | Evaluator in WC pipeline | Evaluator elsewhere | Effort to add WC eval |
|--------|------------------------------|--------------------------|---------------------|----------------------|
| **HT Result** | **11/12** (`detailed_markets.halftime`) | **Missing** | **Yes** — `accuracy_optimization._eval_ht_result()`; legacy `halftime_goals` market; `AutoVerificationAgent` halftime bucket | **S** (1–2 days) — needs HT score from `fixture_results.halftime_score` or events |
| **Correct Score** | rare in archive; legacy has `scoreline_exact` | **Missing** | **Yes** — `AutoVerificationAgent` scoreline_exact; shadow scoreline engine | **M** (2–4 days) — map `detailed_markets.correct_scores` + exact score match |
| **First Goal Team** | **11/12** (`detailed_markets.first_goal`) | **Missing** | **Yes** — `accuracy_optimization._eval_first_team_to_score()`; verification agent | **M** (2–3 days) — needs goal events or first-scorer ordering from API-Football events |
| **Goal Minute** | in payload as `first_goal.minute_range` / band | **Missing** | **Partial** — predicted as band only; no minute-level eval in verification | **L** (4–7 days) — needs event minute + bucket mapping rules |
| **Goalscorer** | **7/12** (`detailed_markets.goalscorer`) | **Missing** | **Yes** — `AutoVerificationAgent` `first_goal_scorer` via `goal_scorers` list | **M** (3–5 days) — needs fixture events with scorer names; fuzzy name match |

**Effort key:** S = small (reuse existing helper + outcome field), M = medium (new outcome resolution), L = large (new data pipeline + rules)

### 2.3 Outcome data availability for advanced eval

| Market | Required outcome source | Currently stored? |
|--------|-------------------------|-------------------|
| HT Result | `fixture_results.halftime_score` or HT goals | **Partial** — column exists; not always populated on refresh |
| Correct Score | `fixture_results.final_score` | **Yes** when FT |
| First Goal Team | API-Football `fixtures/events` (goal order) | **Fetched for UI** (`match_center.enrich_fixture`) — **not persisted** for eval |
| Goal Minute | Events with minute | Same — fetched, not stored for eval |
| Goalscorer | Events + player names | Same; verification agent expects `goal_scorers` on fixture object |

### 2.4 Gap: prediction vs evaluation

```
Prediction path (scoring_engine.py, predict_pipeline.py)
  → generates: HT, first_goal, scoreline_candidates, goalscorer in detailed_markets

WC evaluation path (pick_evaluator.py)
  → evaluates: 1X2, O/U, BTTS, DC, pick tiers ONLY

Legacy verification path (auto_verification_agent.py)
  → evaluates: HT bucket, scoreline, first goal team, first goal scorer
  → NOT connected to worldcup_prediction_evaluations or public Performance Center
```

---

## 3. API utilization audit

### 3.1 API-Football

**Client:** `worldcup_predictor/clients/api_football.py`

| Endpoint / method | Available | Used in predict path | Used elsewhere | Fields largely ignored |
|-------------------|-----------|-------------------|----------------|------------------------|
| `fixtures` (list/upcoming) | Yes | Yes (schedule) | Match center, sync | — |
| `fixtures?id=` | Yes | Yes | Result refresh, match intel | embedded weather stubbed off |
| `teams/statistics` | Yes | Yes | Form, xG agent | many stat keys unused |
| `fixtures/headtohead` | Yes | Yes | H2H scoring | — |
| `injuries` | Yes | Yes | Injury agent, WDE | — |
| `fixtures/statistics` | Yes | Yes | xG intelligence | non-xG stats mostly unused |
| `fixtures/lineups` | Yes | Yes | Lineup agent, WDE | bench/detail unused |
| `odds` | Yes | Yes | Odds/consensus/WDE | bookmaker depth partial |
| `fixtures/events` | Yes | **Quality score only** | Match center UI, league import | **goal order, minutes, scorers not fed to eval store** |
| `standings` | Yes | Yes | Tournament context | — |
| `teams/fixtures` (recent) | Yes | Yes | Form snapshots | — |
| `fixtures/live` | Yes | No (predict) | Match center | — |
| `fixtures` (historical/season) | Yes | No | Backfill, import | — |
| `players/topscorers` | Yes | Deep fetch only | Player quality agent | — |
| `fixtures/players` | Yes | Deep fetch only | Player quality | — |
| `players/squads` | Yes | Deep fetch only | Player quality | — |
| `predictions` (API-Football model) | Yes | **Reference trace only** | OddsMarketAgent disclaimer | percentages never override model |
| `teams/sidelined` | Yes | Gap-fill injuries | — | — |

**Highest-value ignored fields for 46C:** `fixtures/events` (first goal, minute, scorer), halftime score in fixture payload, API-Football `predictions` reference for calibration audit only.

### 3.2 Sportmonks

**Includes requested:** `sportmonks_enrichment.py`

| Include / field group | Available | Consumed in predict path | Largely ignored |
|----------------------|-----------|--------------------------|-----------------|
| `participants` | Yes | Team mapping / normalization | meta beyond IDs |
| `statistics` | Yes | xG extraction, flat stats → supplemental | most non-xG stat keys |
| `lineups` | Yes | Gap-fill when API-Football empty | — |
| `formations` | Yes | Stored in normalized payload | **not WDE factor** |
| `sidelined.sideline` | Yes | Gap-fill injuries | — |
| `metadata` | Yes | Odds/prediction engines | — |
| `scores` | Yes | Stored in supplemental | **not used in scoring/eval** |
| `state` | Yes | Stored | **not used for live/eval sync** |
| `events` | Yes | Stored in raw payload | **not merged into fixture_events for eval** |
| `odds` (premium) | Yes | SportmonksPredictionAgent (gated) | raw odds unless promotion passes |
| `predictions` (premium) | Yes | Benchmark / promotion adapter | not primary prediction |
| `xGFixture` (premium) | Yes | XGIntelligenceAgent → gated promotion | without promotion = shadow only |

**Consumption entry point:** `apply_sportmonks_consumption()` — gap-fills injuries, lineups, fixture statistics when API-Football missing; attaches odds/xG supplemental blocks.

---

## 4. Roadmap

### Phase 46B — Historical Recovery

**Goal:** Unify recoverable predictions into `worldcup_stored_predictions` without corrupting public metrics.

| Step | Action | Risk |
|------|--------|------|
| B1 | Read-only diff report: cache fixture IDs ⊖ stored fixture IDs | None |
| B2 | Quality-guarded import via `WorldcupPredictionStore.upsert` with `source=legacy_import` | Low if quarantine rules apply |
| B3 | Legacy SQLite reconstruct (5 fixtures) → admin inventory only first | Medium |
| B4 | JSONL import as summary-only — **do not** count as public eval until FT + WC eval | Medium |
| B5 | Deduplicate by `fixture_id`; preserve earliest `predicted_at` | Low |
| B6 | Re-run quarantine pass; rebuild `worldcup_accuracy_summary` | Required |

**Expected yield (production):** up to **~27–35** additional full payloads from cache; **5** legacy reconstructs; **~38** partial JSONL summaries.

**Out of scope for 46B:** shadow JSONL (28k local lines), verification logs, user-private PG history.

---

### Phase 46C — Advanced Market Evaluation

**Goal:** Evaluate HT, Correct Score, First Goal, Goal Minute, Goalscorer in WC pipeline when outcome data exists.

| Step | Action | Depends on |
|------|--------|------------|
| C1 | Extend `FixtureOutcomeResolver` with HT score, first goal team, scorer list | Persist events on result refresh |
| C2 | Extend `result_refresh.py` to fetch/store `fixtures/events` for finished stored fixtures | API quota |
| C3 | Port `_eval_ht_result`, `_eval_first_team_to_score` from `accuracy_optimization.py` → `pick_evaluator.py` | C1 |
| C4 | Add `_eval_correct_score` using `detailed_markets.correct_scores` + `final_score` | — |
| C5 | Add `_eval_goalscorer` with fuzzy name match (reuse verification agent logic) | C2 |
| C6 | Add `_eval_goal_minute` band vs event minute | C2; define band rules |
| C7 | New DB columns or `detail_json.markets` keys + `accuracy_summary` blocks | Migration |
| C8 | Expose in Performance Center only when n≥20 per market (45B trust rules) | — |

**Reuse target:** `worldcup_predictor/verification/auto_verification_agent.py` (halftime, scoreline, first goal, scorer evaluators already implemented).

---

### Phase 46D — Full Provider Utilization

**Goal:** Use fetched provider data in scoring, evaluation, and result sync — not only enrichment metadata.

| Step | Provider | Action |
|------|----------|--------|
| D1 | API-Football | Persist `fixtures/events` on result refresh → eval store |
| D2 | API-Football | Populate `halftime_score` on `fixture_results` from fixture payload |
| D3 | API-Football | Wire `OddsMovementAgent` signals into WDE audit (not override) |
| D4 | Sportmonks | Merge `events` + `scores` into unified outcome resolver |
| D5 | Sportmonks | Use `state` for cross-check against API-Football status in refresh |
| D6 | Both | Provider utilization dashboard in admin (fields fetched vs consumed) |
| D7 | Quota | Batch refresh / shared event cache per fixture to limit API calls |

---

## 5. Decision gates before implementation

| Gate | Criterion |
|------|-----------|
| **46B start** | Dry-run import report approved; backup taken; quarantine rules tested |
| **46C start** | Event persistence (C2) complete; at least 1 finished WC fixture with stored prediction |
| **46D start** | 46C outcome store stable; quota budget documented |
| **Public metrics** | No market shown until n≥20 settled real (non-quarantined) evaluations |

---

## 6. Key file references

| Area | Path |
|------|------|
| WC evaluator | `worldcup_predictor/automation/worldcup_background/pick_evaluator.py` |
| Legacy verification eval | `worldcup_predictor/verification/auto_verification_agent.py` |
| HT/FG helpers (unused in WC eval) | `worldcup_predictor/admin/accuracy_optimization.py` |
| Global archive | `worldcup_predictor/automation/worldcup_background/prediction_store.py` |
| Cache payloads | `worldcup_predictor/quota/prediction_cache.py` |
| JSONL history | `worldcup_predictor/accuracy/history_store.py` |
| API-Football client | `worldcup_predictor/clients/api_football.py` |
| Sportmonks includes | `worldcup_predictor/providers/sportmonks_enrichment.py` |
| Sportmonks consumption | `worldcup_predictor/providers/sportmonks_consumption.py` |
| Result refresh | `worldcup_predictor/automation/worldcup_background/result_refresh.py` |

---

**Phase 46A complete.** No import, deploy, or database modifications were performed.
