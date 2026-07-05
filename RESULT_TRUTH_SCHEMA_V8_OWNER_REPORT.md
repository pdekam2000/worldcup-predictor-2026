# Result Truth Schema v8 — Owner Report

**Recommendation:** `RESULT_TRUTH_V8_DEPLOYED_EVALUATIONS_CORRECTED`

---

## What changed

Schema v8 adds explicit **regulation / extra-time / penalty** columns to `fixture_results`. Evaluation now uses **90-minute regulation scores** for exact-score and standard prematch markets.

---

## The AET bug (fixed)

| Fixture | Was evaluating | Now evaluates |
|---------|------------------|---------------|
| Belgium vs Senegal | 3-2 (after ET) | **2-2** (regulation) |
| Argentina vs Cape Verde | 3-2 (after ET) | **1-1** (regulation) |

Post-AET scores remain stored in `home_goals`/`away_goals` for audit. They are **not** used for exact-score evaluation.

---

## Deploy status

| Environment | Schema | Backfill | ECSE re-eval |
|-------------|--------|----------|--------------|
| Local | v8 | 5 FT/PEN rows | 16 fixtures |
| Production (Hetzner) | v8 | 16 rows | 16 fixtures |

Local/production parity: **16/16**

---

## What was NOT changed

- No ECSE or WDE retraining
- No prediction regeneration or timestamp changes
- No authentic snapshot overwrites

---

## Next step

ECSE historical replay backtesting can proceed using `historical_replay_result_truth_contract.json` as the evaluation label policy.
