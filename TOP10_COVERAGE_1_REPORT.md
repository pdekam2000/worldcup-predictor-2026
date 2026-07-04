# TOP10-COVERAGE-1 — End Result Candidate Coverage Report

Phase: **TOP10-COVERAGE-1** | Mode: Read-only research | Sample: **13 finished WC knockout matches**

## Final Recommendation

**TOP10_SHOWS_89_THEORETICALLY_POSSIBLE**

With important caveats: 89% is **not observed**, requires **oracle-perfect Top3 selection**, and **1/13 matches (Belgium 3-2) is outside the stored Top10 pool entirely**. Primary issue for Top5 misses is **ranking (Rank 6–10)**, not missing Top10 storage.

Validation: **18/18 passed**

---

## Executive Summary

| Coverage layer | Rate | Hits / 13 |
|----------------|------|-----------|
| Top 3 (baseline selection) | 53.8% | 7/13 |
| **Top 5** | **76.9%** | 10/13 |
| **Top 10 (snapshot)** | **92.3%** | 12/13 |
| Top 20 (DB distribution) | N/A* | 0/13 |
| Full Poisson distribution (DB) | N/A* | — |
| Optimized Top3 (S5) | 61.5% | 8/13 |

\* `ecse_score_distributions` not linked for WC production fixtures (registry unresolved). Analysis uses **`ecse_prediction_snapshots.top_10_scorelines_json`** as the effective candidate pool.

**Main answer:** Of the **3 Top5 misses**, **2 were in Top10 at Rank 7** (ranking problem). **1 was absent from Top10 entirely** (Belgium **3-2** — candidate generation / tail gap).

---

## PART A — Candidate Coverage Summary

### Where actual scores appear (ECSE snapshot rank)

| Rank bucket | Count | Matches |
|-------------|-------|---------|
| Rank 1–5 | 10 | Most knockouts |
| Rank 6–10 | 2 | Germany 1-1 (rank 7), England 2-1 (rank 7) |
| Rank 11–20 | 0 | — (distribution not linked) |
| Outside Top10 | 1 | **Belgium 3-2** |
| Unavailable | 0 | — |

Correct score is usually **Rank 2–4** within Top5 (consistent with TOP3-OPTIMIZER-1), not Rank 1.

### Coverage vs selection

| Question | Answer |
|----------|--------|
| In Top5 but outside Top3? | **3/13** (23.1%) |
| In Top10 but outside Top5? | **2/13** (Germany, England) |
| Outside Top10 entirely? | **1/13** (Belgium 3-2) |
| Miss due to ranking vs absence (Top5)? | **2 ranking**, **1 candidate absence** |

---

## PART B — Top5 Miss Diagnoses

### 1. Germany vs Paraguay — Actual **1-1** (AET fixture, 90' score used)

| Field | Value |
|-------|-------|
| ECSE Top5 | 2-0 · 3-0 · 1-0 · 4-0 · 2-1 |
| ECSE Top10 includes | **1-1 at rank 7**, also 0-0 rank 8 |
| WDE signals | unavailable in stored payload |
| Odds | STALE_ODDS |
| **Root cause** | **ACTUAL_IN_TOP10_RANKING_PROBLEM** |
| Miss type | **ranking** (draw line ranked too low) |

### 2. England vs Congo DR — Actual **2-1**

| Field | Value |
|-------|-------|
| ECSE Top5 | 2-0 · 3-0 · 1-0 · 4-0 · 0-0 (all low/clean) |
| ECSE Top10 includes | **2-1 at rank 7**, 3-1 rank 8 |
| WDE BTTS | No (actual BTTS Yes) |
| WDE O/U | Under (actual Over) |
| Odds | STALE_ODDS |
| **Root cause** | **ACTUAL_IN_TOP10_RANKING_PROBLEM** |
| Miss type | **ranking** |

### 3. Belgium vs Senegal — Actual **3-2** (AET, 90' score)

| Field | Value |
|-------|-------|
| ECSE Top5 | 1-0 · 1-1 · 2-0 · 0-0 · 2-1 |
| ECSE Top10 max lines | 3-1, 2-2 — **no 3-2** |
| WDE | 1X2 ✓, BTTS Yes ✓, Over ✓ |
| Odds | STALE_ODDS |
| **Root cause** | **ACTUAL_OUTSIDE_TOP10_CANDIDATE_PROBLEM** / **HIGH_GOAL_TAIL_MISSING** |
| Miss type | **candidate_absence** |

**Not an AET/PEN evaluation error** — 90-minute score 3-2 is correct; the scoreline simply was not stored in Top10 candidates.

---

## PART C — Achievable Ceilings

Oracle ceilings (if perfect Top3 always includes actual when present in pool):

| Pool | Ceiling | Calculation |
|------|---------|-------------|
| Perfect Top3 from Top5 | **76.9%** | 10/13 |
| Perfect Top3 from Top10 | **92.3%** | 12/13 |
| Perfect Top3 from Top20/DB | **unmeasured** | registry not linked |
| Current raw Top3 | 53.8% | 7/13 |
| Current optimized S5 Top3 | 61.5% | 8/13 |

**Gap to Top10 ceiling:** 92.3% − 61.5% = **30.8 pp** still available with better 3-of-10 selection (not better generation for 12/13 cases).

---

## PART D — Can Optimized Top3 Reach 89%?

| Metric | Value |
|--------|-------|
| Sample size | 13 |
| Required hits for 89% | **12/13** |
| Matches with actual in Top10 | **12/13** |
| Matches outside Top10 | **1/13** (Belgium) |
| **Maximum possible from Top10 pool** | **92.3%** (12/13) |

**Verdict:**

| Question | Answer |
|----------|--------|
| Is 89% observed? | **No** (best S5 = 61.5%) |
| Is 89% theoretically possible from existing Top10? | **Yes — barely** (need 12/13; pool allows 12) |
| Is 89% likely with current optimizer? | **No** — small sample, ranking + 1 tail miss |
| Is issue ranking or generation? | **Both, but ranking dominates (2/3 Top5 misses)** |

89% on 13 matches requires missing **at most one** game — Belgium is already uncoverable from Top10, so 89% requires **perfect hits on all other 12**. That is theoretically possible but **not demonstrated** and **fragile**.

For 30 matches, 89% requires **27/30** — cannot assess until sample grows.

---

## PART E — Ranking vs Candidate Generation

| Issue type | Evidence | Share of Top5 misses |
|------------|----------|---------------------|
| **Ranking** (in Top10, rank 6–10) | Germany 1-1, England 2-1 | **2/3** |
| **Candidate absence** (outside Top10) | Belgium 3-2 | **1/3** |
| Clean-sheet Top1 bias | 92.3% Top1 clean sheet | drives low ranks for BTTS scores |
| Stale odds | 13/13 STALE_ODDS | contextual, not root cause alone |

### Shadow experiment recommendations (no production changes)

1. **Continue Top3 optimizer S5** — addresses Rank 6–10 cases without new candidates
2. **Shadow tail injection** when WDE Over+BTTS Yes: add **3-2, 2-3, 4-1, 4-2** to candidate pool
3. **Draw hedge** when draw-risk high: ensure **1-1, 2-2** in Top5 not just rank 7+
4. **Link WC fixtures to `ecse_score_distributions`** for true Top20/full analysis (read-only audit)
5. **Do not pursue 89% target** — focus on closing gap to **Top10 ceiling (~92%)** with 30+ matches

---

## PART F — Artifacts

| File | Description |
|------|-------------|
| `artifacts/top10_coverage_1_results.json` | Full match-level coverage |
| `artifacts/top10_coverage_1_match_level.csv` | CSV export |
| `artifacts/top10_coverage_1_validation.json` | Validation results |
| `scripts/run_top10_coverage_1.py` | Runner |
| `scripts/validate_top10_coverage_1.py` | Validator |

---

## UI / Production Guidance (advisory only)

| Display | Recommendation |
|---------|----------------|
| Public Top 3 | Keep raw ECSE Top3 framing (OWNER-PREDICTIONS-UI-2) |
| Owner Top 5 | Show when actual often at rank 4–7 |
| Optimized Top 3 | Shadow/owner preview only |
| 89% messaging | **Do not use** — not validated |

---

## Next Recommended Experiment

**TOP3-OPTIMIZER-2 shadow tail pool:** inject high-goal BTTS lines (3-2, 2-3) when WDE Over+BTTS Yes **before** portfolio selection; re-backtest on 13 matches + holdout when n≥30.

---
STOP — Read-only research complete. No production promotion. No timers.
