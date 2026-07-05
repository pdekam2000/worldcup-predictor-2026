# RESULT-TRUTH-SCHEMA-V8-AND-ECSE-REEVALUATION-1 — Report

**Final recommendation:** `RESULT_TRUTH_V8_DEPLOYED_EVALUATIONS_CORRECTED`

---

## Executive summary

Schema v8 (regulation / AET / PEN columns) applied locally and on Hetzner production. Central evaluation score policy deployed via `evaluation_score_policy.py`. All 16 eligible frozen ECSE predictions re-evaluated against **regulation-time scores**. Two AET fixtures (Belgium, Argentina) corrected from post-ET aggregates to regulation truth. Local/production parity **16/16**.

---

## Task A — Result semantics forensic

Canonical terminology (see `schema_forensic.json`):

| Term | Storage | Meaning |
|------|---------|---------|
| REGULATION_SCORE | `regulation_home_goals` / `regulation_away_goals` | 90-minute score, excluding ET and penalties |
| FINAL_MATCH_SCORE | `home_goals` / `away_goals` | Provider aggregate after ET where applicable |
| PENALTY_SCORE | `penalties_*` or `penalty_score` | Shootout only |
| ADVANCING_TEAM | `qualified_team` | Winner after AET/PEN |
| result_resolution_type | derived from `final_stage` | FT→REGULATION, AET→EXTRA_TIME, PEN→PENALTIES |

**Pre-v8 bug:** AET fixtures evaluated exact-score against `home_goals`/`away_goals` (3-2) instead of regulation (2-2, 1-1).

---

## Task B — Schema v8

Migration via `worldcup_predictor/database/migrations.py` (`RESULT_TRUTH_REPAIR_1_COLUMNS`):

- `regulation_home_goals`, `regulation_away_goals`
- `extra_time_home_goals`, `extra_time_away_goals`
- `penalties_home_goals`, `penalties_away_goals`
- `final_stage`, `qualified_team`, `result_synced_at`

Non-destructive, idempotent ALTER TABLE. Legacy columns preserved. Schema version → **8**.

---

## Task C — Backfill

| Source | Rows |
|--------|-----:|
| Local FT/PEN inference (reg = home_goals where safe) | 5 |
| Production import from local canonical | 16 |

**AET audit (authoritative, not inferred):**

| Fixture | Final (AET) | Regulation | Qualified |
|---------|-------------|------------|-----------|
| Belgium vs Senegal (1567308) | 3-2 | **2-2** | Belgium |
| Argentina vs Cape Verde (1565179) | 3-2 | **1-1** | Argentina |

Provenance: `result_truth_backfill.jsonl`, `aet_pen_audit.json`

---

## Task D — Central evaluation score policy

Module: `worldcup_predictor/outcomes/evaluation_score_policy.py`

| Market | Score basis |
|--------|-------------|
| Exact score | REGULATION |
| 1X2, BTTS, O/U, Double chance | REGULATION |
| Qualification | ADVANCING_TEAM |
| Penalty winner | PENALTY_SCORE |

`FixtureOutcomeResolver` unified to always route through `regulation_fixture_outcome_fields`.

---

## Task E — ECSE re-evaluation

| Metric | Before | After | Delta |
|--------|-------:|------:|------:|
| Rank1 HR | 12.5% | 12.5% | 0 |
| Rank2 HR | 25.0% | 25.0% | 0 |
| Rank3 HR | 12.5% | 12.5% | 0 |
| Rank4 HR | 18.8% | 18.8% | 0 |
| Rank5 HR | 0% | 0% | 0 |
| Hit@3 | 50.0% | 50.0% | 0 |
| Hit@5 | 68.8% | 68.8% | 0 |
| MRR | 0.372 | 0.379 | +0.007 |

**Fixtures with corrected evaluation:**

| Fixture | Prior score | Regulation | Prev rank | New rank |
|---------|-------------|------------|----------:|---------:|
| Belgium vs Senegal | 3-2 | 2-2 | 12 | 10 |
| Argentina vs Cape Verde | 3-2 | 1-1 | null | 11 |

Top5 hit rate unchanged (both still miss Top5 at regulation score). Ranks and MRR corrected.

---

## Task F — WDE impact

WDE 1X2/BTTS/O/U already routes through `FixtureOutcomeResolver` → regulation scores. With v8 backfill, AET fixtures now resolve to regulation draws (Belgium 2-2 → draw, Argentina 1-1 → draw). No WDE prediction regeneration. See `wde_evaluation_impact.json`.

---

## Task G — Local/production parity

**16/16 fixtures OK** — regulation scores and ECSE hit ranks match.

---

## Task H — Historical replay contract

Machine-readable policy: `historical_replay_result_truth_contract.json`

Key rule: **exact-score evaluation target = regulation-time score only**.

---

## Task I — Validation

**21/21 checks passed** (`validation.json`)

---

## Artifacts

```
artifacts/result_truth_schema_v8_and_ecse_reevaluation_1/
```

## Scripts

- `scripts/run_result_truth_schema_v8_and_ecse_reevaluation_1.py`
- `scripts/validate_result_truth_schema_v8_and_ecse_reevaluation_1.py`
- `scripts/_apply_prod_v8_backfill.py`

---

## Final recommendation

**`RESULT_TRUTH_V8_DEPLOYED_EVALUATIONS_CORRECTED`**

Ready for ECSE historical replay backtesting with regulation-time evaluation labels.
