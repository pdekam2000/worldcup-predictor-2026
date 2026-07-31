# BET_COVERAGE_OPTIMIZER_PHASE4_FORWARD_SHADOW_AUDIT

## Final status

**`BET_COVERAGE_OPTIMIZER_PHASE4_FORWARD_SHADOW_READY`**

**NOT DEPLOYED**

| Item | Value |
|---|---|
| Branch | `feature/bet-coverage-optimizer-64-tickets` |
| Base Phase 3 | `262f706` |
| Tests | **67 passed** (`tests/research/bet_coverage_optimizer`) |
| Artifact path | `artifacts/coverage_optimizer/phase4_20260731T005312Z/` (gitignored) |
| Production deploy | **None** |

## What Phase 4 proved

Phase 4 added **no new betting logic**. It forensically audited Main + Insurance using real Interwetten markets (no ResearchBook) and measured Insurance effectiveness.

### Complete coupon failure (historical replay, 120 fixtures / 40 coupons)

| Metric | Value |
|---|---:|
| Main-only all-ticket-loss frequency | **0.575** |
| Main + Insurance all-ticket-loss frequency | **0.425** |
| Insurance reduces complete failure | **Yes** |
| Insurance saves (fixture-level) | 17 |
| Insurance effectiveness | 0.1417 |

### Coverage rates

| Strategy | Coverage rate |
|---|---:|
| Exact3 | 0.433 |
| Exact3 + Main | 0.717 |
| Exact3 + Main + Insurance | **0.858** |

### Real market validation

| Check | Result |
|---|---|
| Synthetic priced markets | **0** |
| Estimated priced markets | **0** |
| Priced coverage + insurance all real | **True** |
| Unpriced exact model legs | 9 (labeled `UNPRICED_MODEL_EXACT`, not fabricated) |

### Coupon recommendation (research sample, €400)

| Item | Value |
|---|---|
| Main tickets | 64 |
| Insurance tickets | 7 |
| Budget | €400 |
| Allocated | €398 |
| Modeled P(all main lose) | 0.0110 |
| Modeled P(main+ins both lose) | 0.0014 |

## Files changed (high level)

- `worldcup_predictor/research/bet_coverage_optimizer/phase4/` (audit, replay, forward shadow, reports, pipeline)
- `worldcup_predictor/research/bet_coverage_optimizer/market_semantics.py` (additive family mapping for Interwetten real-odds families only)
- `scripts/run_bco_phase4_research.py`
- `tests/research/bet_coverage_optimizer/test_phase4_forward_shadow.py`
- `docs/BET_COVERAGE_OPTIMIZER_PHASE4.md`
- this report

## Safety

- Canonical WDE/ECSE formulas unchanged
- Existing freezes unchanged
- Shadow models not promoted
- No schema migration
- Odds never fabricated
- Production **not** deployed

## Docs

See `docs/BET_COVERAGE_OPTIMIZER_PHASE4.md`.
