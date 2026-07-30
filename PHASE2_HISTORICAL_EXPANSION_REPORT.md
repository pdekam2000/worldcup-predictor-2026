# PHASE 2 — Controlled Historical Expansion and Forward Cohort Bootstrap

**Status: COMPLETE (no promotion)**

Parity tip: local = GitHub = production = `03b504a`

---

## 1. Final phase status

Phase 2 completed successfully under promotion-safe constraints.

- Canonical freezes, WDE/ECSE predictions, rankings, and quality gates were not modified.
- Lambda V2 / Exact V2 remain shadow-only.
- Historical replay cohort fully processed for all inventory-eligible fixtures (n=94).
- True-forward inventory currently has **0** future-kickoff eligible freezes; Phase 1 hook remains active for new owner freezes.
- Staged execution: inventory → 15 → 50 → 29 → empty resume (0 remaining).

## 2. Exact historical eligibility counts

From production inventory (`20260730T181201Z`):

| Classification | Count |
|---|---|
| `eligible_historical_replay` | **94** |
| `eligible_true_forward` | **0** |
| `duplicate/already_processed` (later freeze per fixture) | 125 |
| `blocked_missing_result` | 96 |
| Other blocked classes in this scan | 0 |
| Total freeze rows scanned (owner scopes) | 315 |

Eligible historical by league (top): conference_league 45, champions_league 11, europa_league 9, allsvenskan 5, superettan 5, urvalsdeild 4, one_lyga 4, veikkausliiga 3, virsliga 3, a_lyga 3, one_deild 1, world_cup_2026 1.

By scope (all scanned rows): owner_shadow 172, production 141, owner_daily 2.

By kickoff date (eligible historical): 2026-07-23:46, 2026-07-19:16, 2026-07-20:12, 2026-07-21:9, 2026-07-22:9, 2026-07-18:1, 2026-07-14:1.

Artifacts:

- `/opt/worldcup-predictor/backups/infra_deploy/phase2_historical/20260730T181201Z/`
- Integrity: `/opt/worldcup-predictor/backups/infra_deploy/phase2_historical/phase2_integrity_347c9ab.json`

## 3. Historical replay count

**94 / 94** eligible historical fixtures shadowed successfully (cohort=`historical_replay`).

## 4. True-forward count

- Inventory eligible true-forward: **0** (no future kickoffs with valid freeze+result gate at inventory time).
- Phase 1 hook still wired for automatic true-forward on new eligible owner freezes.
- Job table total success includes Phase 1 smoke + historical backfill: **97** success fixtures (94 historical + 3 smoke). Failed job rows (**9**) are leftover Phase 1 smoke schema/thread failures from before Gate-0 upgrades — not Phase 2 batch failures.

## 5. Success / skipped / blocked / failed counts

| Stage | Processed | Success | Skipped | Blocked | Failed | Stopped |
|---|---|---|---|---|---|---|
| Stage 1 inventory | — | dry-run only | — | — | — | — |
| Stage 2 (batch 15) | 15 | 15 | 0 | 0 | 0 | none |
| Stage 2 idempotency re-run | 15 | 0 | 15 | 0 | 0 | none |
| Stage 3a (batch 50) | 50 | 50 | 0 | 0 | 0 | none |
| Stage 3b (batch 29) | 29 | 29 | 0 | 0 | 0 | none |
| Stage 4 resume (empty) | 0 | 0 | 0 | 0 | 0 | none |

## 6. Lambda V2 and Exact V2 rows written

Production FI DB shadow table `lambda_v2_shadow_outputs`:

- Lambda V2 rows: **400**
- Exact V2 rows: **400**
- Approx 8 model variants × (94 historical + 3 smoke + 3 smoke duplicate hash variants on Phase 1 only)

`l2f_shadow_evaluations` historical fixtures: **94** (distinct).

## 7. Evaluation metrics (challenger vs canonical)

Same-fixture cohort, historical_replay only (n=94). Canonical baseline = `market_evaluations.ecse_top5_hit`.

| Model | Top1 | Top3 | Top5 | Top10 | Log loss | MAE total | RMSE total | Canonical Top5 |
|---|---|---|---|---|---|---|---|---|
| EXACT_V2_SELECTED | 0.096 | 0.298 | **0.479** | 0.702 | 3.044 | 1.526 | 1.879 | **0.479** |
| LAMBDA_V2_BLENDED_ADAPTIVE | 0.096 | 0.298 | 0.479 | 0.702 | 3.044 | 1.526 | 1.879 | 0.479 |
| LAMBDA_V2_MARKET_TOTAL | 0.138 | 0.319 | 0.479 | 0.702 | 3.094 | 1.580 | 1.936 | 0.479 |
| LAMBDA_V2_FOOTBALL | 0.064 | 0.255 | 0.394 | 0.660 | 3.206 | 1.547 | 1.886 | 0.479 |

Mean actual-score rank (EXACT_V2_SELECTED): **8.26**.

### By league (EXACT_V2_SELECTED Top5 vs canonical)

Notable: conference_league 0.533 vs 0.533 (n=45); champions_league 0.545 vs 0.636 (n=11); urvalsdeild 0.25 vs 0.00 (n=4).

### By total-goal bucket (EXACT_V2_SELECTED)

| Bucket | n | Exact V2 Top5 | Canonical Top5 |
|---|---|---|---|
| 0–1 | 26 | 0.577 | 0.692 |
| 2 | 21 | 0.762 | 0.762 |
| 3 | 10 | 0.700 | 0.700 |
| 4+ | 37 | **0.189** | **0.108** |

High-scoring games remain the hard segment; Exact V2 shows a modest lift vs canonical on 4+ only in this small cohort (**non-promotion evidence**).

## 8. Historical vs true-forward metrics

- Historical_replay metrics: above (n=94).
- True-forward metrics: **N/A** (no eligible true-forward fixtures in inventory; no non-backfill evaluated rows yet).
- Combined metrics equal historical for now; labeled non-promotion evidence only.

## 9. Leakage and freeze-integrity proof

From `phase2_integrity_347c9ab.json`:

- Payload result-leakage issues: **0**
- Prematch boundary violations (`frozen_at >= kickoff`): **0**
- Freeze content hash before Stage 2 and after all batches: `6396c71e785ff8c77797b56351c38403ad500d9e02c42775d53c32ab17ad7528` (**unchanged**)
- Non-smoke duplicate shadow groups: **0**
- Known Phase 1 smoke duplicate fixtures only: `1497638`, `1508818`, `1508819` (different shadow hashes from two early successful attempts before job skip hardened)
- Idempotency: Stage 2 re-run → 15 skipped; Stage 4 empty batch → 0 processed
- Canonical freezes not rewritten; shadow writes only to FI shadow/job/eval tables

## 10. Disk usage before and after

Throughout Phase 2 production batches:

- Before / after each stage: `/dev/sda1  75G  62G  9.8G  87% /`
- Min-free gate: 8 GB (not breached)
- No large uncompressed FI backups created

## 11. Exact fixture IDs in pilot batches

**Stage 2 (15):**  
1494210, 1494212, 1494213, 1494214, 1494216, 1495736, 1495737, 1495738, 1497626, 1497627, 1497628, 1497629, 1497632, 1508810, 1508811

**Stage 3a (50):**  
1508812, 1508813, 1514236, 1515885, 1515886, 1515888, 1547591, 1547592, 1547593, 1554381, 1556382, 1556383, 1556384, 1556385, 1556501, 1556502, 1556503, 1556504, 1556509, 1556510, 1556511, 1556512, 1556513, 1556514, 1556515, 1556516, 1556517, 1556518, 1556520, 1556521, 1556522, 1556523, 1556524, 1556525, 1556543, 1556544, 1556545, 1556546, 1589417, 1589420, 1589427, 1589428, 1589429, 1589430, 1591866, 1591933, 1591934, 1591935, 1591936, 1591941

**Stage 3b (29):**  
1591942, 1591943, 1591944, 1591945, 1593475, 1593476, 1593477, 1593478, 1593479, 1593481, 1593482, 1593483, 1593484, 1593485, 1593487, 1593488, 1593489, 1593490, 1593491, 1593492, 1593493, 1593495, 1593496, 1593519, 1593520, 1593521, 1593522, 1593523, 1595191

## 12. Files modified

- `worldcup_predictor/research/infra_l2f_forward/historical_cohort.py`
- `worldcup_predictor/research/infra_l2f_forward/historical_replay.py`
- `worldcup_predictor/research/infra_l2f_forward/leakage_checks.py`
- `worldcup_predictor/research/infra_l2f_forward/true_forward_report.py`
- `worldcup_predictor/research/infra_l2f_forward/forward_hook.py` (prefer freeze lambdas for historical boundary)
- `scripts/run_l2f_historical_expansion.py`
- `scripts/report_l2f_phase2_integrity.py`
- `tests/research/infra_l2f_forward/test_historical_expansion.py`

## 13. Tests and validation results

- Local: `pytest tests/research/infra_l2f_forward` → **16 passed**
- Production Stage 1 inventory dry-run: OK
- Production Stage 2–4 batches: OK; freeze hash stable; services active
- Integrity report exit criteria: leakage=0, boundary=0, non_smoke_dups=0
- Service health after deploy `347c9ab`: `worldcup-api` / `worldcup-gpt-actions` **active**

## 14. Commit parity

| Location | SHA |
|---|---|
| Local | `03b504a` |
| GitHub (`release/football-strength-shadow-infra-20260730T151432Z`) | `03b504a` |
| Production `/opt/worldcup-predictor` | `03b504a` |

## 15. Explicit non-promotion statement

**No model promotion occurred.** Lambda V2 and Exact V2 remain shadow-only. Canonical WDE/ECSE outputs, freezes, rankings, UI surfaces, and quality gates were not replaced or relaxed.

## 16. Recommendation for next phase (do not start automatically)

**Recommended next phase (Phase 3 — evaluation deepening, still non-promotional):**

1. Continue true-forward accumulation via the live hook until n≥50–100 true-forward evaluated fixtures.
2. Add odds-bucket / balanced-vs-one-sided / confidence / consensus / no_bet / entropy / Top5-mass slices with locked prematch features only.
3. Harden unique constraint to `(fixture_id, model_id, model_version)` (after cleaning the 3 known smoke duplicate hash pairs).
4. Recover the 96 `blocked_missing_result` fixtures via DB-first result sync, then bounded replay only for newly completed ones.
5. Keep promotion gates closed until true-forward metrics confirm or refute the historical 4+ Top5 lift.

Do **not** start Phase 3 automatically.
