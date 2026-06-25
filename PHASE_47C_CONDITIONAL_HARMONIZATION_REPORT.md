# Phase 47C — Conditional Harmonization Deployment Report

**Status:** PRODUCTION_ACTIVE  
**Date:** 2026-06-22 UTC  
**Goal:** Replace unconditional 1X2 harmonization with Rule A conditional harmonization.

---

## Executive Summary

Production now uses **Rule A** when `RULE_A_GATE_MODE=active`:

- **Odds present** → harmonize 1X2 to scoreline-implied winner  
- **Odds absent** → keep WDE 1X2 winner  

O/U, halftime caps, first-goal alignment, and other consistency guards are **unchanged**.

Offline replay (n=207) confirms expected accuracy lift from **30.0%** → **36.7%** (+6.8 pp).

---

## What Changed

| Component | Change |
|-----------|--------|
| `rule_a_gate/policy.py` | **New** — `resolve_rule_a_1x2()` policy |
| `consistency_engine.py` | Rule A for 1X2 only; telemetry metadata |
| `scoring_engine.py` | Passes `odds_available`, `wde_one_x_two`, `conditional_1x2` |
| `settings.py` | `RULE_A_GATE_MODE` default **`active`**; added `active` mode |
| `rule_a_gate/models.py` | Mode: `off` \| `shadow` \| `active` |

### Unchanged

- WDE factor weights  
- Scoreline engine / λ path  
- O/U harmonization to scoreline total  
- Halftime estimate cap (≤ 55% of full-time total)  
- First-goal team alignment  
- Provider utilization / billing / weather / evaluation pipelines  

---

## Rule A Logic

```
IF RULE_A_GATE_MODE == active:
    IF pre_match_odds.available AND bookmakers:
        1X2 = scoreline_implied
        harmonization_source = scoreline
        harmonization_reason = rule_a_odds_present
    ELSE:
        1X2 = wde_selection
        harmonization_source = wde
        harmonization_reason = rule_a_odds_absent
ELSE IF mode == off:
    1X2 = scoreline_implied  (legacy unconditional)
ELSE mode == shadow:
    production = unconditional; shadow JSONL records Rule A parallel pick
```

---

## Telemetry (prediction metadata)

| Field | Values | Meaning |
|-------|--------|---------|
| `harmonization_used` | `true` / `false` | 1X2 was set via scoreline harmonization path |
| `harmonization_source` | `wde` / `scoreline` | Authority for published 1X2 |
| `harmonization_reason` | `rule_a_odds_present`, `rule_a_odds_absent`, `unconditional`, `no_conflict` | Why that source was chosen |
| `rule_a_active` | `true` / `false` | Rule A enabled for this prediction |
| `odds_available` | `true` / `false` | Pre-match odds on intelligence report |

---

## Replay Validation (n=207)

| Strategy | 1X2 Accuracy | Notes |
|----------|--------------|-------|
| A. Current (pre-47C unconditional) | **30.0%** | Always scoreline 1X2 |
| B. WDE only | **34.8%** | Never harmonize 1X2 |
| C. Rule A (production) | **36.7%** | Odds → scoreline; no odds → WDE |

**Validation:** `scripts/validate_phase47c_conditional_harmonization.py` — **15/15 PASS** (local + production)

---

## Override Impact

| Metric | Before (unconditional) | After (Rule A) |
|--------|------------------------|----------------|
| **1X2 override rate** | **91.8%** (190/207) | **~4.3%** (9/207 odds-path harmonizations) |
| **Harmful overrides** | **63** | **1** (odds-present only) |
| **Beneficial overrides (odds cohort)** | **5** | **5 preserved** |
| **Beneficial overrides (no-odds)** | 48 | Intentionally traded for 62 harmful removals |

### Why accuracy improves

1. **62 harmful `home_win → draw` flips eliminated** on no-odds Bundesliga replay (WDE correct, draw wrong).  
2. **5 beneficial odds-cohort harmonizations preserved** — scoreline still authoritative when market data exists.  
3. **48 no-odds beneficial overrides relinquished** — these were scoreline getting lucky on draws while WDE was wrong; net trade strongly positive (+6.8 pp).

---

## Expected Accuracy Gain

| Metric | Value |
|--------|-------|
| vs unconditional production | **+6.8 pp** (30.0% → 36.7%) |
| vs WDE-only | **+1.9 pp** (34.8% → 36.7%) |
| Harmful override reduction | **98.4%** (63 → 1) |

---

## Production Deployment

| Step | Result |
|------|--------|
| Backup | `/opt/worldcup-predictor/backups/deploy-phase47c-20260622-025057` |
| `RULE_A_GATE_MODE` | Set to **`active`** in `.env.production` |
| API restart | `worldcup-api` active |
| nginx reload | OK |
| Validation | 15/15 PASS |
| Smoke | 4/4 PASS |

### Smoke checks

- `/api/health` — OK  
- `RULE_A_GATE_MODE=active`  
- `harmonize_prediction` keeps WDE when odds absent  
- `/api/performance/summary` — 200  

---

## Mode Reference

| `RULE_A_GATE_MODE` | Production 1X2 | Shadow JSONL |
|--------------------|----------------|--------------|
| `active` | Rule A | Not recorded |
| `shadow` | Unconditional (legacy) | Rule A parallel pick |
| `off` | Unconditional (escape hatch) | Off |

---

## Rollback

```bash
cd /opt/worldcup-predictor
cp backups/deploy-phase47c-20260622-025057/env.production .env.production
# Set RULE_A_GATE_MODE=shadow or off
systemctl restart worldcup-api
```

Or restore pre-deploy files from backup directory.

---

## Files Deployed

```
worldcup_predictor/prediction/consistency_engine.py
worldcup_predictor/prediction/scoring_engine.py
worldcup_predictor/prediction/rule_a_gate/policy.py
worldcup_predictor/prediction/rule_a_gate/models.py
worldcup_predictor/prediction/rule_a_gate/shadow_runner.py
worldcup_predictor/config/settings.py
scripts/validate_phase47c_conditional_harmonization.py
scripts/deploy_phase47c_production.sh
scripts/phase47c_production_smoke.py
```

---

**PHASE_47C_STATUS = PRODUCTION_ACTIVE**
