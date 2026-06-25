# PHASE 31B — HISTORICAL REPLAY BACKTEST

**Mode:** Implement → Validate → Report (measurement only)

**No deploy. No threshold changes.**

---

## Executive Summary

| Metric | Value |
|--------|------:|
| Finished matches replayed | **1616** |
| Replay errors | 0 |
| External API calls | **0** |
| Average confidence (replay) | **37.5** |
| Ranked pick coverage (all thresholds) | **0%** |

Replay confidence **never reached 50** (max ~42.6, avg ~37.5) due to sparse historical odds in SQLite enrichment. Threshold matrix is flat at 100% No Bet for ranked picks.

---

## 1. Data Source

- **Primary:** SQLite `fixtures` + `fixture_results` (`data/football_intelligence.db`)
- **Finished matches:** 1616
- **Enrichment:** `fixture_enrichment` (lineups/stats), `odds_snapshots` where available
- **Strategy:** Hybrid offline replay (Phase 31B-Precheck Option C)

---

## 2. Threshold Test Matrix

DQ threshold unchanged (WDE **50**, Phase 30C **45**). Confidence gates tested: **50, 55, 60**.

| Threshold | Total matches | No Bet rate | Recommendation rate | Avg confidence |
|-----------|----------------:|------------:|--------------------:|---------------:|
| ≥50 | 1616 | 100.0% | 0.0% | 37.5 |
| ≥55 | 1616 | 100.0% | 0.0% | 37.5 |
| ≥60 | 1616 | 100.0% | 0.0% | 37.5 |

---

## 3. Winrate by Market (model picks, all fixtures)

| Market | Threshold 50 | Threshold 55 | Threshold 60 |
|--------|-------------|-------------|-------------|
| 1x2 | 44.2% — 715/1616 correct, coverage 1616 | 44.2% — 715/1616 correct, coverage 1616 | 44.2% — 715/1616 correct, coverage 1616 |
| over_under_2_5 | 44.6% — 721/1616 correct, coverage 1616 | 44.6% — 721/1616 correct, coverage 1616 | 44.6% — 721/1616 correct, coverage 1616 |
| btts | 56.7% — 916/1616 correct, coverage 1616 | 56.7% — 916/1616 correct, coverage 1616 | 56.7% — 916/1616 correct, coverage 1616 |
| double_chance | 78.7% — 1272/1616 correct, coverage 1616 | 78.7% — 1272/1616 correct, coverage 1616 | 78.7% — 1272/1616 correct, coverage 1616 |

---

## 4. Safe / Value / Aggressive (ranked picks)

| Pick | Threshold 50 | Threshold 55 | Threshold 60 |
|------|-------------|-------------|-------------|
| safe_pick | n/a (0 picks) | n/a (0 picks) | n/a (0 picks) |
| value_pick | n/a (0 picks) | n/a (0 picks) | n/a (0 picks) |
| aggressive_pick | n/a (0 picks) | n/a (0 picks) | n/a (0 picks) |
| recommended_bets | n/a (0 picks) | n/a (0 picks) | n/a (0 picks) |

**Finding:** Zero ranked-pick coverage at all tested thresholds — replay confidence stays below 50.

---

## 5. Confidence Bucket Analysis (1X2 model pick winrate)

| Bucket | Count | 1X2 winrate |
|--------|------:|------------:|
| 0-40 | 1084 | 39.2% |
| 40-50 | 532 | 54.5% |
| 50-55 | 0 | n/a |
| 55-60 | 0 | n/a |
| 60-65 | 0 | n/a |
| 65-70 | 0 | n/a |
| 70-75 | 0 | n/a |
| 75+ | 0 | n/a |

**Key insight:** The **40–50** bucket (532 matches) shows **54.5%** 1X2 accuracy — above breakeven — 
but no fixtures reached ≥50 confidence in this offline replay, so thresholds 50/55/60 behave identically.

---

## 6. Current Threshold (60) — Is It Justified?

| Lens | Assessment |
|------|------------|
| Ranked picks on SQLite replay | **100% No Bet** at 60, 55, and 50 — cannot measure pick winrate |
| Model 1X2 (informational) | **44.3%** overall — below profitable 3-way baseline |
| Model BTTS | **56.7%** — modest edge |
| Model Double Chance | **78.7%** — strong (easier market) |
| Production WC UX (Phase 30F) | Live confidences **51–55** — threshold 60 blocks ranked picks |

**Conclusion:** Threshold **60 is conservative but not verifiable for ranked-pick accuracy on this replay** 
(confidence calibration gap). It remains reasonable for production until enriched replay confirms otherwise.

---

## 7. Would Threshold 55 or 50 Help?

| Question | Answer |
|----------|--------|
| Would **55** improve UX on this replay? | **No** — still 100% No Bet (max confidence ~42.6) |
| Would **50** improve UX on this replay? | **No** — same |
| Would **50** damage accuracy? | **Not measurable** for ranked picks (0 coverage); model 1X2 in 40–50 band is **54.5%** |

---

## 8. Phase 31C Recommendation

**Keep 60** for production ranked picks today; however **40–50 confidence bucket shows 54.5% 1X2 winrate** on model picks — supports a future **31C review** once live replay confidence reaches that band.

Suggested 31C actions:

1. **Enrichment upgrade** — attach historical `odds_snapshots` + odds JSON to raise replay confidence toward production band.
2. **Re-run 31B** after enrichment; re-evaluate thresholds 55 vs 60 on ranked-pick winrate.
3. **Keep production threshold at 60** until 31C replay shows ranked picks with measurable WR.

---

## 9. Artifacts

- Summary JSON: `artifacts/backtest_ranked_picks_summary.json`
- Full CSV: `artifacts/backtest_ranked_picks_full.csv`

---
