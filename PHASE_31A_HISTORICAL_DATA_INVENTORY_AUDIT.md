# Phase 31A — Historical Data Inventory Audit

**Status:** Audit complete — **no code changes, no deploy.**

**Goal:** Identify exactly which historical data sources are available for a reliable backtest before implementing Phase 31.

**Audited environments:** Local workspace (`C:\Users\kaman\Desktop\Footbal`) and production server (`91.107.188.229` / `footballpredictor.it.com`), read-only inventory only.

---

## Executive Summary

The system has **strong historical match coverage** (1,616 finished fixtures in SQLite) but **very weak stored prediction coverage** for backtesting production picks (17 SQLite predictions, 27–105 JSONL records, 16 user PG history rows, all Phase 29 PG results still **pending**).

| Dimension | Finding |
|-----------|---------|
| **Best backtest path** | **Backtest B — Historical API replay** on SQLite fixtures + results (~1,616 finished matches) |
| **Production prediction history backtest** | **Not viable yet** — sample too small, no finished SaaS outcomes, no stored Phase 30C payloads |
| **Ranked pick reconstruction (30C)** | **PARTIAL** — can rebuild basic picks from core fields; full safe/value/aggressive ranking requires `extended_markets_json` + specialist context, which is missing on all non–no-bet historical rows |
| **Sportmonks historical depth** | **Minimal** (1 enrichment row) — not usable for backtest today |
| **Overall data volume (finished matches)** | **Large** (1,616) |
| **Overall data volume (scored predictions)** | **Small** (<100 fixtures with outcome-linked evaluations) |

---

## 1. Data Source Inventory

### 1.1 Prediction History (JSONL)

**Path:** `data/predictions/prediction_history.jsonl`  
**Store:** `PredictionHistoryStore` (`worldcup_predictor/accuracy/history_store.py`)

| Metric | Local | Production |
|--------|-------|------------|
| Total records | **105** | **27** |
| Unique fixtures | 26 | ~26 |
| Date range | **2021-08-13 → 2026-06-18** | Same band (subset) |
| With `extended_markets_json` | **16 (15%)** | ~6 |
| `no_bet_flag=true` rate | **62%** | Similar |
| Avg confidence | **55.2%** | ~52% |
| Finished outcome join (verification) | **16 fixtures** | Same |

**Fields stored per record:**

- Core: `predicted_1x2`, `predicted_over_under_2_5`, `predicted_halftime_goals`, `predicted_first_goal_team`, `predicted_scoreline`, `predicted_first_goal_scorer`
- Quality: `confidence_score`, `data_quality_score`, `no_bet_flag`, `risk_level`
- Meta: `prediction_id`, `prediction_version`, `lineups_available`, `is_preliminary`, `source`
- Extended (optional): `extended_markets_json` (full FT 1X2, O/U, BTTS, HT, correct scores, goalscorer when present)

**Not stored:** `recommended_bets`, `safe_pick`, `value_pick`, `aggressive_pick`, `market_ranking`, `specialist_summary`, full API payload.

**Payload quality:** Adequate for **legacy 1X2 / O/U / HT** evaluation. **Insufficient** for Phase 30C ranked-pick backtest without reconstruction + extended markets (only 15% of rows; **0 rows** have extended markets AND `no_bet_flag=false` locally).

---

### 1.2 SQLite Database (`data/football_intelligence.db`)

**Role:** Primary intelligence + fixture + result store (PG is SaaS-only per architecture notes).

| Table | Rows (local/prod) | Purpose |
|-------|-------------------|---------|
| `fixtures` | **1,684** | Imported fixtures |
| `fixture_results` | **1,616** | Finished scores, HT, O/U outcome |
| `predictions` | **17** | Structured prediction runs |
| `prediction_markets` | **85** | Per-market picks (1x2, ou, ht, scoreline, first_goal) |
| `verification_results` | **70** | Market-level verify rows |
| `fixture_enrichment` | **1,612** | Cached enrichment blobs |
| `sportmonks_fixture_enrichment` | **1** | Sportmonks raw enrichment |
| `odds_snapshots` | **961** | Historical odds snapshots |
| `xg_snapshots` | **0** | xG snapshots (empty) |
| `api_response_cache` | **1,045** | API-Football response cache |
| `league_import_runs` | **43** | Import audit log |

**Fixture date range:** `2021-08-13` → `2026-06-28`  
**Finished (FT/AET/PEN):** **1,616**

**Top imported leagues (by fixture count):**

| League ID | Season | Matches |
|-----------|--------|---------|
| 39 (Premier League) | 2023 | 380 |
| 78 (Bundesliga) | 2021–2024 | 308 each |
| Unassigned (`NULL`) | — | 72 |

**Predictions ↔ results overlap:** Only **4** SQLite predictions join to finished `fixture_results`. All 17 stored predictions have `no_bet_flag=1`.

**Evaluation tables:** `verification_results` covers markets: 1x2 (16), O/U (16), HT bucket (16), first goal team (16), scoreline (4), first goal scorer (2).

---

### 1.3 PostgreSQL (SaaS)

**Role:** Users, subscriptions, **user prediction history** (Phase 29 UI).

| Table | Rows (production) |
|-------|-------------------|
| `users` | 8 |
| `user_prediction_history` | **16** |
| Result breakdown | **16 pending**, 0 correct/wrong |

**Date range:** 2026-06-18 → 2026-06-20 (view timestamps)

**Stored per row:** `fixture_id`, teams, `prediction_1x2`, `confidence`, `result` (enum), `match_date`, `league` — **no** O/U, BTTS, ranked picks, or full payload.

**Backtest value today:** Low — no settled outcomes yet; UI evaluation depends on live fixture results (Phase 29 computes on read).

---

### 1.4 API-Football Imported History

| Source | Volume | Notes |
|--------|--------|-------|
| SQLite `fixtures` + `fixture_results` | **1,616 finished** | Primary imported history |
| `league_import_runs` | 43 runs | Mix of success/fail; recent WC 2025 seasons show `failed` with 0 imports |
| `api_response_cache` | 1,045 entries | Raw cached API responses |
| `.cache/api_football` | **8,984 files / ~176 MB** (local); **232 files / ~25 MB** (prod) | Lineups, fixtures, odds fragments |
| Demo CSV | **12 rows** | `data/historical/worldcup_sample.csv` — illustrative WC 2022 only |

**Leagues with meaningful bulk import:** Premier League 2023, Bundesliga 2021–2024. World Cup 2026 fixtures exist in schedule layer but bulk historical import runs for competition 135 largely **failed**.

---

### 1.5 Sportmonks Imported History

| Metric | Value |
|--------|-------|
| `sportmonks_fixture_enrichment` rows | **1** |
| xG snapshots (SQLite) | **0** |
| Premium flags in schema | odds / predictions / xG availability columns exist but barely populated |
| Shadow JSONL (prod) | ~7,210 lines across promotion/shadow files — **not** production prediction archive |

**Verdict:** Sportmonks is wired for live enrichment but **not** built up as a historical backtest corpus.

---

### 1.6 Cache Folders

| Location | Local | Production |
|----------|-------|------------|
| `.cache/api_football/` | 8,984 files | 232 files |
| `.cache/predictions/` | 3 files | minimal |
| `data/shadow/*.jsonl` | many | ~7,210 total lines |
| `data/validation/real_world_validation.jsonl` | 32 rows | present |
| `data/verification/prediction_verification.jsonl` | 542 rows / **16 fixtures** | 542 rows |

**Prediction API cache** (`.cache/predictions/`): stores full API responses when populated, but **almost empty** — not a reliable historical archive post–Phase 30C.

---

## 2. Backtest Readiness Matrix

Scoring: average of five booleans (usable, finished results, prediction payload, confidence, market data) × 100%.

| Source | Usable | Finished results | Prediction payload | Confidence | Market data | **Readiness** |
|--------|--------|------------------|--------------------|------------|-------------|---------------|
| JSONL prediction history | Partial | Partial (16 fx) | Partial | Yes | Partial | **35%** |
| SQLite fixtures + results | **Yes** | **Yes** | No (replay) | On replay | Via enrichment | **75%** |
| SQLite `predictions` table | Partial | Partial (4 fx) | Partial | Yes | Partial | **20%** |
| PostgreSQL user history | No | No (all pending) | Minimal (1X2 only) | Partial | No | **15%** |
| Verification JSONL | Yes | Yes (16 fx) | Partial | No | Partial | **45%** |
| `real_world_validation.jsonl` | Partial | Yes (32 fx) | Partial (1X2) | Yes | No BTTS/O/U | **40%** |
| API-Football cache | Partial | Partial | Raw only | No | Partial | **55%** |
| Sportmonks enrichment | No | No | No | No | No | **5%** |
| Shadow replay JSONL | Partial | Varies | Shadow-only | Partial | Partial | **30%** |
| Demo WC CSV | Demo only | Yes (12) | N/A | No | Odds only | **25%** |

---

## 3. Data Volume Summary

| Category | Count | Tier |
|----------|-------|------|
| **Finished matches (SQLite)** | **1,616** | **Large** (1,000–10,000) |
| **Total fixtures (SQLite)** | 1,684 | Large |
| **Stored predictions (JSONL records)** | 105 local / 27 prod | Small (<100 unique fixtures) |
| **Predictions with verified outcomes** | **16 fixtures** | Small |
| **PostgreSQL user views** | 16 (all pending) | Small |
| **real_world_validation settled** | 32 | Small |
| **Earliest fixture data** | 2021-08-13 | — |
| **Latest fixture data** | 2026-06-28 | — |
| **Earliest prediction record** | 2021-08-13 (1 demo row) / bulk from 2026-06-11 | — |
| **Latest prediction record** | 2026-06-18 | — |

**Tier definitions applied:**

- Small: <100 matches — **scored prediction corpora**
- Medium: 100–1,000 — not met for predictions
- Large: 1,000–10,000 — **finished fixture results**
- Very Large: 10,000+ — not met

---

## 4. Recommended Backtest Strategies

### Backtest A — Production Prediction History

**Use:** JSONL + PG user history + verification JSONL + future forward capture.

| Attribute | Assessment |
|-----------|------------|
| Expected sample size | **16–32 fixtures** with evaluable outcomes today |
| Reliability | **Low** — tiny sample, heavy no-bet bias, no Phase 30C fields stored |
| Strengths | True production picks; verification already market-scored |
| Limitations | No BTTS/DC ranked pick history; PG all pending; 62% no-bet; no specialist_summary archive |

**Recommendation:** Use as **supplementary forward-validation** only until Phase 31 adds payload capture. **Not primary backtest.**

---

### Backtest B — Historical API Data Replay (Recommended Primary)

**Use:** SQLite `fixtures` + `fixture_results` + `fixture_enrichment` + `odds_snapshots`; re-run `PredictPipeline` / WDE in replay mode per fixture (pre-kickoff intelligence reconstruction via `HistoricalLoader` pattern or stored enrichment).

| Attribute | Assessment |
|-----------|------------|
| Expected sample size | **Up to 1,616 finished matches** (Large) |
| Reliability | **High** for model calibration; **Medium** for production-fidelity (replay ≠ exact live snapshot) |
| Strengths | Large N; HT + O/U + 1X2 outcomes; odds snapshots for 961 fixtures; enrichment for 1,612 |
| Limitations | Not identical to live production runs; Sportmonks/xG sparse; promotion modes may differ; API quota cost; WC 2026 import gaps |

**Recommendation:** **Primary Phase 31 backtest engine.**

---

## 5. Ranked Pick Reconstruction (Phase 30C)

Can historical data reproduce `safe_pick`, `value_pick`, `aggressive_pick`, and `recommended_bets` using today's `market_ranking_engine`?

| Output | Feasibility | Evidence |
|--------|-------------|----------|
| `recommended_bets` (1X2 + O/U basic) | **PARTIAL** | Rebuild `MatchPrediction` from JSONL core fields — works structurally |
| `recommended_bets` (Phase 30C ranked) | **PARTIAL** | Requires ranking engine + thresholds; most historical rows are no-bet |
| `safe_pick` / `value_pick` / `aggressive_pick` | **NO** (historical) / **PARTIAL** (replay) | Needs `extended_markets` + non–no-bet gate; **0 JSONL rows** with ext markets AND actionable |
| `market_ranking` full list | **PARTIAL** | Possible on replay; not stored historically |
| `specialist_summary` / odds consensus inputs | **NO** | Not archived in JSONL or PG history |

**Reconstruction test (local):**

- Records **with** `extended_markets_json` but `no_bet_flag=true` → ranking returns empty / No Bet (correct).
- Records **without** extended markets → ranking empty even if fields exist.
- **0 records** satisfy: `extended_markets_json` present AND `no_bet_flag=false` AND confidence ≥ 55.

**Verdict:** **PARTIAL overall**

- **YES** for replay-generated predictions (Backtest B) — full Phase 30C output at replay time.
- **NO** for faithful historical reconstruction of what users actually saw in ranked picks (payloads not stored).
- **PARTIAL** for legacy 1X2/O/U accuracy from JSONL + verification.

**Forward fix (Phase 31+, no implementation in 31A):** Persist `accuracy_tracking` + full API block on each prediction write (JSONL + optional PG JSONB).

---

## 6. Risks and Limitations

1. **Sample size mismatch** — 1,616 finished matches vs ~16 with scored production predictions.
2. **No-bet dominance** — 62%+ historical JSONL flagged no-bet; ranked pick evaluation skewed toward empty picks.
3. **Extended markets sparse** — Only 15% JSONL rows; blocks DC/BTTS/HT ranking replay from history alone.
4. **Phase 29 PG history** — All 16 rows pending; no closed-loop user winrate yet.
5. **Sportmonks / xG gap** — Cannot backtest promotion/xG paths historically at scale.
6. **Replay fidelity** — Backtest B re-runs today’s engine on past data; not byte-identical to original live prediction.
7. **League composition** — Bulk data is PL 2023 + Bundesliga; limited WC 2026 historical depth in SQLite.
8. **Demo data contamination** — 12-row WC 2022 CSV and demo fixture IDs (900001+) in validation JSONL — exclude from production metrics.
9. **Cache not durable archive** — Prediction cache nearly empty; cannot reconstruct Phase 30A/30C UI state from cache.

---

## 7. Recommended Phase 31 Execution Plan

### Phase 31B — Historical Replay Backtest (Primary)

1. Build replay runner over SQLite `fixture_results` (1,616 rows), ordered by kickoff.
2. Use stored `fixture_enrichment` where available; fallback to `HistoricalLoader`-style synthesis.
3. Capture at replay time: full `build_prediction_output()` including Phase 30C ranking.
4. Score vs `fixture_results`: 1X2, O/U 2.5, HT bucket, BTTS (from extended markets), DC (derived).
5. Report by league, confidence bucket, no-bet vs actionable.

**Expected N:** 500–1,616 depending on enrichment availability filter.

### Phase 31C — Forward Production Capture (Secondary)

1. Extend JSONL `PredictionHistoryRecord` / write-side hook to store `accuracy_tracking` + `recommended_bets` + `market_ranking` snapshot (append-only).
2. Optionally mirror to PG `user_prediction_history` as JSONB metadata (future).
3. After 4–8 weeks live WC play, re-run **Backtest A** with meaningful N.

**Expected N (3 months):** 100–500 if prediction volume increases.

### Phase 31D — Verification Consolidation

1. Unify `verification_results`, `prediction_verification.jsonl`, and Phase 29 evaluation into one backtest report schema.
2. Exclude demo fixture IDs (`900001–900012`) from headline metrics.

### Explicitly defer

- Sportmonks/xG historical backtest until enrichment rows > 100.
- PG-only backtest until `user_prediction_history.result` has settled rows.

---

## 8. Audit Conclusion

| Question | Answer |
|----------|--------|
| Is production prediction history enough for Phase 31? | **No** — too small, no ranked pick archive |
| Is SQLite fixture history enough? | **Yes** — 1,616 finished matches (Large tier) |
| Best data source for Phase 31 | **Backtest B — Historical replay on SQLite** |
| Ranked pick reconstruction | **PARTIAL** — replay yes, historical archive no |
| Blockers before Phase 31 implementation | None for Backtest B; define replay scope + exclusion rules |

**Audit status:** Complete. No code changes. No deploy. Awaiting approval for Phase 31B implementation.

---

## Appendix — Key Paths

| Asset | Path |
|-------|------|
| JSONL prediction history | `data/predictions/prediction_history.jsonl` |
| Verification outcomes | `data/verification/prediction_verification.jsonl` |
| Real-world validation | `data/validation/real_world_validation.jsonl` |
| SQLite DB | `data/football_intelligence.db` |
| Phase 30C ranking | `worldcup_predictor/api/market_ranking_engine.py` |
| Historical loader | `worldcup_predictor/backtesting/historical_loader.py` |
| Accuracy service | `worldcup_predictor/accuracy/service.py` |
