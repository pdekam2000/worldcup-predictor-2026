# FINAL DEEP FORENSIC REPORT

## 1. Executive summary

Deep forensic audit of the WorldCup Predictor platform against immutable frozen prematch predictions and FT90 results in `data/evaluation/forward_prediction_tracking.db`.

**Headline metrics (n=142 evaluated freezes with confirmed FT results):**

| Market | Hit rate | 95% bootstrap CI | n |
|--------|----------|------------------|---|
| Exact Top1 | **16.9%** | 10.6–23.2% | 142 |
| Exact Top3 | **31.0%** | 23.9–38.7% | 142 |
| Exact Top5 | **44.4%** | 35.9–52.8% | 142 |
| Exact Top10 | **76.1%** | 68.3–83.1% | 142 |
| WDE 1X2 | **49.3%** | 41.6–57.8% | 142 |
| BTTS | **47.9%** | 39.4–55.6% | 142 |
| O/U 2.5 | **53.5%** | 45.1–61.3% | 142 |

**Primary accuracy killers (evidence-backed):**

1. **Wrong WDE direction** drives 42 Exact Top5 misses — when 1X2 is wrong, score ranking rarely recovers.
2. **Goal underestimation** (27 cases) — lambdas too low vs actual totals; high-score (≥4 goals) tail Top5 rate is only **7.1%** (n=42).
3. **Rank calibration gap** — 39 fixtures have actual score in Top5 but not Top1 (mass/order wrong).
4. **Freeze metadata defect** — 1580/1785 ranking probabilities NULL; Top5 mass/entropy missing on 316/357 freezes even when payload `ecse.top10` held probabilities (**safe fix implemented for new freezes only**).
5. **Result sync gap** — 109 freezes still unresolved (no FT in eval DB); 62 fixtures have duplicate freezes.
6. **Odds columns mostly empty** on freezes (316/357) — blocks odds-profile segmentation; payload often lacks odds block too.

Production live commit was **not** verified (no SSH). Workspace was dirty at audit start. GPT Actions MCP server was in **error** state during this run.

## 2. Final audit status

`DEEP_FORENSIC_AUDIT_COMPLETE_WITH_SAFE_FIXES`

## 3–4. Commits / parity

- Audit branch: `audit/deep-model-forensic-20260730T115031Z`
- Base commit at branch create: `a1962d182309957c4ec79c7f51f6697295250706`
- Production deployed commit: **UNKNOWN** (no live SSH probe)
- GitHub source-of-truth: `origin/main` present; audit branch local-only until push
- See `environment_inventory.json`, `parity_matrix.json`

## 5–7. Freeze reconciliation

| Quantity | Count |
|----------|------:|
| Frozen predictions in eval DB | 357 |
| Unique fixtures with duplicate freezes | 62 |
| Actual FT results available | 142 |
| Successfully evaluated (earliest freeze × FT) | 142 |
| Unresolved / excluded (no FT) | 109 |
| Ranking rows with NULL probability | 1580 / 1785 |
| Predictions with any ranking probability | 41 / 357 |

Historical freezes were **not** rewritten. Evaluation prefers earliest freeze per fixture.

## 8–13. Global metrics

See `metric_summary.json`, `global_performance_summary.md`, `confidence_intervals.csv`, `calibration_tables.csv`, `confusion_matrices/`.

- Mean actual exact-score rank (when modeled in Top10): **4.76** (median 5)
- Outside Top10 / unmodeled: **23.9%**
- Goal MAE: home **1.05**, away **0.86**, total **1.43**, GD **1.31**

## 14–20. Segments & strategy signals

**Best Top5 leagues (n≥5):** europa_league 66.7% (n=6), primera_nacional 62.5% (n=16), virsliga 60% (n=5), conference_league 56.5% (n=23).

**Worst Top5:** world_cup_2026 0% (n=3, tiny), one_lyga 14.3% (n=7), one_deild 20% (n=10), urvalsdeild 28.6% (n=7).

**Timing:** early 24–72h slightly best Top5 (47.2%, n=36); mid 6–24h best WDE (56.2%, n=89); late <6h Top5 41.2% (n=17).

**Odds profiles:** nearly all evaluated rows lack freeze odds columns → segment unstable; treat as data-integrity issue first.

**Strategy frontier (research-only, tiny Tier S n=9):** Tier S Top5 55.6% / WDE 77.8%; No Bet Top5 53.8% (n=13) — **do not promote**; needs forward shadow.

**no_bet / consensus:** see CSVs — consensus column almost always null on freezes (354/357).

## 21. Exact-score root causes

| Class | Count |
|-------|------:|
| wrong_WDE_direction | 42 |
| in_top5_but_not_top1 | 39 |
| correct_direction_underestimated_goals | 27 |
| correct_direction_wrong_scoreline | 3 |
| correct_direction_overestimated_goals | 3 |
| high_score_tail_miss | 2 |
| model_limitation_or_upset | 1 |
| draw_or_0_0_miss | 1 |

Interpretation: ~half of Top5 misses are directional (WDE); among direction-correct misses, **under-scoring** dominates. When actual total goals ≥4, Top5 almost collapses (7.1%).

## 22–30. Code / completeness / data quality

Phase-1 scan (heuristic): incomplete markers **219**, hidden/fallback markers **214**, other review hits **987** — see CSVs (noise expected; triage CRITICAL via SAFE_FIX_LOG + ranking forensics).

Critical integrity findings:

- `_ecse_rank_rows` ignored top10 probabilities when top5 had null probs → null masses/entropy/ranking probs (**fixed for future freezes**).
- Duplicate freezes per fixture (62) — concurrent/owner/research paths.
- Odds/consensus rarely persisted on freeze rows.
- WDE probs stored as percent (e.g. 83.5) while ECSE ranking probs are fractions when present — unit inconsistency risk for any consumer that mixes them.
- Production / GPT Actions parity not live-verified; worldcup-predictor MCP discovery failed this run.

## 31–33. Safe fixes / tests

### Implemented (audit branch)

**FIX-001** — `worldcup_predictor/forward_evaluation/freeze_service.py`  
Backfill Top5 probabilities from `top_10_scorelines`; fall back to top10 when Top5 prob coverage < 3.  
Tests: `tests/forward_evaluation/test_ecse_rank_rows_prob_backfill.py` (3 new) + existing freeze suite.

Validation:

- `pytest tests/forward_evaluation/test_ecse_rank_rows_prob_backfill.py tests/forward_evaluation/test_freeze_service.py` → **33 passed**
- `pytest tests/forward_evaluation/` → **106 passed, 1 failed** (`test_timer_unit_not_enabled_by_default_in_repo` — **pre-existing** timer-unit comment expectation; unrelated to FIX-001)

No historical freezes mutated. No quality gates weakened. No production deploy.

## 34–38. Experiments / strategy / shadow

Registered challengers (not executed as canonical retrains): Dixon-Coles / low-score correction; rank calibration by league; dynamic tail mass; market-informed λ; selection strategy tiers.  
See `experiment_registry.csv`, `proposed_challenger_spec.md`, `proposed_strategy_rules.md`, `forward_shadow_plan.md`, `rejected_experiments.md`.

## 39. Production deployment recommendation

1. **Do not** promote model-formula changes from this audit.
2. **May** deploy FIX-001 after CI green + owner acknowledge (new freezes only; improves eval metadata).
3. Prioritize result-sync completion for 109 unresolved freezes and single-freeze-per-fixture enforcement.
4. Repair odds persistence into freeze columns before trusting odds-segment strategy.

## 40. Prioritized roadmap

### P0 — correctness / integrity
1. Deploy FIX-001 (rank prob backfill) after CI
2. Complete FT90 result sync for unresolved freezes (read-only reconcile first)
3. Enforce one canonical earliest freeze for evaluation; quarantine duplicates
4. Persist odds + freshness + consensus onto freeze rows when present in WSP
5. Document/enforce probability units (0–1 vs percent) at API boundary

### P1 — high-impact accuracy
1. Challenger: reduce under-scoring / expand high-goal tail (shadow)
2. Challenger: Dixon-Coles / low-score + rank calibration by league tier
3. Improve WDE/ECSE directional consistency (meta-layer, non-rewriting)
4. League promotion/demotion for chronically weak competitions (one_deild, one_lyga, WC friendlies)

### P2 — calibration & strategy
1. Forward-shadow selection tiers (Tier S/A/Watch/NoBet) — additive only
2. Uncertainty-aware no_bet using entropy + Top5 mass once masses are reliably populated
3. Reliability diagrams by market after odds columns repaired

### P3 — architecture
1. Training-serving skew monitors / artifact hashes
2. Job idempotency for freeze capture
3. GPT Actions / OpenAPI / production commit parity checks in CI

### P4 — research
1. Lineup/injury features when coverage stable
2. Odds-movement late-freeze models
3. Provider quality weighting

## Sub-statuses

- FREEZE_RECONCILIATION_STATUS: COMPLETE
- RESULT_SYNC_STATUS: PARTIAL (109 unresolved)
- EXACT_SCORE_AUDIT_STATUS: COMPLETE
- WDE_AUDIT_STATUS: COMPLETE
- BTTS_AUDIT_STATUS: COMPLETE
- OU_AUDIT_STATUS: COMPLETE
- MODEL_EXPERIMENT_STATUS: REGISTERED_NOT_EXECUTED
- SAFE_FIX_STATUS: FIX_001_IMPLEMENTED_LOCAL
- LOCAL_VALIDATION_STATUS: TARGETED_PASS_SUITE_1_PREEXISTING_FAIL
- GITHUB_PARITY_STATUS: BRANCH_LOCAL_ONLY
- PRODUCTION_PARITY_STATUS: UNKNOWN
- GPT_ACTIONS_PARITY_STATUS: UNKNOWN_MCP_ERROR
- FORWARD_SHADOW_READINESS: STRATEGY_SPEC_READY

## Primary status

DEEP_FORENSIC_AUDIT_COMPLETE_WITH_SAFE_FIXES
