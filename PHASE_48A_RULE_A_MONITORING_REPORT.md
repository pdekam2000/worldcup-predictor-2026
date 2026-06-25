# Phase 48A — Rule A Monitoring Report

**Status:** ACTIVE IN PRODUCTION  
**Date:** 2026-06-22 UTC

---

## Purpose

Measure the **real production impact** of Phase 47C Rule A conditional harmonization using settled fixtures and harmonization telemetry — not offline replay alone.

---

## Data Sources

| Source | Role |
|--------|------|
| `worldcup_prediction_evaluations` | Settled 1X2 correct/wrong (quarantined rows excluded) |
| `worldcup_stored_predictions` | Harmonization metadata at predict time |
| `performance_snapshots.rule_a_json` | Point-in-time Rule A counters |

---

## Telemetry Fields (per prediction)

| Field | Values |
|-------|--------|
| `harmonization_used` | `true` / `false` |
| `harmonization_source` | `wde` / `scoreline` |
| `harmonization_reason` | `rule_a_odds_present`, `rule_a_odds_absent`, `no_conflict`, `unconditional` |
| `rule_a_active` | `true` when `RULE_A_GATE_MODE=active` |
| `odds_available` | Pre-match odds on intelligence report |

Stamped via `stamp_prediction_engine_metadata()` from `MatchPrediction.metadata`.

---

## Production Counters

| Counter | Definition |
|---------|------------|
| **WDE preserved** | `harmonization_source=wde` or harmonization not used for 1X2 |
| **Scoreline override** | `harmonization_source=scoreline` and `harmonization_used=true` |
| **Beneficial override** | On WDE≠scoreline conflict: scoreline matches actual, WDE does not |
| **Harmful override** | On conflict: WDE matches actual, scoreline does not |
| **Neutral override** | On conflict: both wrong |
| **Override rate** | `scoreline_override / (wde_preserved + scoreline_override)` |

---

## Expected vs Replay

| Metric | Offline replay (n=207) | Production (live) |
|--------|-------------------------|-------------------|
| Unconditional accuracy | 30.0% | Pre-47C historical |
| Rule A accuracy | 36.7% | **To be measured** as fixtures settle |
| Harmful overrides | 63 → 1 | Tracked in `harmful_override` |
| Override rate | 91.8% → ~4.3% | Tracked in `override_rate` |

Production sample is still small at deploy time — Rule A counters populate as new predictions include telemetry and matches finish.

---

## Monitoring Surfaces

1. **API:** `GET /api/performance/summary` → `rule_a_monitoring`
2. **API:** `GET /api/performance/monitoring` → full bundle
3. **UI:** Performance Center → Rule A Monitoring panel
4. **DB:** `performance_snapshots.rule_a_json` history

---

## Interpretation Guide

| Signal | Meaning |
|--------|---------|
| High `wde_preserved`, low `harmful_override` | Rule A working as designed (no-odds path) |
| `beneficial_override` &gt; `harmful_override` on odds cohort | Scoreline harmonization adding value |
| `no_telemetry` rising | Legacy predictions pre-47C — will age out |
| `override_rate` ~10–15% | Expected (odds-present fixtures only) |

---

## No WDE Changes

Rule A monitoring is **read-only analytics**. Factor weights and decision math unchanged.

---

**Rule A production monitoring: ACTIVE**
