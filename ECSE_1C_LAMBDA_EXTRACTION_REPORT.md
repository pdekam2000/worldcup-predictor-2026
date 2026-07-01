# ECSE-1C — Lambda Extraction Report

**Phase:** ECSE-1C  
**Method version:** `ECSE-1C-v1`  
**Generated:** 2026-06-29 UTC  
**Output table:** `ecse_lambda_features`

---

## Executive Summary

Lambda extraction completed for **168,233** of **217,518** ECSE training fixtures (**77.3%** coverage). All lambdas are strictly positive with `lambda_total = lambda_home + lambda_away` enforced exactly. **No `ft_draw_closing` odds** were available (OddAlerts SOURCE_EXPORT_GAP); all rows have `missing_draw_flag=1` and use double-chance / 1X2 balance / league prior for draw proxy probability.

**Validation:** 15/15 checks passed.

---

## Build Results

| Metric | Value |
|--------|-------|
| Training dataset rows scanned | 217,518 |
| Lambda rows inserted | **168,233** |
| Skipped (insufficient odds) | 49,285 (22.7%) |
| Avg `lambda_home` | 1.618 |
| Avg `lambda_away` | 1.562 |
| Avg `lambda_total` | 3.180 |
| Avg `data_quality_score` | 0.537 |
| Avg `source_feature_count` | 5.34 |
| Build batch | `ECSE-1C-20260629_122538` |

---

## Method Overview

### Inputs (from `ecse_training_dataset` closing odds)

| Signal | Use |
|--------|-----|
| `ft_home_closing` / `ft_away_closing` | 1X2 implied probs, home/away goal split |
| `ft_draw_closing` | **Unavailable** — not required; no build failure |
| `btts_yes/no_closing` | BTTS calibration nudge on team lambdas |
| `ou_over_*` / `ou_under_*` | Poisson total-goals λ from 1.5 / 2.5 / 3.5 lines |
| `team_*_over_05/15` | Direct team λ from scoring probability |
| `dc_*_closing` | Draw proxy: `(P(HD)+P(DA)−P(HA))/2` |
| `fh_*_closing` | Counted in feature coverage (future weighting) |

### Pipeline steps

1. **Implied probability** — `1 / odds` (odds ≥ 1.0)
2. **Margin removal** — proportional de-vig on two-way markets (O/U, BTTS, team O/U)
3. **λ_total** — invert Poisson over-probability for lines 2.5 (40%), 1.5 (20%), 3.5 (15%); blend with team-sum estimate (25%)
4. **λ_home / λ_away** — team over-0.5/1.5 inversions blended with `λ_total × share` from 1X2 strength
5. **BTTS calibration** — gentle scale (±15%) when model BTTS deviates >3pp from market
6. **Enforce** — `lambda_total = lambda_home + lambda_away`, clip each λ ∈ [0.15, 6.0]

### Draw handling (SOURCE_EXPORT_GAP safe)

| Priority | Source | Rows affected |
|----------|--------|---------------|
| 1 | `ft_draw_closing` | 0 (none available) |
| 2 | Double-chance formula | ~73,624 (full/partial DC) |
| 3 | 1X2 balance with DC draw | blended into `implied_draw_probability` |
| 4 | League prior 0.26 | remainder when no DC/1X2 |

All rows receive `draw_proxy_probability` (never NULL). `missing_draw_flag=1` on all 168,233 rows.

---

## Output Schema: `ecse_lambda_features`

| Column | Description |
|--------|-------------|
| `registry_fixture_id` | FK to `ecse_training_dataset` (UNIQUE) |
| `lambda_home` | Expected home goals |
| `lambda_away` | Expected away goals |
| `lambda_total` | `lambda_home + lambda_away` (exact) |
| `draw_proxy_probability` | Draw prob estimate (DC / 1X2 / prior) |
| `implied_home_probability` | De-vigged home win prob (when available) |
| `implied_away_probability` | De-vigged away win prob |
| `implied_draw_probability` | Draw prob used in 1X2 split |
| `data_quality_score` | 0–1 composite input richness |
| `missing_draw_flag` | 1 = no `ft_draw_closing` |
| `source_feature_count` | Count of non-null input odds |
| `insufficient_odds_flag` | Always 0 for inserted rows |
| `method_version` | `ECSE-1C-v1` |
| `build_batch` | Build identifier |
| `created_at` | UTC timestamp |

---

## Skipped Fixtures (49,285)

Fixtures skipped when **no λ estimate possible** — requires at least one of:

- O/U 2.5 (or 1.5 / 3.5 pair), or
- Both team over-0.5 markets, or
- Both `ft_home` and `ft_away` closing odds

and `data_quality_score ≥ 0.20`.

These fixtures lack sufficient overlapping market signals for stable Poisson inversion.

---

## Validation Summary

| Check | Result |
|-------|--------|
| Source tables unchanged | **PASS** |
| Lambdas strictly positive | **PASS** (0 violations) |
| `lambda_total ≈ lambda_home + lambda_away` | **PASS** (0 mismatches) |
| Missing draw handled safely | **PASS** (no failures) |
| `draw_proxy_probability` populated | **PASS** (100%) |
| Insufficient fixtures skipped | **PASS** (49,285) |
| Idempotent rebuild | **PASS** |
| Fingerprint stable | **PASS** |

---

## Source Table Integrity

| Table | Rows (unchanged) |
|-------|------------------|
| `ecse_training_dataset` | 217,518 |
| `historical_csv_odds_prematch_clean` | 1,908,702 |
| `historical_fixture_results` | 222,985 |

---

## Files

| Path | Purpose |
|------|---------|
| `worldcup_predictor/research/ecse_lambda_extraction.py` | Core extraction engine |
| `scripts/run_ecse_1c_lambda_extraction.py` | Build runner |
| `scripts/validate_ecse_1c_lambda_extraction.py` | 15-check validator |
| `artifacts/ecse_1c_lambda_summary.json` | Machine-readable summary |
| `artifacts/ecse_1c_validation.json` | Validation checklist |

---

## Usage

```bash
python scripts/run_ecse_1c_lambda_extraction.py
python scripts/run_ecse_1c_lambda_extraction.py --rebuild
python scripts/validate_ecse_1c_lambda_extraction.py
```

---

## Next Steps (not executed)

- ECSE-1D: scoreline probability grid from `(lambda_home, lambda_away)`
- Re-run after draw CSV re-export to replace draw proxy with direct `ft_draw` de-vig
- Optional: weight `fh_*` odds for half-time λ split

---

*No API calls. No production prediction / WDE / EGIE changes. No model training.*
