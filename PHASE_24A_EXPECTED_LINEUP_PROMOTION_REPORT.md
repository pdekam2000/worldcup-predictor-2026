# Phase 24A — Expected Lineup Promotion Report

**Status:** Complete (local only — no deployment)  
**Scope:** World Cup 2026 (`world_cup_2026`)  
**Default mode:** `shadow` (production-safe; set `EXPECTED_LINEUP_PROMOTION_MODE=gated` to apply)

---

## Objective

Promote `ExpectedLineupAgent` from trace-only into **controlled** influence on the existing **`lineup_strength` WDE factor (12%)** and **lineup confidence** — via the Promotion Adapter Layer, without changing factor weights.

---

## Promotion Architecture

```
ExpectedLineupAgent (22F)
        ↓
compute_expected_lineup_promotion()  ← gates + bounded composite blend
        ↓
apply_lineup_promotion_to_factor()   ← gated mode only
        ↓
WeightedDecisionEngine._build_factors() → lineup_strength (12% weight unchanged)
        ↓
decide() → confidence_delta (gated only, bounded)
        ↓
audit.trace + prediction.metadata + shadow JSONL
```

**Feature flag:** `EXPECTED_LINEUP_PROMOTION_MODE`

| Mode | Factor apply | Confidence apply | Shadow log |
|------|--------------|------------------|------------|
| `off` | No | No | No |
| `shadow` | No (compute only) | No | Yes |
| `gated` | Yes | Yes (bounded) | Yes |

**Rollback:** Set `EXPECTED_LINEUP_PROMOTION_MODE=off` — instant revert to Phase 22F trace behavior.

---

## Delta Limits (Enforced)

| Limit | Value |
|-------|-------|
| Max lineup score delta | ±8.0 |
| Max lineup edge delta | ±0.04 |
| Max confidence boost | +2.0 |
| Max confidence reduction | −4.0 |

**Composite blend weights (sum = 1.0):**

- Official XI: 75% lineup_v2 + 15% expected_xi + 10% lineup_confidence  
- Expected-only: 15% lineup_v2 + 70% expected_xi + 15% lineup_confidence  

**Gates:** WC 2026 only, non-placeholder, expected agent usable, data_sources present.  
**Dampening:** 50% delta when `lineup_supports_internal=false`.

**Not allowed (by design):**

- Direct 1X2 winner override  
- Auto no-bet creation from promotion  
- Confidence spikes above +2  

---

## Required Outputs

| Output | Location |
|--------|----------|
| `lineup_delta_score` | `audit.trace`, `prediction.metadata` |
| `lineup_promotion_active` | `audit.trace`, `prediction.metadata` |
| `lineup_promotion_reason` | `audit.trace`, `prediction.metadata` |
| `lineup_promotion_confidence` | `audit.trace`, `prediction.metadata` |
| `expected_vs_confirmed_history` | `audit.trace`, shadow JSONL |

---

## Files Changed

**New**

- `worldcup_predictor/promotion/__init__.py`
- `worldcup_predictor/promotion/config.py`
- `worldcup_predictor/promotion/models.py`
- `worldcup_predictor/promotion/expected_lineup_adapter.py`
- `worldcup_predictor/promotion/shadow_store.py`
- `scripts/validate_phase24a_expected_lineup_promotion.py`
- `PHASE_24A_EXPECTED_LINEUP_PROMOTION_REPORT.md`

**Modified**

- `worldcup_predictor/config/settings.py` — `EXPECTED_LINEUP_PROMOTION_MODE`, shadow path
- `worldcup_predictor/decision/weighted_decision_engine.py` — adapter hook in `_build_factors`, confidence in `decide()`, metadata
- `worldcup_predictor/decision/audit_report.py` — promotion fields on `FinalDecisionTrace`

**Unchanged**

- WDE factor weights (15/15/12/12/12/10/10/8/6)  
- `ExpectedLineupAgent` / 22F engine (no logic change)  
- Orchestrator order  

---

## Cache Impact

- **No new API calls.** Promotion reads existing specialist signals and settings.
- Shadow log: `{EXPECTED_LINEUP_PROMOTION_SHADOW_PATH}` default `data/shadow/expected_lineup_promotion_shadow.jsonl`
- Expected lineup ApiCache (22F) unchanged.

---

## Prediction Impact

| Mode | lineup_strength score | Confidence | 1X2 selection |
|------|----------------------|------------|---------------|
| `off` | Baseline (lineup_v2) | Unchanged | Unchanged |
| `shadow` | Unchanged | Unchanged | Unchanged |
| `gated` | Baseline + bounded delta | ± bounded delta | May shift only via factor edge (no direct override) |

**Validation fixture (offline):** baseline lineup score **46.0** → shadow delta **+8.0** (capped) → gated score **54.0**.

WDE weights verified unchanged: `lineup_strength` remains **0.12**.

---

## Rollback Strategy

1. **Instant:** `EXPECTED_LINEUP_PROMOTION_MODE=off` in `.env`  
2. **Default safe:** factory default remains `shadow` (compute/log only)  
3. **No migration rollback** — no DB schema changes  
4. Shadow JSONL preserved for post-mortem  

---

## Validation Results

```bash
python scripts/validate_phase24a_expected_lineup_promotion.py
python scripts/validate_phase22f_expected_lineups.py
```

| Script | Result |
|--------|--------|
| `validate_phase24a_expected_lineup_promotion.py` | **24/24** |
| `validate_phase22f_expected_lineups.py` | **27/27** (regression) |

### Shadow vs gated comparison (validator scenario)

| Metric | Before (`off`) | Shadow | Gated |
|--------|----------------|--------|-------|
| lineup_promotion_active | false | true | true |
| lineup_delta_score | 0.0 | +8.0 | +8.0 |
| lineup_strength factor score | 46.0 | 46.0 | 54.0 |
| applied to prediction | — | false | true |

---

## Environment Variables

```env
EXPECTED_LINEUP_PROMOTION_MODE=shadow   # off | shadow | gated
EXPECTED_LINEUP_PROMOTION_SHADOW_PATH=data/shadow/expected_lineup_promotion_shadow.jsonl
```

---

## Stop Boundary

Phase 24A complete. **Phase 24B (Tournament Context) not started** — awaiting approval.
