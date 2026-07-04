# ECSE-RERANK-1 — Shadow Evaluation

## Comparison: Baseline ECSE vs Shadow Re-Rank

Finished matches: **13** (knockout-only in current DB)

| Metric | Baseline | Shadow | Delta |
|--------|----------|--------|-------|
| Top 1 exact hit | 15.4% | 23.1% | +7.7pp |
| Top 3 hit | 53.8% | 53.8% | +0.0pp |
| Top 5 hit | 76.9% | 76.9% | +0.0pp |
| Avg goal error (Top1) | 1.15 | 0.85 | -0.30 |
| Clean-sheet Top1 rate | 92.3% | 53.8% | -38.5pp |
| BTTS consistency | 45.5% | 90.9% | +45.4pp |
| O/U consistency | 63.6% | 81.8% | ++18.2pp |
| Winner direction preserved | 90.9% | 100.0% | ++9.1pp |

## Segments

- **Knockout**: same as all (13 matches) — no group-stage finished ECSE rows yet
- **Fresh odds**: 0 matches
- **Stale odds**: 13 matches
- **Unknown odds**: 0 matches

## AET/PEN

- 4 matches flagged AET or PEN
- Shadow evaluation compares against 90-minute score only

## Before / After Examples

### England vs Congo DR (fixture 1567307)

- Actual (90'): **2-1**
- Baseline Top 1: **2-0**
- Shadow Top 1: **2-0** (rank changed: False)
- Shadow Top 3: 2-0, 3-0, 1-0
- WDE: 1X2=home_win BTTS=no O/U=under_2_5

### Belgium vs Senegal (fixture 1567308)

- Actual (90'): **3-2**
- Baseline Top 1: **1-0**
- Shadow Top 1: **2-1** (rank changed: True)
- Shadow Top 3: 2-1, 1-0, 3-1
- WDE: 1X2=home_win BTTS=yes O/U=over_2_5

### Portugal vs Croatia (fixture 1567309)

- Actual (90'): **2-1**
- Baseline Top 1: **1-0**
- Shadow Top 1: **2-1** (rank changed: True)
- Shadow Top 3: 2-1, 1-0, 2-0
- WDE: 1X2=home_win BTTS=yes O/U=under_2_5

## Artifacts

- `artifacts/ecse_rerank_1_shadow_results.json`
- `artifacts/ecse_rerank_1_shadow_results.jsonl`
