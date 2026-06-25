# PHASE 52A — Shadow Backtest Report

**Phase:** 52A  
**Status:** `SHADOW_BACKTEST_COMPLETE`  
**Competition:** `premier_league`  
**Fixtures:** 359  
**Errors:** 0

## Head-to-head

| Metric | Baseline | Survival | Delta | Target |
|--------|----------|----------|-------|--------|
| First Goal Team | 50.8% | 49.3% | −1.5pp | ≥50.8% |
| Goal Range | 27.8% | **31.0%** | **+3.2pp** | ≥35% |
| Goal Minute Exact | 3.4% | 3.6% | +0.2pp | — |
| Goal Minute Soft | 33.8% | **38.4%** | **+4.6pp** | ≥40% |

## Coverage

| | Baseline | Survival |
|---|----------|----------|
| Published | 349 | 349 |
| NO_PICK | 10 | 10 |

Both engines respect `MIN_DATA_QUALITY_FOR_PREDICTION = 0.45`.

## Range prediction distribution (primary pick)

| Bucket | Baseline picks | Survival picks |
|--------|----------------|----------------|
| 0–15 | 191 (54.7%) | 222 (63.6%) |
| 16–30 | 115 | 109 |
| 31–45+ | 4 | 10 |
| 46–60 | 29 | 16 |
| 61–75 | 6 | 2 |
| 76–90+ | 4 | 0 |

Survival improves **accuracy** on range despite still favoring early buckets — internal probability vectors are more calibrated even when argmax remains 0–15.

## Success criteria evaluation

| Criterion | Required | Survival | Pass |
|-----------|----------|----------|------|
| Goal Range | >35% | 31.0% | **No** |
| Goal Minute Soft | >40% | 38.4% | **No** |
| First Goal Team | ≥50.8% | 49.3% | **No** |

## Verdict

**Deploy justified: False**

Survival shows promising direction on timing markets (+3.2pp range, +4.6pp minute soft) but fails all three promotion gates. Per Phase 52A stop condition:

- **Do not activate in production**
- **Do not replace current EGIE**
- Continue shadow observation and model refinement in a future phase

**PHASE_52A_STATUS = SHADOW_BACKTEST_COMPLETE**
