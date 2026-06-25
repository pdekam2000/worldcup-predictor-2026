# PHASE API-J — Historical xG Availability + UEFA EGIE Scale Validation

**Mode:** Audit → Validate → Expand Sample → Re-Backtest → Report  
**Production deploy:** NO  

---

## Executive Answer

**Can Sportmonks historical UEFA data materially improve EGIE?**

**Partially — with strong limits.**

| Signal | Verdict | Evidence |
|--------|---------|----------|
| **xG** | Limited | Live probe confirmed `type_id=5304` on **Europa League 2024/25** (fixture 19135812). After sample expansion, **3.64%** (8/220) fixtures parse non-null xG. Champions League / Conference League samples and all pre-2024 cache rows lack true xG. **Strategy B does not diverge from A** (45.8% vs 45.8% FG on published picks). |
| **Predictions** | Moderate on recent seasons | Expanded dataset: **29.55%** fixtures have non-empty `predictions[]` on finished 2024/25 CL probes. Legacy cache (105 fixtures) had 0%. Parser captures some values but types vary (O/U, not always 1X2). |
| **Odds** | Yes | **47.73%** coverage; Strategy D/E/F show **+28.7pp** FG lift vs A — driven by odds enrichment shifting picks off `"none"`, not xG. |
| **Events** | Gap remains | **34 fixtures** still have scores but empty events (2005-era EL); targeted re-ingest recovered **0/20**. |

**Bottom line:** Sportmonks can support EGIE enrichment on **recent UEFA seasons** for odds and (selectively) xG/predictions, but the **current mixed historical sample is not xG-rich enough** for Strategy B promotion. Build a **season-filtered holdout** (EL/CL 2024/25) before any production decision.

---

## STEP 1 — Historical xG Availability

Artifact: `artifacts/historical_xg_availability_audit.json`

- **xg_only_recent_seasons:** True for Europa League 2024/25 (live `type_id=5304`); false for CL/ECL probes and legacy cache
- **xg_only_completed_fixtures:** Probed finished state_id in {5,7,8}
- **xg_season_cutoff:** True xG on EL 2024/25; absent on CL/ECL samples and all cached pre-2024 seasons
- **alternate_endpoint:** Same `/fixtures/{id}` with `xGFixture.type` include; no separate historical xG endpoint found
- **parser_misses_lowercase_key:** Fixed in API-J — `parse_uefa_xg` reads lowercase `xgfixture` type_id 5304
- **post_expansion_xg_coverage:** 3.64% (8/220 fixtures)

## STEP 2 — Historical Predictions Availability

Artifact: `artifacts/historical_predictions_availability_audit.json`

- **historical_available_on_finished:** True on 2024/25 CL probes (29 prediction rows per fixture)
- **pre_match_only:** False — predictions persist on finished recent fixtures in API
- **expires_after_kickoff:** False for 2024/25 sample; legacy 2005–2014 cache had empty arrays
- **post_expansion_coverage:** 29.55% (65/220 fixtures)
- **parser_note:** `parse_uefa_predictions` extracts 1X2 when present; many rows are O/U or market-specific types

## STEP 3 — Pending Fixture Root Causes

Artifact: `artifacts/uefa_pending_fixture_root_causes.json`

| Cause | Count |
|-------|-------|
| baseline_predicted_none | 57 |
| missing_events | 28 |
| no_goal_scored | 27 |
| resolved | 8 |

**After re-ingest:**
- baseline_predicted_none: 109
- no_goal_scored: 52
- missing_events: 34
- resolved: 24
- incomplete_events: 1

## STEP 4 — Targeted Re-Ingest

- API calls: 20
- Events recovered: 0
- xG recovered: 0
- Unchanged: 20

## STEP 5 — Sample Size Growth

Artifact: `artifacts/before_vs_after_sample_size.json`
- Mapping fixtures: 120 → 220 (+100)
- Provider coverage: `{"xg": 3.64, "pressure": 21.82, "odds": 47.73, "predictions": 29.55, "lineups": 65.91, "events": 60.91, "statistics": 52.73}`

## STEP 6 — Dataset Rebuild

- Survival dataset: `C:\Users\kaman\Desktop\Footbal\data\egie\uefa_club\uefa_survival_dataset.parquet`
- Validations: `validate_egie_uefa_club_dataset.py`, `validate_uefa_event_team_mapping.py`

## STEP 7 — A–F Backtest Comparison


| Strategy | FG Team | Pending | Goal Range | Soft Minute | Paid Cov |
|----------|---------|---------|------------|-------------|----------|
| A | 45.8% | 110 | 23.1% | 28.4% | 0 |
| B | 45.8% | 75 | 23.1% | 28.4% | 8 |
| C | 46.4% | 78 | 23.1% | 28.4% | 43 |
| D | 74.5% | 28 | 23.1% | 28.4% | 98 |
| E | 74.5% | 28 | 23.1% | 28.4% | 106 |
| F | 74.5% | 28 | 23.1% | 28.4% | 135 |

**vs API-I baseline (Strategy A):**

| Metric | API-I | API-J |
|--------|-------|-------|
| Mapping fixtures | 120 | 220 (+100) |
| Backtest eligible | 93 | 168 |
| FG pending (A) | 57 | 110 |
| FG winrate (A, non-pending) | 50.0% | 45.8% |
| FG resolved (validation) | 73.3% | **81.6%** |

> **Strategy B (xG):** 45.8% FG, **8 fixtures** with xG — **does not materially improve vs A**. Do not treat B≈A as proof that xG is useless; xG sample is too small (3.64% coverage).

> **Strategy D/E/F (odds):** 74.5% FG — lift is from odds enrichment reducing `"none"` picks, not from xG or predictions.

## STEP 8 — Feature Impact Ranking

Artifact: `artifacts/uefa_feature_impact_ranking.json`

| Feature | Tier | FG Δ vs A | Coverage |
|---------|------|-----------|----------|
| odds | S | +28.7pp | 98 |
| xg_pressure_odds | S | +28.7pp | 106 |
| full_provider | S | +28.7pp | 135 |
| pressure | B | +0.6pp | 43 |
| xg | B | -0.1pp | 8 |

## Quota Usage

- Estimated total API calls (Phase API-J): **~143**

## Recommendation (Phase API-K)

1. **Build xG-rich UEFA holdout** from Europa League 2024/25+ fixtures where `type_id=5304` is confirmed.
2. **Re-ingest event-missing fixtures** only if Sportmonks returns events (2005-era EL may be permanently empty).
3. **Capture predictions pre-kickoff** — finished payloads retain empty `predictions[]`.
4. **Do not promote** Strategy B–F until xG coverage exceeds 30% on evaluable FG fixtures.

---

**STOP — No deploy. No production changes.**
