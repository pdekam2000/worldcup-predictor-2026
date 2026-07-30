# PHASE 3 — Parity Alignment + True-Forward Accumulation + Result Recovery

**Status: COMPLETE (no promotion)**

## 1. Final Phase 3 status

Phase 3 completed under promotion-safe constraints.

- Production parity restored to source tip, then Phase 3 code deployed.
- All unique missing-result freezes recovered and evaluated in the recovered cohort.
- True-forward hook remains active; inventory still shows **0** live true-forward jobs with `run_id=l2f-forward-v1`.
- Deep-slice + prematch high-goal detector research artifacts generated.
- Lambda V2 / Exact V2 remain shadow-only.

## 2. Parity result and final commit hashes

### Stage 1 parity (`757500a` → `bab0cf9`)

Diff was **docs-only**:

- Single file: `PHASE2_HISTORICAL_EXPANSION_REPORT.md` (+7 / −4)
- No runtime, model, schema, or prediction-path changes

Production updated to `bab0cf9` without replaying Phase 2 batches.

### Final tip after Phase 3 implementation

| Location | SHA |
|---|---|
| Local | `161f3be` (+ report commit below if present) |
| GitHub (`release/football-strength-shadow-infra-20260730T151432Z`) | same tip as local |
| Production `/opt/worldcup-predictor` | `161f3be` at recovery completion |

Health after alignment/deploy:

- `worldcup-api`: active
- `worldcup-gpt-actions`: active
- `nginx`: active
- API OpenAPI: HTTP 200 on `127.0.0.1:8000/openapi.json`
- Canonical λ regression report remains **PASS** (unchanged freeze hash)

## 3. Inventory of missing-result freezes

Phase 2 classification counted **96 freeze rows** with `blocked_missing_result`.

Phase 3 unique-fixture inventory (first ACTIVE freeze per fixture, valid prematch boundary, missing `actual_results`):

| Metric | Count |
|---|---|
| Unique fixtures missing results | **46** |
| After full recovery | **0** remaining |

By competition (initial 46): eliteserien 9, allsvenskan 8, veikkausliiga 6, superettan 6, urvalsdeild 5, one_lyga 5, one_deild 4, virsliga 2, a_lyga 1.

By kickoff date: 2026-07-26:20, 2026-07-25:11, 2026-07-27:6, 2026-07-24:6, 2026-07-22:2, 2026-07-23:1.

Artifact: `/opt/worldcup-predictor/backups/infra_deploy/phase3/20260730T192752Z/missing_result_inventory.json`

## 4–6. Recovery classifications

All 46 unique fixtures were recovered via **provider fallback** (production `fixture_results` were empty / status `NS`).

| Classification | Count |
|---|---|
| `result_recovered_provider` | **46** |
| `result_recovered_db` | 0 |
| `result_already_present` | 0 (except mid-run reuse after sync) |
| `fixture_not_finished` | 0 (after env fix) |
| `postponed_or_cancelled` | 0 |
| `provider_unavailable` | 0 (after env fix) |
| `ambiguous_fixture_identity` | 0 |
| `conflicting_result` | 0 |
| `permanently_unresolved` | 0 |

Note: first pilot without `APP_ENV=production` misclassified 15 as `fixture_not_finished` because provider credentials were not loaded. Fixed in `161f3be` (`APP_ENV=production` when `.env.production` exists). Re-run succeeded.

### Bounded batches

| Batch | Processed | Recovered provider | Shadow generated | Evaluated |
|---|---|---|---|---|
| Pilot (15) | 15 | 15 | 15 | 15 |
| Medium (20) | 20 | 20 | 17* | 20 |
| Final (10) | 10 | 10 | 10 | 10 |
| Orphan fix 1494217 | 1 | (already synced) | 1 | 1 |

\*3 smoke fixtures already had shadow rows (`1497638`, `1508818`, `1508819`).

## 7. Newly evaluated shadow fixtures

- Cohort `historical_replay_result_recovered`: **46** distinct fixtures
- Prior cohort `historical_replay`: **94** (unchanged)
- True-forward evaluated: **0**

## 8. Updated historical metrics

`historical_replay` (n=94) unchanged vs Phase 2:

| Model | Top5 | Canonical Top5 | MAE total | RMSE total |
|---|---|---|---|---|
| EXACT_V2_SELECTED | 0.479 | 0.479 | 1.526 | 1.879 |
| LAMBDA_V2_BLENDED_ADAPTIVE | 0.479 | 0.479 | 1.526 | 1.879 |

`historical_replay_result_recovered` (n=46):

| Model | Top1 | Top3 | Top5 | Top10 | MAE | RMSE |
|---|---|---|---|---|---|---|
| EXACT_V2_SELECTED | 0.130 | 0.326 | 0.435 | 0.783 | 1.509 | 1.817 |

Canonical Top5 comparison is mostly unavailable in this recovered subset (`market_evaluations` missing for many freezes) — do **not** treat recovered-only Top5 as promotion evidence.

## 9. True-forward cohort

- Discovered / success / evaluated: **0 / 0 / 0**
- Hook remains active (Phase 1)
- Reporting command: `scripts/report_l2f_true_forward.py`

## 10. Deep-slice comparison (research only)

Combined evaluated Exact V2 SELECTED rows used for slices: historical + recovered (**n≈140**).

### Outcome-defined (NOT for routing)

| Slice | n | Exact V2 Top5 | Canonical Top5 |
|---|---|---|---|
| actual 0–1 | 39 | 0.564 | 0.692 |
| actual 2–3 | 52 | 0.692 | 0.742 |
| actual 4+ | 49 | **0.143** | **0.108** |

Flagged in artifacts as `OUTCOME_DEFINED_SLICE_NOT_FOR_ROUTING`.

### Prematch-observable expected-total buckets

| et_bucket (prematch λ total) | n | Exact V2 Top5 | Canonical Top5 | Exact Wilson 95% |
|---|---|---|---|---|
| 2.0–2.5 | 11 | 0.636 | 0.778 | [0.35, 0.85] |
| 2.5–3.0 | 59 | 0.508 | 0.513 | [0.38, 0.63] |
| ≥3.0 | 70 | 0.400 | 0.391 | [0.29, 0.52] |

Uplift at `et≥3.0` is tiny (~+0.9pp) and **not** promotion evidence.

Odds balanced slice was unavailable (`odds_home/away` mostly null on freezes → balanced=None for all).

## 11. Prematch high-goal detector (research only)

Stored as research artifact: `.../high_goal_detector_research.json`

Train cohorts: historical + recovered. True-forward holdout: reserved (n=0 available).

| Rule | n | Coverage | Precision (actual 4+) | Recall | Challenger Top5 uplift |
|---|---|---|---|---|---|
| `et_gte_2_75` | 102 | 73% | 0.373 | 0.776 | ≈0.0 |
| `et_gte_3_0` | 70 | 50% | 0.457 | 0.653 | ≈+0.009 |
| `et_gte_2_75_and_tail` | 0 | — | insufficient | — | — |
| `et_gte_2_75_balanced` | 0 | — | insufficient (no odds) | — | — |

**Not activated** in canonical routing.

## 12. Proof: final goals not used as routing input

- Detector predicates use only `expected_total_lambda`, optional freeze-time ECSE tail mass, and optional balanced odds.
- `actual_total_goals` is used only after selection to score precision/recall.
- Artifact field: `proof_no_final_goals_in_inputs=true`, `routing_activated=false`.

## 13. Freeze / canonical integrity

- Freeze content hash before/after all recovery batches: `6396c71e785ff8c77797b56351c38403ad500d9e02c42775d53c32ab17ad7528`
- `freeze_unchanged: true` on every apply batch
- Freezes not rewritten; results written only to `actual_results` / `fixture_results`
- Shadow writes only to FI shadow / jobs / `l2f_shadow_evaluations`

## 14. Disk usage

Before/after every batch: `/dev/sda1  75G  62G  9.8G  87% /`  
Min-free gate 8G never breached. No large uncompressed DB backups.

## 15. Files modified

- `worldcup_predictor/research/infra_l2f_forward/result_recovery.py`
- `worldcup_predictor/research/infra_l2f_forward/deep_slices.py`
- `worldcup_predictor/research/infra_l2f_forward/high_goal_detector.py`
- `worldcup_predictor/research/infra_l2f_forward/true_forward_report.py`
- `scripts/run_l2f_phase3_result_recovery.py`
- `scripts/report_l2f_true_forward.py`
- `tests/research/infra_l2f_forward/test_result_recovery.py`
- `PHASE3_RESULT_RECOVERY_REPORT.md` (this file)

## 16. Tests and validation

- Local: `pytest tests/research/infra_l2f_forward` → **20 passed** (includes result classification, cohort separation, detector leakage-input check)
- Production: parity docs-only deploy; recovery pilot 15/15; medium 20/20; final 10/10; orphan 1494217 fixed
- Inventory after completion: **0** missing
- Services active; OpenAPI 200
- Cohorts remain separate in `l2f_shadow_evaluations`

## 17. Explicit non-promotion statement

**No model promotion occurred.** Lambda V2 and Exact V2 remain shadow-only. Canonical WDE/ECSE outputs, freezes, rankings, UI, and quality gates were not replaced or relaxed. The prematch high-goal detector is research-only and not wired into production decision logic.

## 18. Recommendation for Phase 4 (do not start automatically)

1. Accumulate true-forward freezes until n≥50–100 evaluated.
2. Persist prematch 1X2 odds onto freeze envelopes so balanced/favorite slices become usable.
3. Recompute recovered-cohort canonical Top5 by evaluating ECSE from immutable freeze payloads (without regenerating freezes).
4. Only then revisit whether `et≥3.0` (or a refined prematch gate) deserves a **shadow** routing experiment — still not promotion.

Do **not** start Phase 4 automatically.
