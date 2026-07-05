# ECSE Top5 Reliability Gate — Owner Report

**Dataset:** n=16 legitimate eligible fixtures (post-forensic review)  
**Overall Top5 hit rate:** 68.8% (11/16)  
**Gate recommendation:** Do not deploy — insufficient OOS signal

---

## Target definition

- **Hit (1):** actual full-time score appears anywhere in ECSE ordered Top5
- **Miss (0):** otherwise
- Rank not used in target (only for secondary analysis)

---

## Hit vs miss (key features)

| Feature | HIT | MISS | Diff |
|---------|----:|-----:|-----:|
| lambda_total | 2.59 | 2.75 | −0.16 |
| lambda_gap | 1.23 | 1.76 | −0.54 |
| cum_top5_prob | 0.58 | 0.63 | −0.05 |
| wde_confidence | 63 | 73 | −10 |

Misses skew toward higher lambda gap and higher WDE confidence — weak, n=5 misses only.

---

## Segment hit rates (n≥3 only)

| Segment | N | Hit rate |
|---------|--:|---------:|
| Strong favorite | 8 | 75% |
| Medium scoring regime | 10 | 80% |
| High scoring regime | 6 | 50% |
| Strongly WDE/ECSE aligned | 9 | 67% |
| BTTS Yes lean | 8 | 75% |
| Over 2.5 lean | 5 | 80% |
| Under 2.5 lean | 9 | 67% |

Wide confidence intervals on all segments — **not actionable**.

---

## Shadow reliability gate (OOS)

Transparent rule-based gate trained on first 10 fixtures, tested on last 6:

| Class | Coverage (test) | Top5 hit | Hit@3 |
|-------|----------------:|---------:|------:|
| All (baseline) | 6 | 67% | 50% |
| HIGH_RELIABILITY | 1 | 0% | 0% |
| MEDIUM_RELIABILITY | 4 | 75% | 50% |
| LOW_RELIABILITY | 1 | 100% | 100% |

**Gate fails usefulness criteria:**
- HIGH group has n=1 (trivial coverage)
- HIGH Top5 hit (0%) worse than baseline (67%)
- Results unstable across chronological split

---

## Rank bias inside reliability classes (test set)

| Class | Rank2 hits |
|-------|-----------|
| MEDIUM_RELIABILITY | 2 of 3 hits |

Rank2 bias from ECSE-TOP5-RANK-FORENSIC-1 **may persist** in medium-reliability cases; sample too small to confirm.

---

## Bottom line

**`ECSE_PARITY_RESTORED_NO_RELIABILITY_SIGNAL`**

- Parity fixed; reliability research can proceed as more finished matches accumulate
- No pre-match reliability gate ready for production
- Continue collecting eligible evaluations; revisit gate when n≥30+ with strict chronological OOS
