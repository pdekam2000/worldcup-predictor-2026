# PHASE A13A — PREDICTION COVERAGE + COMBO HOTFIX REPORT

**Date:** 2026-06-25  
**Final status:** `HOTFIX_DEPLOYED_OK` (UI/cache/routing fixes live)  
**Combo note:** Still empty — all cached WC predictions are `no_bet` (engine/data, not UI)  
**Validation:** 19/19 PASS (`scripts/validate_phase_a13a_prediction_coverage_combo_hotfix.py`)  
**Production:** https://footballpredictor.it.com

---

## Executive summary

Three user-reported issues were audited against production. **Draw bias** and **combo empty state** root causes were **UI/summary extraction bugs** (now fixed). **Zero-fixture leagues** are mostly **off-season / provider-empty** with one league (Premier League) showing fixtures but **0% prediction coverage**.

No changes to WDE, EGIE, scoring engine, ML models, calibration, or subscription logic.

---

## Root causes

| Issue | Root cause | Classification |
|-------|------------|----------------|
| Draw on many matches | `extract_prediction_summary` used `payload.prediction: "draw"` even when `no_bet: true` | **UI/cache extraction** — FIXED |
| Combo Tips empty | (1) Cross-fixture conflict filter blocked all accumulators; (2) All 18 WC predictions are `no_bet` with no `best_pick` | **(1) UI — FIXED**; **(2) engine/data — report only** |
| Leagues with no fixtures | 7/9 leagues: 0 upcoming (June off-season / UCL window); PL has 200 fixtures | **Provider/season** — explained in UI |

---

## Draw count before / after

| Metric | Before | After deploy |
|--------|--------|--------------|
| Visible Draw labels (WC sample) | **17 / 18** | **0 / 18** |
| `best_pick` with `no_bet: true` | Shown as Draw | **`null`** (hidden) |
| Card message | "1x2: Draw" | **"Prediction not generated yet"** |

All 17 Draw rows had `no_bet: true` and low confidence (15–40%) — placeholder `prediction` field, not real WDE picks.

---

## Combo candidates before / after

| Metric | Before | After |
|--------|--------|-------|
| Combo conflict scope | Global (blocked Home+Away across matches) | **Same-fixture only** |
| League correlation cap | 2 legs | **4 legs** |
| SAFE combo thresholds | 68% conf / 73 AI | **62% / 65** |
| Bettable legs (prod data) | 0 | **0** (all `no_bet`) |
| Empty state message | Generic | **Explains no_bet / filter rejection** |

Combo will populate automatically when stored predictions include bettable `best_available_pick` without `no_bet`.

---

## League coverage table

| Competition | Provider ID | Season | Upcoming | Predictions | Zero reason |
|-------------|-------------|--------|----------|-------------|-------------|
| premier_league | 39 | 2026 | 200 | 0 | — |
| world_cup_2026 | 1 | 2026 | 18 | 18 | — |
| bundesliga | 78 | 2026 | 0 | 0 | off season |
| la_liga | 140 | 2026 | 0 | 0 | off season |
| ligue_1 | 61 | 2026 | 0 | 0 | off season |
| serie_a | 135 | 2026 | 0 | 0 | off season |
| champions_league | 2 | 2026 | 0 | 0 | off season |
| conference_league | 848 | 2026 | 0 | 0 | off season |
| europa_league | 3 | 2026 | 0 | 0 | off season |

---

## Prediction coverage table

| Metric | Value |
|--------|-------|
| Total upcoming fixtures (all) | 218 |
| With cached prediction row | 18 |
| With visible `best_pick` (after fix) | 0 |
| `no_bet` summaries | 18 |
| WC coverage | 100% stored / 0% bettable |
| PL coverage | 0% |

---

## Files changed

### Backend (read/summary only)
| File | Change |
|------|--------|
| `worldcup_predictor/api/match_center_helpers.py` | Hide `no_bet` picks; `match_winner` fallback; status "Awaiting pick" |
| `worldcup_predictor/api/routes/competitions.py` | `zero_fixture_reason` + `provider_league_id` |

### Frontend
| File | Change |
|------|--------|
| `base44-d/src/lib/comboGenerator.js` | Same-fixture conflicts; A+ value; relaxed SAFE; odds est. label |
| `base44-d/src/pages/ComboTipsPage.jsx` | page_size 200→100 cap fix path; better empty states |
| `base44-d/src/components/match-center/EliteMatchCard.jsx` | "Prediction not generated yet" |
| `base44-d/src/components/match-center/LeagueSelector.jsx` | Zero-fixture reason hint |
| `base44-d/src/lib/predictionDetailProUtils.js` | Align no_bet + match_winner fallback |

### Tooling
| File | Role |
|------|------|
| `scripts/audit_phase_a13a_prediction_coverage.py` | Full coverage/draw/combo audit |
| `scripts/validate_phase_a13a_prediction_coverage_combo_hotfix.py` | 19-check validation |
| `data/validation/phase_a13a_audit_report.json` | Audit artifact |

---

## Validation

```
Phase A13A — 19/19 checks PASS
  no_bet_clears_best_pick, match_winner_fallback, combo_same_fixture_conflict
  frontend_build, smoke_matches, smoke_competitions, smoke_combo_page
  draw_distribution_report, prediction_coverage_report
```

Post-deploy audit: **Draw labels 0**, **best_pick 0** (correct for all-no_bet data).

---

## Deploy status

| Step | Status |
|------|--------|
| Backup (DB + frontend) | Done on server |
| Backend `match_center_helpers.py` + `competitions.py` | Deployed |
| Frontend `dist/` | Deployed (local build) |
| API restart | Done |
| Smoke `/matches`, `/combo-tips`, APIs | 200 |

---

## Next recommendation

1. **Regenerate World Cup predictions** with bettable picks (`no_bet: false`) — combo and elite cards will light up without further UI work.
2. **Extend background prediction storage** to Premier League (200 fixtures, 0 cached) — coverage gap is generation scope, not Match Center UI.
3. **Off-season leagues** — zero upcoming is expected in June; `zero_fixture_reason` now shown in league selector.
4. **Do not** loosen combo to include `no_bet` rows — that would surface low-confidence placeholder data.

**WDE / scoring / models:** unchanged — Draw spike was **summary extraction**, not model bias.

---

**STOP** — Phase A13A complete.
