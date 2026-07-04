# ECSE-RERANK-1 — Final Report

Phase: **ECSE-RERANK-1** | Status: Shadow complete — **DO NOT PROMOTE**

## Executive Summary

Shadow re-rank layer built and validated. On **13 finished knockout matches** (local DB):

- Baseline ECSE Top 1: **15.4%** → Shadow Top 1: **23.1%** (+7.7pp)
- Top 3 unchanged at **53.8%** (re-rank mainly reorders within Top 10)
- Top 5 unchanged at **76.9%**
- BTTS consistency: **45.5%** → **90.9%**
- Clean-sheet Top 1 overprediction reduced: **92.3%** → **53.8%**

Sample too small for production promotion of re-rank logic.

## Baseline Metrics

| Metric | Value |
|--------|-------|
| ECSE Top 1 | 15.4% |
| ECSE Top 3 | 53.8% |
| ECSE Top 5 | 76.9% |
| WDE 1X2 | 81.8% |
| WDE BTTS | 54.5% |
| WDE O/U 2.5 | 54.5% |
| Clean-sheet Top 1 | 92.3% |
| WDE BTTS Yes + clean Top 1 | 6/13 |

## Shadow Re-Rank Metrics

| Metric | Baseline | Shadow |
|--------|----------|--------|
| Top 1 hit | 15.4% | 23.1% |
| Top 3 hit | 53.8% | 53.8% |
| Top 5 hit | 76.9% | 76.9% |
| BTTS consistency | 45.5% | 90.9% |
| O/U consistency | 63.6% | 81.8% |
| Rank changes | — | 5/13 matches |

## Before / After Examples

| Match | Baseline Top 1 | Shadow Top 1 | Actual | Notes |
|-------|----------------|--------------|--------|-------|
| Portugal vs Croatia | 1-0 | 2-1 | 2-1 | BTTS Yes — exact hit after boost |
| Belgium vs Senegal | 1-0 | 2-1 | 3-2 | Over + BTTS — closer, not exact |
| England vs Congo DR | 2-0 | 2-0 | 2-1 | WDE Under/BTTS No — no boost (correct) |
| Netherlands vs Morocco | 1-0 | 1-1 | 1-1 | Draw line promoted |

## Odds Freshness

All 18 snapshots: **STALE_ODDS**. Shadow layer correctly flags **REQUIRES_FRESH_ODDS**.
Do not promote re-rank confidence until odds freshness pipeline improves.

## AET / PEN

4 matches (AET/PEN). Evaluation uses 90-minute scores only.
Belgium 3-2 (AET) evaluated against 90-minute result stored in DB.

## What Changed (Shadow Only)

- New module: `worldcup_predictor/research/ecse_rerank/`
- Script: `scripts/run_ecse_rerank_1_shadow_analysis.py`
- Validation: `scripts/validate_ecse_rerank_1_shadow_layer.py`
- **No** WDE changes, **no** production ECSE changes, **no** DB writes

## Production Recommendation

| Decision | Choice |
|----------|--------|
| Re-rank logic | **KEEP_SHADOW_ONLY** |
| UI framing | **PROMOTE_UI_TOP3_ONLY** (wording only, no model change) |
| Owner preview re-rank | **NEED_MORE_DATA_30_TO_50_MATCHES** |
| Lambda recalibration | **DO_NOT_PROMOTE** |
| Timers | **Not enabled** |

## Final Recommendation

**ECSE_RERANK_NEEDS_MORE_DATA**

Rationale:
- Validation passed (26/26 checks)
- Shadow shows meaningful consistency gains (+45pp BTTS alignment) and modest Top 1 lift (+7.7pp on n=13)
- Sample size (13 finished) and 100% stale odds block production re-rank promotion
- UX Top 3 framing can ship independently without model changes

---
STOP — No production promotion. No retrain. No timers.
