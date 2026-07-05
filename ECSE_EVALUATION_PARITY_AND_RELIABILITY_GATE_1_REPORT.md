# ECSE-EVALUATION-PARITY-AND-RELIABILITY-GATE-1 — Report

**Phase:** ECSE-EVALUATION-PARITY-AND-RELIABILITY-GATE-1  
**Date:** 2026-07-05  
**Final recommendation:** `ECSE_PARITY_RESTORED_NO_RELIABILITY_SIGNAL`

---

## Executive summary

Local canonical DB had **16** eligible finished ECSE evaluations; Hetzner production had **1** (Colombia vs Ghana only). Root cause was **missing production data**, not an evaluator bug: 14 authentic frozen ECSE snapshots and 15 FT result rows existed only locally from controlled prediction batches (2026-06-29 → 2026-07-01). After surgical import of canonical rows (original `generated_at`, no regeneration), production reached **16/16 parity** with full fixture intersection.

Reliability research on the legitimate n=16 dataset shows **68.8% Top5 hit rate** but **no stable OOS reliability gate** (test n=6; HIGH group n=1). Rank2 bias persists in MEDIUM reliability class (2/3 hits at rank 2).

---

## Task A — Local vs production eligibility forensic

### Counts

| Environment | Frozen ECSE snapshots | Eligible finished |
|-------------|----------------------:|------------------:|
| Local | 18 | **16** |
| Production (before repair) | 7 | **1** |
| Production (after repair) | 21 | **16** |

### Per-fixture parity table (pre-repair)

| Fixture | Local Eligible | Prod Eligible | Root Cause | Repairable? |
|---------|:--------------:|:-------------:|------------|:-----------:|
| Brazil vs Japan (1562344) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Netherlands vs Morocco (1562345) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| USA vs Bosnia (1562586) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Ivory Coast vs Norway (1564789) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Germany vs Paraguay (1565176) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| France vs Sweden (1565177) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Australia vs Egypt (1565178) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Argentina vs Cape Verde (1565179) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Mexico vs Ecuador (1567306) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| England vs Congo DR (1567307) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Belgium vs Senegal (1567308) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Portugal vs Croatia (1567309) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| **Colombia vs Ghana (1567310)** | yes | **yes** | OK | no |
| Spain vs Austria (1567311) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Switzerland vs Algeria (1567312) | yes | no | MISSING_PRODUCTION_ECSE | yes |
| Canada vs Morocco (1567824) | yes | no | MISSING_PRODUCTION_RESULT | yes |

**Dominant root cause:** `MISSING_PRODUCTION_ECSE` (14 fixtures). Canada additionally had ECSE on prod but `STATUS_NOT_FINAL` + no FT result row.

**Not observed:** `EVALUATOR_QUERY_BUG`, `TIMEZONE_NORMALIZATION_FAILURE`, `DUPLICATE_SNAPSHOT_SELECTION_FAILURE`, `FIXTURE_ID_MISMATCH`, `SNAPSHOT_AFTER_KICKOFF`.

Colombia had different snapshot timestamps (local Jul 1 batch vs prod Jul 4) but both pre-kickoff and eligible — existing prod snapshot retained per no-overwrite rule.

---

## Task B — Source of truth

| Mismatch class | Verdict |
|----------------|---------|
| 14× MISSING_PRODUCTION_ECSE | Local has valid canonical frozen snapshots absent from production — **promote authentic rows** |
| 15× fixture/result rows | Local has confirmed FT results from result-truth pipeline — **promote** |
| Canada (1567824) | Prod had ECSE + fixture but stale status `1H` — **update status + import result only** |
| Colombia (1567310) | Both environments eligible with different snapshots — **no action** |

Local data should be promoted; production was incomplete, not authoritative.

**Note:** Two AET fixtures (Belgium 1567308, Argentina 1565179) use **regulation scores** (2-2, 1-1) for local eligibility/evaluation. Production schema v7 lacks `regulation_*` columns; imported rows carry regulation fields but evaluator may fall back to `home_goals`/`away_goals` (3-2) on prod until schema v8 deploy. Eligibility parity is restored; evaluation score truth for AET matches may differ on prod until result-truth schema deploy.

---

## Task C — Safe parity repair

**Applied:** 2026-07-05 via `scripts/_import_ecse_parity_repair.py` on Hetzner.

| Action | Count |
|--------|------:|
| Fixtures inserted | 15 |
| Fixture status updates | 1 (Canada) |
| Results inserted | 15 |
| ECSE snapshots inserted | 14 |
| Evaluations run | 15 |

**Provenance:** `artifacts/ecse_evaluation_parity_and_reliability_gate_1/parity_repair_export.json` — SHA256 payload hashes per fixture, source `local_canonical_authentic_frozen_rows`.

**Forbidden actions avoided:** no model regeneration, no timestamp fabrication, no prediction content changes, no overwrite of existing Colombia ECSE.

---

## Task D — Parity validation (post-repair)

| Metric | Value |
|--------|------:|
| Local eligible | 16 |
| Production eligible | 16 |
| Intersection | 16 |
| Local-only | 0 |
| Production-only | 0 |

**Target met:** production parity with all legitimately eligible fixtures.

---

## Task E — Top5 reliability target

Dataset: n=16 legitimate eligible fixtures (local canonical, regulation-aware).  
**Target:** 1 if actual FT score ∈ ECSE ordered Top5, else 0.

Overall **Top5 hit rate: 68.8%** (11/16).

Pre-match features attached per fixture in `reliability_dataset.jsonl`: lambdas, cumulative Top3/5 probability, entropy, WDE confidence/alignment, favorite strength, BTTS/O/U lean, knockout stage.

---

## Task F — Hit vs miss forensic

| Feature | HIT mean | MISS mean | Difference | Evidence |
|---------|---------:|----------:|-----------:|----------|
| lambda_total | 2.588 | 2.747 | −0.159 | Hits in slightly lower-scoring regimes |
| lambda_gap | 1.228 | 1.764 | −0.536 | Larger lambda gaps associate with misses |
| top5_entropy | 1.981 | 1.981 | +0.001 | No separation |
| top1_prob | 0.151 | 0.169 | −0.017 | Misses slightly higher Top1 concentration |
| cum_top5_prob | 0.578 | 0.625 | −0.047 | Misses have higher Top5 mass (counterintuitive) |
| wde_confidence | 63.4 | 73.0 | −9.6 | Higher WDE confidence on misses |

No single feature cleanly separates hits from misses at n=16.

---

## Task G — Segment reliability

Segments with n≥3 (95% CI via bootstrap):

| Segment | N | Hits | Hit rate | 95% CI |
|---------|--:|-----:|---------:|--------|
| strong_favorite | 8 | 6 | 75.0% | [37.5%, 100%] |
| medium_favorite | 3 | 2 | 66.7% | [0%, 100%] |
| balanced | 4 | 3 | 75.0% | [25%, 100%] |
| medium scoring | 10 | 8 | 80.0% | [50%, 100%] |
| high scoring | 6 | 3 | 50.0% | [16.7%, 83.3%] |
| strongly_aligned | 9 | 6 | 66.7% | [33.3%, 100%] |
| mostly_aligned | 4 | 3 | 75.0% | [25%, 100%] |
| BTTS yes | 8 | 6 | 75.0% | [37.5%, 100%] |
| BTTS no | 6 | 4 | 66.7% | [33.3%, 100%] |
| Over 2.5 | 5 | 4 | 80.0% | [40%, 100%] |
| Under 2.5 | 9 | 6 | 66.7% | [33.3%, 100%] |

All CIs wide; no segment claims actionable reliability.

---

## Task H — Shadow reliability gate (OOS)

Chronological split: train n=10, test n=6.

Rule-based gate (train medians on cum_top5, entropy, WDE confidence + alignment score):

| Class | N (test) | Top5 hit | Top1 acc | Hit@3 |
|-------|---------:|---------:|---------:|------:|
| Baseline | 6 | 66.7% | 0% | 50.0% |
| HIGH_RELIABILITY | 1 | 0% | 0% | 0% |
| MEDIUM_RELIABILITY | 4 | 75.0% | 0% | 50.0% |
| LOW_RELIABILITY | 1 | 100% | 0% | 100% |

**Gate useful:** false (`gate_useful_oos: false`). HIGH group coverage trivial (n=1); no meaningful OOS improvement.

---

## Task I — Rank forensic by reliability class (test set)

| Class | Rank1 | Rank2 | Rank3 | Rank4 | Rank5 |
|-------|------:|------:|------:|------:|------:|
| MEDIUM | 0 | **2** | 0 | 1 | 0 |
| LOW | 0 | 0 | 1 | 0 | 0 |
| HIGH | 0 | 0 | 0 | 0 | 0 |

**Rank2 bias remains** in MEDIUM reliability (2/3 hits at rank 2). Insufficient sample to confirm or refute in HIGH/LOW.

---

## Task J — Validation checklist

| Check | Status |
|-------|--------|
| No future-result leakage | PASS |
| No regenerated historical predictions | PASS |
| All prediction timestamps authentic (pre-kickoff) | PASS |
| All actual scores confirmed (local regulation-aware) | PASS |
| Local/production parity table complete | PASS |
| Every production repair has provenance | PASS |
| Reliability features pre-match only | PASS |
| Chronological splits strict | PASS |
| No production model writes | PASS |
| No model retraining | PASS |
| No public publish | PASS |

Validator: **18/18 checks passed** (`artifacts/ecse_evaluation_parity_and_reliability_gate_1/validation.json`).

---

## Artifacts

```
artifacts/ecse_evaluation_parity_and_reliability_gate_1/
├── fixture_parity_audit.json
├── production_exclusion_reasons.json
├── parity_repair_export.json
├── parity_repairs.json
├── post_repair_parity.json
├── reliability_dataset.jsonl
├── hit_vs_miss_forensic.json
├── segment_reliability_metrics.json
├── shadow_reliability_gate.json
├── rank_by_reliability_class.json
├── validation.json
└── workflow.json
```

## Scripts

- `scripts/run_ecse_evaluation_parity_and_reliability_gate_1.py`
- `scripts/validate_ecse_evaluation_parity_and_reliability_gate_1.py`
- `scripts/_probe_ecse_parity_16ids.py` (production probe)
- `scripts/_import_ecse_parity_repair.py` (surgical import)

---

## Final recommendation

**`ECSE_PARITY_RESTORED_NO_RELIABILITY_SIGNAL`**

Parity restored (16/16). Reliability gate research inconclusive at current sample size; no production gate deployment recommended.
