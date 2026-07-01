# ECSE-1D — Score Distribution Report

**Phase:** ECSE-1D  
**Method version:** `ECSE-1D-v1`  
**Generated:** 2026-06-29 UTC  
**Output table:** `ecse_score_distributions`

---

## Executive Summary

Independent Poisson score distributions generated for **168,233** fixtures (**6,224,621** rows). Each fixture has **37** scorelines (0-0 through 5-5 plus an **OTHER** tail bucket). All per-fixture probabilities sum to **1.0**; ranks are unique and order by probability. **No actual result labels** are used during generation.

**Validation:** 17/17 checks passed.

---

## Build Results

| Metric | Value |
|--------|-------|
| Lambda fixtures scanned | 168,233 |
| Fixtures built | 168,233 |
| Distribution rows inserted | **6,224,621** |
| Scorelines per fixture | 37 (36 grid + OTHER) |
| Avg rank-1 probability | 0.1064 (~10.6%) |
| Avg OTHER bucket mass | 0.0164 (~1.6%) |
| Build batch | `ECSE-1D-20260629_123036` |

---

## Method

### Model

Independent Poisson baseline:

```
P(h, a) = Poisson(h; λ_home) × Poisson(a; λ_away)
```

for `h, a ∈ {0, 1, 2, 3, 4, 5}`.

**OTHER bucket** captures all mass where either side scores **> 5**:

```
P(OTHER) = 1 − Σ P(h,a) over grid
```

Final normalization divides all 37 entries so they sum to exactly 1.0.

### Input

| Source | Columns used |
|--------|----------------|
| `ecse_lambda_features` | `registry_fixture_id`, `lambda_home`, `lambda_away`, `data_quality_score` |

**Not used:** `ecse_training_dataset` labels, `historical_fixture_results`, or any post-match outcomes.

---

## Output Schema

| Column | Description |
|--------|-------------|
| `registry_fixture_id` | Fixture key (UNIQUE with `scoreline`) |
| `scoreline` | e.g. `2-1` or `OTHER` |
| `home_goals` | 0–5, or −1 for OTHER |
| `away_goals` | 0–5, or −1 for OTHER |
| `probability` | Normalized probability |
| `rank` | 1 = most likely |
| `method_version` | `ECSE-1D-v1` |
| `lambda_home` / `lambda_away` | Snapshot from lambda features |
| `data_quality_score` | Input quality from ECSE-1C |
| `build_batch` / `created_at` | Build metadata |

---

## Top-N Helpers

Python helpers in `ecse_score_distribution.py`:

| Function | Description |
|----------|-------------|
| `fetch_top_scorelines(conn, fid, top_n=5)` | Top N grid scorelines (excludes OTHER) |
| `fetch_top_scorelines_including_other(conn, fid, top_n=10)` | Top N including OTHER if ranked |
| `sample_top_n_summary(conn, sample_fixtures=5)` | Batch sample for reports |

Example top-5 for fixture `1`: `1-1` (7.97%), `1-2` (7.62%), `2-1` (7.62%), `2-2` (7.30%), `1-3` (4.87%).

---

## Validation Summary

| Check | Result |
|-------|--------|
| Probabilities strictly positive | **PASS** (0 violations) |
| Per-fixture Σp = 1.0 | **PASS** (0 off-tolerance) |
| Ranks unique 1..37 | **PASS** |
| No result labels in generation | **PASS** (SQL + generator audit) |
| Source tables unchanged | **PASS** |
| Top-5 / Top-10 helpers | **PASS** |
| Idempotent rebuild | **PASS** |

---

## Source Table Integrity

| Table | Rows (unchanged) |
|-------|------------------|
| `ecse_lambda_features` | 168,233 |
| `ecse_training_dataset` | 217,518 |

---

## Files

| Path | Purpose |
|------|---------|
| `worldcup_predictor/research/ecse_score_distribution.py` | Distribution engine |
| `scripts/run_ecse_1d_score_distribution.py` | Build runner |
| `scripts/validate_ecse_1d_score_distribution.py` | Validator |
| `artifacts/ecse_1d_distribution_summary.json` | Machine summary |
| `artifacts/ecse_1d_validation.json` | Checklist |

---

## Usage

```bash
python scripts/run_ecse_1d_score_distribution.py
python scripts/run_ecse_1d_score_distribution.py --rebuild
python scripts/validate_ecse_1d_score_distribution.py
```

---

## Next Steps (not executed)

- ECSE-1E: calibration vs actual exact scores (evaluation only)
- Dixon–Coles tail adjustment (optional upgrade from independent Poisson)
- Implied score market overlay when available

---

*No API calls. No WDE/EGIE changes. No model training. No deployment.*
