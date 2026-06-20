# Phase 24C — xG + Sportmonks Promotion Report

**Status:** Complete (local only — no deployment)  
**Scope:** World Cup 2026 (`world_cup_2026`)  
**Default modes:** `shadow` for both flags (production-safe)

---

## Objective

Promote **XGIntelligenceAgent** (Phase 22D) into controlled **`tactics_matchup`** influence, and **SportmonksPredictionAgent** (Phase 22C) into a **confidence/disagreement layer only** — without changing WDE weights, 1X2 selection authority, or auto no-bet behavior.

---

## Promotion Architecture

```
XGIntelligenceAgent (22D)
        ↓
compute_xg_promotion() → apply_xg_promotion_to_factor()  [gated only]
        ↓
WeightedDecisionEngine._build_factors() → tactics_matchup (12% unchanged)

SportmonksPredictionAgent (22C)
        ↓
compute_sportmonks_prediction_promotion()  [decide() — confidence/audit only]
        ↓
decide() → combined promotion confidence delta (24A+24B+24C cap)
        ↓
audit.trace + conflicts + limitations + shadow JSONL
```

**Feature flags:**

| Flag | Modes | Default |
|------|-------|---------|
| `XG_PROMOTION_MODE` | `off` \| `shadow` \| `gated` | `shadow` |
| `SPORTMONKS_PREDICTION_PROMOTION_MODE` | `off` \| `shadow` \| `gated` | `shadow` |

| Mode | xG tactics apply | SM confidence apply | Shadow log |
|------|------------------|---------------------|------------|
| `off` | No | No | No |
| `shadow` | No (compute only) | No (compute only) | Yes |
| `gated` | Yes (when gates pass) | Yes (bounded) | Yes |

**Rollback:** Set either flag to `off` — instant revert. Independent from 24A/24B flags.

---

## Delta Limits (Enforced)

### xG → tactics_matchup

| Limit | Value |
|-------|-------|
| Max tactics score delta | ±6.0 |
| Max tactics O/U (`tactics_over`) delta | ±0.15 |
| Min xG confidence (when plan ≠ full) | 50.0 |
| Max disagreement for apply | 0.35 |

**Gates:** WC 2026, non-placeholder, `plan_support=full` OR `xg_confidence≥50`, `comparison_available`, `xg_total` present, disagreement ≤ 0.35.

**Apply rule:** If `xg_supports_internal=false` → trace only (no factor apply).

**Blend (when gated + supports internal):**

```
raw_adjust = clamp(0.6*(xg_total-2.5)*10 + 0.4*(goals_pressure-50)*0.1, ±6)
score_delta = clamp((baseline + raw_adjust)/2 - baseline, ±6)
over_delta  = clamp((xg_total - 2.5) * 0.25, ±0.15)
```

### Sportmonks → confidence/audit only

| Limit | Value |
|-------|-------|
| Max confidence reduction | −6.0 |
| Max confidence boost | 0.0 (reduction-only by design) |
| Min Sportmonks confidence gate | 55.0 |
| Cumulative promotion cap (24A+24B+24C) | ±6.0 |

| Conflict | Confidence delta |
|----------|------------------|
| medium / caution | −3 |
| high / no_bet_review | −6 |
| high + consensus < 50 | additional −2 (within cap) |

**Never:** override `_resolve_1x2()`, change `baseline.one_x_two.selection`, auto no-bet.

**Trace-only:** `no_bet_review` → audit warning + `sportmonks_no_bet_review_trace` (not auto no-bet).

---

## Required Outputs

| Output | Location |
|--------|----------|
| `xg_delta_score` | `audit.trace`, `prediction.metadata` |
| `xg_promotion_active` | `audit.trace`, `prediction.metadata` |
| `xg_promotion_reason` | `audit.trace`, `prediction.metadata` |
| `xg_promotion_confidence` | `audit.trace`, `prediction.metadata` |
| `sportmonks_confidence_delta` | `audit.trace`, `prediction.metadata` |
| `sportmonks_disagreement_signal` | `audit.trace`, `prediction.metadata` |
| `sportmonks_promotion_active` | `audit.trace`, `prediction.metadata` |
| `sportmonks_promotion_reason` | `audit.trace`, `prediction.metadata` |
| `combined_promotion_confidence_delta` | `audit.trace`, `prediction.metadata` |

---

## Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/promotion/config.py` | 24C constants |
| `worldcup_predictor/promotion/models.py` | `XGPromotionResult`, `SportmonksPredictionPromotionResult` |
| `worldcup_predictor/promotion/xg_promotion_adapter.py` | **New** |
| `worldcup_predictor/promotion/sportmonks_prediction_adapter.py` | **New** |
| `worldcup_predictor/promotion/shadow_store.py` | xG + SM shadow records/stores |
| `worldcup_predictor/promotion/__init__.py` | Export 24C symbols |
| `worldcup_predictor/config/settings.py` | `XG_PROMOTION_MODE`, `SPORTMONKS_PREDICTION_PROMOTION_MODE`, shadow paths |
| `worldcup_predictor/decision/audit_report.py` | 24C trace fields |
| `worldcup_predictor/decision/weighted_decision_engine.py` | xG tactics hook + SM confidence/audit + cumulative cap |
| `scripts/validate_phase24c_xg_sportmonks_promotion.py` | **New** |
| `PHASE_24C_XG_SPORTMONKS_PROMOTION_REPORT.md` | **New** |

**Unchanged:** WDE factor weights, calibration, deployment.

---

## Prediction Impact (Offline Simulation)

Test fixture: France vs Japan (WC 2026).

| Mode | Tactics score | xG delta | 1X2 | Combined conf delta |
|------|---------------|----------|-----|---------------------|
| `off` | 58.5 | 0.0 | home_win | 0.0 |
| `shadow` | 58.5 (factor) / 59.3 (computed) | +0.84 | home_win | 0.0 (computed −3 SM not applied) |
| `gated` | 59.3 | +0.84 | home_win (unchanged) | −3.0 (Sportmonks medium/caution) |

- No 1X2 winner flip  
- No auto no-bet from Sportmonks `no_bet_review`  
- O/U path receives bounded `tactics_over` delta when xG gated  

---

## Cache Impact

**None.** Adapters consume existing specialist signals and supplemental Sportmonks blocks already loaded by Phase 22C/22D enrichment. No new API calls or cache TTL changes.

Shadow logs:

- `data/shadow/xg_promotion_shadow.jsonl`
- `data/shadow/sportmonks_prediction_promotion_shadow.jsonl`

---

## Rollback Strategy

1. `XG_PROMOTION_MODE=off` — reverts tactics to pre-24C path.  
2. `SPORTMONKS_PREDICTION_PROMOTION_MODE=off` — removes SM confidence/audit promotion.  
3. Both default to `shadow` — zero production factor/confidence apply until explicitly gated.  
4. Independent rollback per adapter; 24A/24B flags unaffected.

---

## Validation Results

| Validator | Result |
|-----------|--------|
| `validate_phase24c_xg_sportmonks_promotion.py` | **32/32 passed** |
| `validate_phase24a_expected_lineup_promotion.py` | **24/24 passed** |
| `validate_phase24b_tournament_context_promotion.py` | **28/28 passed** |

---

## WDE Weights (Unchanged)

| Factor | Weight |
|--------|--------|
| data_quality | 15% |
| team_form | 15% |
| injuries_suspensions | 12% |
| lineup_strength | 12% |
| tactics_matchup | 12% |
| player_quality | 10% |
| odds_market_signal | 10% |
| motivation_psychology | 8% |
| weather_referee_context | 6% |

---

## Recommendation for Phase 25 Calibration

Phase 24A–24C complete the **trace promotion stack** in shadow-safe mode. Phase 25 calibration should:

1. **Replay shadow JSONL** (24A–24C) against finished WC 2026 fixtures — measure hit-rate delta shadow vs gated vs off.  
2. **Tune adapter caps** (not WDE weights) using empirical distributions: lineup ±8, context motivation ±6, xG tactics ±6, SM confidence −3/−6.  
3. **Gate promotion to `gated`** only after shadow replay shows positive uplift on 1X2, O/U, and confidence calibration without increasing false no-bet rate.  
4. **Keep Sportmonks confidence-only** until governance approves optional 15% odds_score blend (Phase 23B optional hook — not implemented in 24C).  
5. **Run unified cumulative cap review** — current ±6.0 across 24A+24B+24C may need fixture-type stratification (group vs knockout).  
6. **Do not change WDE weights** until shadow replay + A/B gated metrics justify a separate weight calibration approval.

---

Phase 24C complete. **Phase 25 not started** — awaiting approval.
