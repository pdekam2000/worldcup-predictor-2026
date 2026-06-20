# Phase 16 — Odds-Primary Shadow Engine Report

Generated: 2026-06-19T17:37:11.933879+00:00

## Mode

- **Shadow only** — production engine unchanged
- **No deploy**, no live prediction changes
- Engine: `OddsPrimaryScorelineEngine` (odds 70% + xG 25% + stats nudge 5%)

## Dataset

- Fixtures evaluated (with results): **28**
- Odds-available shadow path: **26**

## 1. Accuracy comparison

### All fixtures (final production vs shadow scoreline 1X2)

| Metric | Production | Shadow |
|--------|------------|--------|
| 1X2 accuracy | 53.6% | 39.3% |
| Δ (Shadow − Prod) | | **-14.3%** |

### Odds-available cohort (primary shadow path)

| Metric | Production | Shadow |
|--------|------------|--------|
| 1X2 accuracy | 53.8% | 38.5% |
| Δ | | **-15.4%** |

## 2. Draw comparison

| | Production | Shadow |
|--|------------|--------|
| Draw rate (all) | 35.7% | 7.1% |
| Draw rate (odds cohort) | 34.6% | 3.8% |

## 3. Spread comparison

| | Production | Shadow |
|--|------------|--------|
| Avg λ spread | 0.3261 | 1.0131 |
| Median λ spread | 0.2000 | 0.8824 |

## 4. Scoreline distribution (top 8)

### Production

- `1-0`: 13 (46.4%)
- `1-1`: 10 (35.7%)
- `0-1`: 3 (10.7%)
- `0-2`: 1 (3.6%)
- `2-0`: 1 (3.6%)

### Shadow

- `1-0`: 12 (42.9%)
- `0-1`: 7 (25.0%)
- `2-0`: 6 (21.4%)
- `1-1`: 2 (7.1%)
- `0-2`: 1 (3.6%)

## 5. Best examples (shadow correct, production wrong)

- **1489372** Haiti vs Scotland: actual `away_win` | prod `draw` (1-1) | shadow `away_win` (0-1) | λ 1.15/1.30 → 0.60/1.66
- **900007** Mexico vs Poland: actual `draw` | prod `home_win` (1-0) | shadow `draw` (1-1) | λ 1.01/0.99 → 1.19/1.07

## 6. Worst examples (production correct, shadow wrong)

- **1489379** Saudi Arabia vs Uruguay: actual `draw` | prod `draw` (1-1) | shadow `away_win` (0-1)
- **1489377** Belgium vs Egypt: actual `draw` | prod `draw` (1-1) | shadow `home_win` (1-0)
- **1489371** Brazil vs Morocco: actual `draw` | prod `draw` (1-1) | shadow `home_win` (1-0)
- **1539000** Canada vs Bosnia & Herzegovina: actual `draw` | prod `draw` (1-1) | shadow `home_win` (1-0)
- **1489378** Iran vs New Zealand: actual `draw` | prod `draw` (1-1) | shadow `home_win` (1-0)
- **1489376** Netherlands vs Japan: actual `draw` | prod `draw` (1-1) | shadow `home_win` (1-0)

## 7. Recommendation

**Verdict: FAIL — REDESIGN**

**Redesign — shadow accuracy does not exceed production**

### Success criterion

- Accuracy > Production: **NO** (all fixtures)
- Odds cohort: **NO**

Note: Draw rate reduction is expected but **not** the success metric for Phase 16.

**Stop — shadow only. No deploy. No production changes.**
