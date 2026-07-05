# ECSE Historical Replay Backtest — ECSE-HISTORICAL-REPLAY-BACKTEST-1

**Generated:** 2026-07-04 22:51:09 UTC  
**Recommendation:** `ECSE_RELIABILITY_GATE_SIGNAL_FOUND`  
**Replay N:** 73,573 fixtures (2023-01-01 → latest completed eligible fixture)

---

## Executive Summary

Strict time-causal replay of the **current production ECSE odds-only path** (`external_row_to_ecse_odds_features → extract_lambdas → generate_score_distribution`) on **73,573** historical fixtures yields:

| Question | Answer |
| --- | --- |
| Rank1 exact-score hit rate | **12.713%** (95% CI 12.47–12.96%) |
| Rank2 hit rate | **10.962%** — Rank2 does **not** outperform Rank1 |
| Hit@5 | **50.283%** (95% CI 49.92–50.64%) |
| Rank order stable by year? | **Yes** — Rank1 is best rank in 2023, 2024, 2025, 2026 |
| Reliability gate useful? | **Yes** — HIGH_RELIABILITY OOS Hit@5 **53.4%** vs 49.66% overall (+3.74pp), 54.9% coverage |
| Frozen 16-fixture sample consistent? | **Partially** — Rank1 HR aligned (12.5% vs 12.7%); Hit@5 inflated in tiny frozen sample (68.75% vs 50.3%) |

No ECSE/WDE retraining, no production writes, no formula changes.

---

## Task A — Historical Data Inventory

**Source:** `external_historical_csv_raw_rows` (353,396 total rows)

| Metric | Count |
| --- | ---: |
| Fixtures from 2023-01-01 | 111,082 |
| Finished with valid FT scores | 111,082 |
| Prematch odds coverage (1X2) | 73,591 |
| ECSE lambda eligible | 73,573 |
| **Replay eligible** | **73,573** |

**Year breakdown (replay eligible):** 2023=17,619 · 2024=20,542 · 2025=22,000 · 2026=13,412

**Feature coverage notes:**

| Feature family | Coverage | Used in replay path |
| --- | --- | --- |
| Prematch 1X2 odds | 73,591 | Yes |
| OU/BTTS/DC odds (when present) | Partial | Yes (lambda extraction) |
| xG snapshots | 0 | No |
| Pressure | 0 | No |
| Standings / form / lineups / injuries | Not in CSV | No |

**Top competitions (replay eligible):**

| Competition | Finished | ECSE Eligible | Odds Coverage | Required Feature Coverage | Replayable |
| --- | ---: | ---: | ---: | ---: | ---: |
| EN2 | 2,483 | 1,903 | 1,903 | 1,903 | 1,903 |
| EN3 | 2,503 | 1,900 | 1,900 | 1,900 | 1,900 |
| EN4 | 2,508 | 1,898 | 1,899 | 1,898 | 1,898 |
| US1 | 2,102 | 1,740 | 1,740 | 1,740 | 1,740 |
| SP2 | 1,641 | 1,575 | 1,576 | 1,575 | 1,575 |
| Champions League | — | 814 | 814 | 814 | 814 |

Full inventory: `artifacts/ecse_historical_replay_backtest_1/historical_inventory.json`

---

## Task B — Eligibility & Temporal Causality

**Eligibility rule (documented before replay):**

1. `eventDate >= 2023-01-01`
2. Valid integer FT goals (home + away)
3. Valid prematch odds `oddsFT_1/X/2 > 1.0`
4. `extract_lambdas` succeeds on odds-only feature row
5. `generate_score_distribution` succeeds
6. Unique `row_hash` (deduplicated)

**Temporal causality audit:**

| Feature | Causality status |
| --- | --- |
| Odds | Prematch CSV closing line; no post-kickoff odds in source |
| Team form / rolling stats | Not used in odds-only ECSE path |
| xG / pressure / standings | Not used |
| Target match result | Used **only** for post-hoc evaluation |
| Lineups / injuries | Not available in source |

Audit artifact: `artifacts/ecse_historical_replay_backtest_1/temporal_causality_audit.json`

**Limitation:** CSV export lacks explicit odds timestamp; prematch timing assumed per export convention.

---

## Task C — Production-Path Replay

Each eligible fixture replayed through current ECSE generation path. Outputs stored in research artifact store only:

- `artifacts/ecse_historical_replay_backtest_1/replay_predictions.jsonl` (73,573 rows, ~130 MB)

Per-fixture fields: lambdas, full score distribution, Top1–Top10, probabilities, actual FT score, hit rank, Top5 HIT/MISS.

---

## Task D — Overall Rank Forensic

| Rank | Hits | Hit Rate | 95% CI | Expected | Calibration Δ |
| --- | ---: | ---: | --- | ---: | ---: |
| 1 | 9,353 | 12.713% | [12.47, 12.96] | 12.849% | -0.136pp |
| 2 | 8,065 | 10.962% | [10.74, 11.19] | 11.532% | -0.570pp |
| 3 | 7,206 | 9.794% | [9.58, 10.01] | 10.008% | -0.213pp |
| 4 | 6,633 | 9.016% | [8.81, 9.22] | 8.973% | +0.042pp |
| 5 | 5,738 | 7.799% | [7.61, 8.00] | 7.680% | +0.119pp |
| 6 | 5,229 | 7.107% | [6.92, 7.30] | 6.968% | +0.140pp |
| 7 | 4,539 | 6.169% | [6.00, 6.35] | 5.984% | +0.185pp |
| 8 | 3,585 | 4.873% | [4.72, 5.03] | 5.179% | -0.306pp |
| 9 | 3,459 | 4.701% | [4.55, 4.86] | 4.530% | +0.171pp |
| 10 | 3,047 | 4.141% | [4.00, 4.29] | 3.940% | +0.202pp |

**Rank comparisons (Rank B beats Rank A?):**

| Comparison | Rank A HR | Rank B HR | B beats A? |
| --- | ---: | ---: | --- |
| Rank1 vs Rank2 | 12.713% | 10.962% | **No** |
| Rank1 vs Rank3 | 12.713% | 9.794% | No |
| Rank1 vs Rank4 | 12.713% | 9.016% | No |
| Rank1 vs Rank5 | 12.713% | 7.799% | No |
| Rank2 vs Rank3 | 10.962% | 9.794% | No |
| Rank2 vs Rank4 | 10.962% | 9.016% | No |

**Conclusion:** Rank1 is the highest exact-score hit rate on this sample. The hypothesis that Rank2 outperforms Rank1 is **rejected** at scale (N=73,573).

---

## Task E — Cumulative Coverage (Hit@K)

| K | Hits | Rate | Marginal | 95% CI |
| --- | ---: | ---: | ---: | --- |
| Hit@1 | 9,353 | 12.713% | +12.713pp | [12.47, 12.96] |
| Hit@2 | 17,418 | 23.674% | +10.962pp | [23.37, 23.98] |
| Hit@3 | 24,624 | 33.469% | +9.794pp | [33.13, 33.81] |
| Hit@4 | 31,257 | 42.484% | +9.016pp | [42.13, 42.84] |
| Hit@5 | 36,995 | **50.283%** | +7.799pp | [49.92, 50.64] |
| Hit@10 | 56,854 | 77.276% | +26.992pp | [76.97, 77.58] |

---

## Task F — Year-by-Year Stability

| Year | N | Best Rank | Rank1 HR | Rank2 HR | Hit@3 | Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 17,619 | 1 | 12.941% | 11.340% | 34.088% | 50.752% |
| 2024 | 20,542 | 1 | 12.779% | 10.471% | 33.215% | 49.976% |
| 2025 | 22,000 | 1 | 12.809% | 11.086% | 33.791% | 50.764% |
| 2026 | 13,412 | 1 | 12.153% | 11.013% | 32.516% | 49.351% |

Rank1 advantage is **stable across all years**. Hit@5 ranges 49.4–50.8%.

---

## Task G — Competition Segments (N≥200)

Rank1 is best rank in the vast majority of competitions. Notable exceptions where another rank wins (small effect):

| Competition | N | Best Rank | Rank1 HR | Rank2 HR | Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| JP2 | 1,329 | **2** | 11.738% | 12.039% | 51.091% |
| US2 | 1,222 | **2** | 9.083% | 10.311% | 44.435% |
| TU1 | 1,178 | **2** | 11.630% | 11.715% | 49.576% |
| Champions League | 814 | 1 | 13.268% | 11.302% | 49.263% |
| AR1 | 1,465 | 1 | 14.812% | 14.608% | 63.003% |
| TN1 | 521 | 1 | 20.154% | 15.547% | 68.138% |

Full table: `ECSE_HISTORICAL_REPLAY_OWNER_REPORT.md` Table 3.

---

## Task H — Match Regime Analysis

| Regime | N | Best Rank | Rank1 HR | Hit@3 | Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: |
| medium_home_favorite | 27,764 | 1 | 13.481% | 34.844% | 51.729% |
| strong_home_favorite | 20,028 | 1 | 11.774% | 31.920% | 48.707% |
| medium_expected_goals | 54,877 | 1 | 13.038% | 34.031% | 51.009% |
| low_expected_goals | 5,558 | 1 | 14.034% | 35.642% | 52.357% |
| high_expected_goals | 13,138 | 1 | 10.154% | 27.371% | 41.848% |
| balanced_market | 5,005 | 1 | 13.986% | 34.006% | 50.929% |
| strong_away_favorite | 6,377 | 1 | 11.416% | 32.147% | 48.377% |

Rank1 remains dominant across odds and lambda regimes. High expected-goals regime shows lowest Hit@5 (41.85%).

---

## Task I — Top5 Hit vs Miss Forensic

| Metric | TOP5_HIT (N=36,995) | TOP5_MISS (N=36,578) |
| --- | ---: | ---: |
| Avg lambda_total | 2.789 | 2.894 |
| Avg top1_prob | 0.130 | 0.127 |
| Avg top5_mass | **0.516** | 0.505 |
| Avg entropy | **2.862** | 2.894 |
| Avg lambda_gap | 0.972 | 1.042 |

Top5 hits associate with **higher top5 probability mass** and **lower distribution entropy** — consistent with the reliability gate design.

---

## Task J — Reliability Gate Research

Chronological 70/30 split (train N=51,501 · test N=22,072). Thresholds fit on train only.

| Class | Coverage | N | Top1 | Hit@3 | Hit@5 | vs Overall Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HIGH_RELIABILITY | 54.9% | 12,117 | 13.36% | 35.49% | **53.40%** | **+3.74pp** |
| MEDIUM_RELIABILITY | 45.1% | 9,955 | 11.13% | 29.79% | 45.10% | -4.56pp |
| LOW_RELIABILITY | 0% | 0 | — | — | — | — |

Gate criteria met: HIGH materially exceeds OOS Hit@5, coverage non-trivial (54.9%), improvement persists in chronological test split.

---

## Task K — Rank Reranking Research (Walk-Forward OOS)

Test N=22,072. Pure reranking preserves Top5 membership (`membership_preserved: true`).

| Metric | Raw ECSE | A (global) | B (competition) |
| --- | ---: | ---: | ---: |
| Top1 accuracy | 12.36% | 12.36% | 11.92% |
| Hit@3 | 32.92% | 32.92% | 32.86% |
| Hit@5 | 49.66% | 49.66% | 49.66% |
| MRR | 0.2847 | 0.2847 | 0.2822 |

Global rank correction does not improve Top1. Competition correction slightly **hurts** Top1 with no Hit@5 gain. No actionable reranking signal.

---

## Task L — Frozen vs Replay Comparison

**Do not merge samples.**

| Dataset | N | Rank1 HR | Rank2 HR | Rank3 HR | Rank4 HR | Rank5 HR | Hit@3 | Hit@5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HISTORICAL_REPLAY | 73,573 | 12.713% | 10.962% | 9.794% | 9.016% | 7.799% | 33.469% | 50.283% |
| FROZEN_PREMATCH | 16 | 12.500% | 25.000% | 12.500% | 18.750% | 0.000% | 50.000% | 68.750% |

Frozen sample Rank1 HR is directionally consistent. Rank2/Hit@5 in frozen sample are **not** representative of large-scale replay (tiny-N noise).

---

## Task M & N — Leakage Audit & Validation

- **73,573 / 73,573** fixtures passed leakage checks
- Validation: **11/11 checks passed**
- No production writes, no retraining, no duplicate keys
- Top5 order matches probability order
- Rerank membership preserved

See `ECSE_HISTORICAL_REPLAY_LEAKAGE_AUDIT.md` and `artifacts/ecse_historical_replay_backtest_1/validation.json`

---

## Final Recommendation

**`ECSE_RELIABILITY_GATE_SIGNAL_FOUND`**

Rationale: While Rank1 order is confirmed at scale (rejecting Rank2 superiority), the shadow reliability gate identifies pre-match conditions (high top5 mass, low entropy, adequate data quality) where OOS Hit@5 improves by **+3.74pp** with **54.9%** coverage — the strongest actionable historical signal for shadow-only follow-up.

---

## Artifacts

```
artifacts/ecse_historical_replay_backtest_1/
├── historical_inventory.json
├── eligibility_report.json
├── temporal_causality_audit.json
├── replay_predictions.jsonl
├── rank_metrics.json
├── hit_at_k.json
├── yearly_stability.json
├── competition_metrics.json
├── regime_metrics.json
├── hit_vs_miss_forensic.json
├── reliability_gate_results.json
├── reranking_walk_forward.json
├── frozen_vs_replay_comparison.json
├── leakage_validation.json
└── validation.json
```

**Scripts:** `scripts/run_ecse_historical_replay_backtest_1.py` · `scripts/validate_ecse_historical_replay_backtest_1.py`
