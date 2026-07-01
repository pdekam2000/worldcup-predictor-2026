# GOAL TIMING SPLIT — Smoke Report (GT-1)

**Phase:** GT-1  
**Mode:** Internal research — ECSE-LIVE-1 smoke fixtures  
**Status:** ok  
**Model:** `GT-1-v1`  

> Probabilistic research outputs only — not guaranteed predictions.

## Summary

- Targets: **8**
- Predicted: **8**
- Inserted: **0**
- Already exists (idempotent): **8**
- Insufficient data: **0**

## Fixture Results

| Match | Fixture | Side | Window | Tier | Home 0–30 | Away 0–30 | Home 31+ | Away 31+ | No goal |
|-------|---------|------|--------|------|-----------|-----------|----------|----------|---------|
| Brazil vs Japan | 1562344 | home | 31_plus | A | 29.3% | 10.1% | 38.9% | 13.5% | 8.2% |
| Germany vs Paraguay | 1565176 | home | 31_plus | A | 35.3% | 5.5% | 46.9% | 7.3% | 5.0% |
| Netherlands vs Morocco | 1562345 | home | 31_plus | A | 23.3% | 15.9% | 30.8% | 21.0% | 9.0% |
| Ivory Coast vs Norway | 1564789 | away | 31_plus | A | 14.9% | 25.5% | 19.8% | 33.7% | 6.1% |
| France vs Sweden | 1565177 | home | 31_plus | A | 37.6% | 3.9% | 49.8% | 5.2% | 3.4% |
| Mexico vs Ecuador | 1567306 | home | 31_plus | A | 23.8% | 13.7% | 31.6% | 18.1% | 12.9% |
| England vs DR Congo | 1567307 | home | 31_plus | A | 37.0% | 3.6% | 49.0% | 4.7% | 5.8% |
| Belgium vs Senegal | 1567308 | home | 31_plus | A | 23.7% | 15.4% | 31.4% | 20.4% | 9.1% |

## Method (brief)

- ECSE λ_home / λ_away baseline for first-goal team share
- Total λ + O/U / BTTS odds adjust scoring likelihood
- Early vs late split from EGIE/historical priors (default ~43% in 0–30)
- Confidence tiers A/B/C from data quality + probability spread

## Safety

- No WDE / EGIE / ECSE source table writes
- No public API or UI exposure
- Repeat run skips existing `fixture_id` + `model_version` rows

## Artifacts

- `C:/Users/kaman/Desktop/Footbal/artifacts/goal_timing_split_smoke.json`
