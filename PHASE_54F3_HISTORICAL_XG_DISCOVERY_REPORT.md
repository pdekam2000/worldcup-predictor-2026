# PHASE 54F-3 — Sportmonks Historical xG Discovery Report

**Date:** 2026-06-23  
**Mode:** Discovery → Coverage Audit → Validation → Report  
**Status:** COMPLETE (audit only — no production, WDE, SaaS, or deploy changes)

**Authoritative run:** Production server (`91.107.188.229`) with valid Sportmonks ALL-IN token — **207 live API calls**, responses cached under `artifacts/phase54f3_xg_discovery/raw/`.

---

## Executive Summary

We answered the core question: **Sportmonks contains substantial xG for modern competitions; our integration was discovering only a tiny fraction due to parser/configuration bugs.**

| Finding | Result |
|---------|--------|
| Sportmonks historical xG exists? | **YES (recent seasons)** / **NO (pre~2024 WC, older CL)** |
| Our importer missing data? | **YES** — primary root cause |
| Corrected sample xG rate | **17.1%** across all probed seasons (105 fixtures) |
| Recent-season sample rate | **60–80%** (WC 2026, CL/EL 2024–2026) |
| Estimated overall coverage (3,784 finished fixtures audited) | **~19.5%** (736 fixtures with xG extrapolated) |
| Maximum realistic coverage (modern seasons, fixed importer) | **60–80%** per league-season |

**Final recommendation:** `FIX_IMPORTER` + `EXPAND_XG_IMPORT`  
**Not ready for:** Phase 54G Pressure Index or EGIE promotion until importer fix is deployed and recent-season backfill completes.

---

## 1. How much historical xG do we really have?

### Subscription footprint (discovery run)

| League | ID | Seasons in API | Seasons sampled | Finished fixtures (sampled pages) |
|--------|-----|----------------|-----------------|-----------------------------------|
| World Cup | 732 | 6 | 6 | 369 |
| Champions League | 2 | many | 6 | 1,324 |
| Europa League | 5 | many | 6 | 1,500 |
| Europa Conference | 2286 | 6 | 6 | 1,250 |
| European Championship | 1326 | **0** (empty) | 0 | — |
| Premier League | 8 | **0** (empty) | 0 | — |
| Nations League | 1538 | discovered | partial | — |
| Euro Qualification | 1325 | discovered | partial | — |

**Total finished fixtures counted:** 3,784 (across 24 league-season rows)

### xG availability (after parser correction)

| Metric | Value |
|--------|-------|
| Fixtures deep-probed | 105 |
| Probes with team xG | 18 (17.1%) |
| Extrapolated fixtures with xG | 736 |
| Overall estimated coverage | **19.45%** |

### Historical timeline (sample coverage %)

| League | Season | Sample xG % | Notes |
|--------|--------|-------------|-------|
| World Cup | 2026 | **80%** | Strong — aligns with Phase 54D |
| World Cup | 2022–2006 | **0%** | No xG in Sportmonks for sampled fixtures |
| Champions League | 2024/2025, 2025/2026 | **60%** | Usable |
| Champions League | 2021/2022–2023/2024 | **0%** | Pre-xG era in API |
| Europa League | 2024/2025, 2025/2026 | **60%** | Usable |
| Conference League | 2025/2026 | **40%** | Partial |

**Earliest season with xG (in sample):** CL/EL 2024/2025, WC 2026  
**Latest:** 2025/2026 competitions

---

## 2. Which leagues have the best xG coverage?

**Best (60–80% sample rate):**

1. World Cup 2026 (732) — **80%**
2. Champions League 2024–2026 — **60%**
3. Europa League 2024–2026 — **60%**
4. Europa Conference League 2025/2026 — **40%**

**No xG in sample:** WC 2006–2022, older CL seasons (pre-2024/25), Euro 1326 (no season metadata returned), Premier League 8 (no season metadata returned).

---

## 3. Which seasons have the best coverage?

Top seasons by corrected sample coverage:

| Rank | League | Season | Sample % | Est. fixtures with xG |
|------|--------|--------|----------|------------------------|
| 1 | World Cup | 2026 | 80% | 36 / 45 |
| 2 | Champions League | 2025/2026 | 60% | 150 / 250 |
| 3 | Champions League | 2024/2025 | 60% | 150 / 250 |
| 4 | Europa League | 2025/2026 | 60% | 150 / 250 |
| 5 | Europa League | 2024/2025 | 60% | 150 / 250 |
| 6 | Conference League | 2025/2026 | 40% | 100 / 250 |

---

## 4. Is our current importer missing data?

**YES — conclusively.**

### Evidence

1. **Raw API payloads** contain `xgfixture[]` arrays with `type_id: 5304` (Expected Goals).
2. **Pre-fix parser** (`_expected_rows_from_fixture`) only read uppercase `xGFixture`, missing lowercase `xgfixture` list format → `expected_row_count: 0` on all 105 probes.
3. **After fix:** WC fixture `19609127` shows `has_team_xg: true`, `expected_row_count: 108`, full metric family (xg, xgot, npxg, xga, …).
4. **UEFA cache (local):** 8/80 fixtures had true team xG when parsed correctly; 72 had no xG in source (not importer fault).
5. **Phase 54F-2** false xGoT from Shots On Target — separate bug, already repaired.

**Importer was the bottleneck, not Sportmonks absence** for modern fixtures.

---

## 5. Is Sportmonks xG worth the subscription cost?

| Use case | Verdict |
|----------|---------|
| World Cup 2026 modeling | **YES** — 80% xG coverage in sample |
| Modern UEFA club (2024+) | **YES** — ~60% coverage |
| Deep historical backfill (WC 2018, old CL) | **NO** — 0% in API sample |
| Premier League / Euro via current league IDs | **UNCLEAR** — API returned empty `seasons[]` (subscription scope or ID issue) |
| Pressure / Odds / Predictions (54D) | **YES** — already validated |

**Overall:** ALL-IN subscription is justified for **forward-looking WC + modern UEFA xG**. Not justified if the primary goal is decade-long historical xG across all competitions.

---

## 6. Maximum realistic xG coverage we can reach

| Scope | Realistic ceiling |
|-------|-------------------|
| WC 2026 season | **70–90%** (after full backfill + parser fix) |
| CL / EL 2024/2025–2025/2026 | **55–70%** |
| Conference League 2025/2026 | **35–50%** |
| All finished fixtures 2006–2026 | **~20–25%** (dominated by pre-xG seasons) |
| EGIE UEFA cache (80 files) | **~10%** (only 8 cache files contain type 5304 xG) |

To exceed **30% rolling xG for EGIE backtest**, target **WC 732 + CL/EL 2024+ live backfill**, not legacy cache alone.

---

## 7. Endpoint Audit (Part D)

Tested on fixture `19609127` with four include strategies:

| Variant | xGFixture block | Team xG (corrected) | Notes |
|---------|-----------------|---------------------|-------|
| `xGFixture.type` includes | Yes | **Yes** | Primary path — works when parser reads `xgfixture` |
| `statistics.type` only | No | No | No xG without xGFixture |
| `deep_combo` | Yes | **Yes** | Full audit include set |
| Fallback includes | No | No | Statistics only insufficient for xG |

**Filters used:** `fixtureSeasons:{season_id}` — works  
**Pagination:** `per_page=50`, `has_more` — works; capped at 5 pages/season in discovery  
**Correct endpoint:** `GET /fixtures/{id}?include=...xGFixture.type...` — **confirmed**

---

## 8. API Capability Audit (Part F)

| Capability | Verdict |
|------------|---------|
| Historical xG retrievable | **PARTIAL** (recent seasons YES, old seasons NO) |
| League-wide xG | **PARTIAL** (WC + UEFA yes; PL/Euro metadata gap) |
| Season-wide xG | **YES** |
| Fixture-level xG | **YES** (with correct includes + parser) |
| Player xG | **PARTIAL** (lineup xG less common in sample; team xG strong) |

---

## 9. Root Cause Analysis (Part G)

| Code | Cause | Verdict |
|------|-------|---------|
| **A** | Sportmonks limited historical xG | **TRUE** for WC ≤2022, CL pre-2024 |
| **B** | Importer misses available xG | **TRUE** — lowercase `xgfixture`, metric misclassification |
| **C** | Wrong season mapping | **PARTIAL** — audited oldest 6 seasons first for some leagues; recent seasons have xG |
| **D** | Wrong endpoint | **FALSE** — `/fixtures/{id}` is correct |
| **E** | Wrong include / parser config | **TRUE** — parser did not read `xgfixture[]` list |
| **F** | Pagination issue | **FALSE** — pagination works; budget capped pages |
| **G** | Combination | **TRUE** — A + B + E together explain all observations |

**Primary:** **B + E** (fixable immediately)  
**Secondary:** **A** (provider data boundary for old seasons)

---

## 10. XG_COVERAGE_MATRIX

Full matrix: `artifacts/phase54f3_xg_discovery/XG_COVERAGE_MATRIX.json`

Sample rows (corrected):

| league | season | fixtures | fixtures_with_xg | coverage_pct | team_xg | xgot |
|--------|--------|----------|------------------|--------------|---------|------|
| World Cup | 2026 | 45 | 36 | 80.0 | 4 | 4 |
| Champions League | 2025/2026 | 250 | 150 | 60.0 | 3 | 3 |
| Europa League | 2024/2025 | 250 | 150 | 60.0 | 3 | 3 |
| Europa Conference League | 2025/2026 | 250 | 100 | 40.0 | 2 | 2 |
| World Cup | 2022 | 64 | 0 | 0.0 | 0 | 0 |

---

## 11. Validation

`scripts/validate_phase54f3_xg_discovery.py` — run after parser replay.

| Check | Status |
|-------|--------|
| Target leagues audited | PASS |
| Seasons audited | PASS (24 rows) |
| Coverage matrix | PASS |
| Endpoint audit | PASS |
| Root cause analysis | PASS |
| No production/WDE/SaaS changes | PASS |
| No deploy | PASS |
| No token leaked | PASS |

---

## 12. What should happen next?

### Recommendation: `FIX_IMPORTER` + `EXPAND_XG_IMPORT`

1. **Deploy parser fix** (`sportmonks_xg_extraction.py` — read `xgfixture` lowercase list) — done locally, deploy to server.
2. **Re-run Phase 54E backfill** for leagues **732, 2, 5, 2286** — seasons **2024/2025+** only (`--metric-key xg`, `--max-calls 200`).
3. **Re-run Phase 54F** EGIE xG backtest after rolling coverage ≥30% on target fixture set.
4. **Clarify with Sportmonks** why leagues **1326** and **8** return empty `seasons[]` (`NEED_PROVIDER_CLARIFICATION` for PL/Euro).
5. **Do NOT** start Phase 54G Pressure Index until xG import path is fixed and backfill confirms ≥30% rolling coverage.

### Not recommended now

| Option | Why |
|--------|-----|
| READY_FOR_54G | xG path not production-validated |
| STOP_XG_WORK | Subscription has clear value for WC/modern UEFA |
| Rely on UEFA cache only | 10% true xG — insufficient |

---

## Deliverables

| Item | Path |
|------|------|
| Discovery engine | `worldcup_predictor/feature_store/xg_discovery/` |
| Main script | `scripts/phase54f3_sportmonks_xg_discovery.py` |
| Parser replay | `scripts/phase54f3_replay_probe_from_cache.py` |
| Validation | `scripts/validate_phase54f3_xg_discovery.py` |
| Artifacts | `artifacts/phase54f3_xg_discovery/` |
| Coverage matrix | `artifacts/phase54f3_xg_discovery/XG_COVERAGE_MATRIX.json` |

---

*Phase 54F-3 complete. STOP — no deploy, no live prediction changes.*
