# PHASE 54J — Lineup & Player Feature Store Foundation

**Date:** 2026-06-24  
**Mode:** Feature Store Architecture → Historical Import → Validation → Report  
**Status:** Complete — validation **17/17 PASS** (after report)  
**API calls:** 0 (cache-first)

---

## Executive summary

Built a reusable **lineup / player feature store** (`worldcup_predictor/feature_store/player_store/`) with PostgreSQL tables, cache-first historical import, rolling player features, and lineup context. Imported **69,503 player-match rows** across **1,605 fixtures** and **10,262 unique players** from Sportmonks cache (UEFA + WC targets).

### Final recommendation: **`BUILD_GOALSCORER_SHADOW_ENGINE`**

Rolling features and lineup eligibility are sufficient to begin a shadow goalscorer engine (no production integration). Parallel track: **`BUILD_LINEUP_STRENGTH_ENGINE`** for team-level attack signals.

---

## Architecture

| Module | Role |
|--------|------|
| `models.py` | `PlayerMatchStatRecord`, `PlayerRollingFeatureRecord`, `PlayerIngestResult` |
| `normalizers.py` | Extract lineups → per-player match stats + lineup context |
| `aggregations.py` | Point-in-time rolling features (goals_last_N, xg_per_90, form) |
| `repository.py` | PostgreSQL upsert, manifest, coverage audit |
| `player_feature_store.py` | Cache backfill orchestrator |

### Database (migration `013_player_feature_store`)

| Table | Purpose |
|-------|---------|
| `fs_player_match_stats` | Per-player per-fixture stats |
| `fs_player_rolling_features` | Rolling + lineup features at fixture time |
| `fs_player_ingest_manifest` | Resumable ingest tracking |

---

## Coverage audit

| Metric | Value |
|--------|-------|
| **Players imported (unique)** | **10,262** |
| **Player-match rows** | 69,503 |
| **Fixtures imported** | 1,605 |
| **Fixtures with lineups (cache)** | 1,605 / 1,689 processed (84 empty) |
| **Starter rows** | 34,991 (50.3%) |
| **Minutes > 0** | 48,725 (70.1%) |
| **xG rows** | 15,901 (22.9%)* |
| **Lineup available (rolling)** | 99.6% |
| **Formation coverage** | 6.7% (UEFA odds-rich ingests) |
| **Rolling signal rows** | 47,558 (68.4%) |

\*xG from `xglineup` (lowercase) in xG-licensed cache; parser fixed during 54J.

### By league

| League | Fixtures | Players | xG rows |
|--------|----------|---------|---------|
| Champions League (2) | 555 | 3,903 | partial |
| Europa League (5) | 539 | 3,791 | partial |
| Conference (2286) | 464 | 5,119 | partial |
| World Cup (732) | 47 | 1,244 | partial |

### By season (top)

| Season | Fixtures | Players |
|--------|----------|---------|
| 25581 | 409 | 4,130 |
| 25580 | 281 | 2,248 |
| 25582 | 271 | 2,153 |
| 23620 | 267 | 2,107 |

---

## Rolling features (Part D)

Stored per player per fixture (point-in-time, prior matches only):

- `goals_last_3`, `goals_last_5`, `goals_last_10`
- `assists_last_5`, `minutes_last_5`, `starts_last_5`
- `shots_last_5`, `shots_on_target_last_5`
- `xg_last_5`, `xg_last_10`
- `goals_per_90`, `xg_per_90`
- `starter_probability`, `recent_form_score`

**Rolling coverage:** 71.3% of rolling rows have non-zero history signal (`goals_last_5` or `minutes_last_5`).

---

## Lineup features (Part E)

Stored on `fs_player_rolling_features`:

| Field | Coverage |
|-------|----------|
| `starting_xi_json` | 99.6% fixtures |
| `bench_json` | 99.6% |
| `formation` | 6.7% |
| `goalkeeper_player_id` | high where XI present |
| `captain_player_id` | partial |
| `lineup_available` | 99.6% |
| `lineup_quality_score` | 0.5–1.0 heuristic |

---

## Goalscorer readiness matrix (Part G)

| Feature | Coverage | Quality | Goalscorer Value |
|---------|----------|---------|------------------|
| goals_last_5 | 71.3% | high | high |
| goals_per_90 | 71.3% | high | high |
| xg_per_90 | 22.9% | medium | high |
| starter_probability | 50.3% | high | high |
| lineup_status | 99.6% | high | high |
| player_rating | partial | medium | medium |
| shots_on_target | partial | medium | medium |
| recent_form_score | 71.3% | medium | high |

---

## Report answers

### 1. How many players imported?

**10,262 unique players** (69,503 player-match stat rows).

### 2. How many fixtures imported?

**1,605 fixtures** with lineups (1,689 cache files scanned; 84 had no lineup data).

### 3. Rolling feature coverage?

**69,503 rolling rows**; **71.3%** have meaningful prior-match signal.

### 4. xG coverage?

**15,901 player rows (22.9%)** with xG from `xglineup`. Fixture-level xG availability ~63% on xG cache (per 54I); not every player row carries xG in payload.

### 5. Lineup coverage?

**99.6%** rolling rows marked `lineup_available`; **50.3%** starter rows in match stats.

### 6. Goalscorer readiness?

**Ready for shadow engine** — goals_per_90, starter_probability, lineup_status, and recent_form_score are populated at scale. xG and rating are supplementary.

### 7. Best player features?

1. **goals_per_90** + **goals_last_5** — primary anytime scorer signal  
2. **starter_probability** — eligibility filter  
3. **lineup_status** — pre-match gate  
4. **xg_per_90** — secondary (22.9% coverage, growing with xG cache)  
5. **recent_form_score** — composite form index  

### 8. What should be built next?

**Phase 54K proposal (not executed):**

1. **`BUILD_GOALSCORER_SHADOW_ENGINE`** — odds name-mapping + rolling features → shadow First/Anytime scorer probabilities  
2. **`GOALSCORER_ODDS_RESEARCH_ONLY`** (from 54I) — calibrate against Goalscorers market  
3. Re-run rolling after full chronological ingest (second pass) for richer history chains  
4. WC lineups re-ingest with deep includes if WC coverage must expand beyond 47 fixtures  

---

## Validation

**17/17 PASS** (`artifacts/phase54j_player_feature_store/validation.json`)

- player stats imported  
- rolling features built  
- lineups imported  
- coverage audit generated  
- no duplicates  
- no production / WDE / SaaS / deploy changes  
- no token leaked  

---

## Artifacts & scripts

| Path | Description |
|------|-------------|
| `artifacts/phase54j_player_feature_store/backfill_result.json` | Full import summary |
| `artifacts/phase54j_player_feature_store/coverage_audit.json` | DB coverage |
| `artifacts/phase54j_player_feature_store/goalscorer_readiness.json` | Readiness matrix |
| `scripts/phase54j_player_feature_store_backfill.py` | Cache backfill CLI |
| `scripts/validate_phase54j_player_feature_store.py` | Validation gate |
| `alembic/versions/013_player_feature_store.py` | Migration |

---

**Phase 54J complete. No deploy. No live prediction changes. No modeling started.**
