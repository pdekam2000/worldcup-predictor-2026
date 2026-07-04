# TOP3-ENDRESULT-OPTIMIZER-1 — Baseline Rank-Hit Analysis

Phase: **TOP3-ENDRESULT-OPTIMIZER-1** | Mode: Read-only audit | Sample: **13 finished WC 2026 matches** (knockout)

Data source: `ecse_prediction_snapshots` + `fixture_results` + `worldcup_stored_predictions` (local DB, read-only).

---

## Hit Rates (Baseline ECSE)

| Metric | Rate | Hits / N |
|--------|------|----------|
| Top 1 exact | **15.4%** | 2/13 |
| Raw ECSE Top 3 | **53.8%** | 7/13 |
| Raw ECSE Top 5 | **76.9%** | 10/13 |

---

## Actual Correct Score — ECSE Rank Distribution

Where did the actual 90-minute score rank within ECSE Top 10?

| Rank | Count | Share |
|------|-------|-------|
| Rank 1 | 2 | 15.4% |
| Rank 2 | 3 | 23.1% |
| Rank 3 | 2 | 15.4% |
| Rank 4 | 3 | 23.1% |
| Rank 5 | 0 | 0.0% |
| Miss (outside Top 10) | 3 | 23.1% |

**Insight:** Correct scores often land at **Rank 2–4**, not Rank 1. Raw Top 3 misses Rank-4 hits and all misses.

---

## Top5 Signal Outside Top3

- Matches where actual was in **Top 5 but outside Top 3:** **3/13 (23.1%)**
- This is the main opportunity for portfolio optimization: swap a low-value Top3 slot for a Rank 4–5 candidate aligned with WDE markets.

Examples from sample:
- Actual at Rank 4+ while Top3 were clean-sheet lines (Portugal 2-1, England 2-1, Brazil 2-1)
- Germany 1-1: actual not in Top 5 at all (miss)

---

## Clean-Sheet & Market Bias

| Bias metric | Value |
|-------------|-------|
| Clean-sheet Top 1 rate | **92.3%** (12/13) |
| Actual BTTS Yes (90') | **8/13** |
| WDE BTTS Yes + ECSE clean-sheet Top 1 | **6/13** |
| Actual Over 2.5 (90') | **7/13** |
| WDE Over + ECSE Top1 total ≤ 2 | **4/13** |

**Root cause confirmed:** ECSE compresses to 1-0 / 2-0 clean sheets while WDE often signals BTTS Yes or Over 2.5. Correct scores frequently require BTTS or 3+ goal lines ranked 2–4 in ECSE.

---

## AET / PEN

- **4/13** matches flagged AET or PEN status
- All evaluation uses **90-minute score** from `fixture_results.home_goals/away_goals`
- Penalty winner / advancement outcome is **not** used for exact-score hit logic

---

## Odds Freshness (context)

All 13 finished matches in sample had **STALE_ODDS** relative to prediction time (same finding as ECSE-RERANK-1). Optimizer does not fetch new odds.

---

## Baseline Conclusion

Raw ECSE Top 3 at **53.8%** is reasonable but suboptimal:
- Top 5 already captures **76.9%** — pool has signal
- **3 matches** had the answer in Top 5 but not Top 3
- Portfolio selection (not re-ranking production ECSE) is the right shadow approach
