# MATCH-EVAL-1567310-1 — Production Evaluation Report

**Task:** Register first real production ECSE hit  
**Mode:** Result Sync → Evaluation → Validation → Report  
**Environment:** Hetzner `/opt/worldcup-predictor`, `APP_ENV=production`  
**Date:** 2026-07-04

---

## Executive summary

Official evaluation registered for fixture **1567310** (Colombia vs Ghana) against the frozen production prediction. Provider confirmed **1-0 FT**. WDE 1X2/BTTS/O/U all **HIT**. ECSE Top1 **MISS** (2-0); Top3 and Top5 **HIT** with **correct rank = 2** (1-0). Frozen prediction unchanged. No odds refresh. Timers remain off.

**Final recommendation:** `FIRST_PRODUCTION_ECSE_EVALUATION_COMPLETE`

---

## Part A — Provider result verification

**Pipeline:** `run_production_prediction_pipeline.py --mode results-only` — success (2026-07-04 08:31 UTC)

| Check | Value |
|-------|-------|
| Status | **FT** |
| 90-min home | **1** |
| 90-min away | **0** |
| match_outcome_type | FT |
| penalty_score | null |
| final_score | 1-0 |
| finished_at | 2026-07-04T04:30:24Z |
| Source | production DB (`fixture_results`, outcome_source=local) |

No AET/PEN contamination. Provider confirms **1-0 FT** — evaluation proceeded.

---

## Part B — Evaluation

**Pipeline:** `run_production_prediction_pipeline.py --mode eval-only` — success (2026-07-04 08:32 UTC)

### WDE (90-minute)

| Market | Prediction | Outcome |
|--------|------------|---------|
| 1X2 Home Win | 57.3% | **HIT** (`market_1x2_status: correct`) |
| BTTS No | — | **HIT** |
| O/U Under 2.5 | — | **HIT** |

### ECSE (90-minute, snapshot_id=1)

| Tier | Frozen candidates | Outcome | Rank |
|------|-------------------|---------|------|
| Top1 | 2-0 | **MISS** | — |
| Top3 | 2-0, 1-0, 3-0 | **HIT** | **2** |
| Top5 | +4-0, 2-1 | **HIT** | **2** |

ECSE row: `top1_correct=0`, `top3_correct=1`, `top5_correct=1`, `rank_of_actual_score=2`

---

## Part C — Production records

| Check | Status |
|-------|--------|
| ECSE snapshot count | 1 (unchanged — original only) |
| ECSE evaluation created | Yes (id=1, single row) |
| Duplicate evaluation | No |
| WDE evaluation | Yes (`evaluation_source=production`) |
| Frozen `generated_at` | Unchanged (`2026-07-04T00:58:13Z`) |
| Payload hash | Unchanged (`07b841fc1025af28`) |
| Odds metadata at freeze | Preserved (`ODDS_FRESHNESS_UNKNOWN` in payload — not rewritten) |
| Operational stale context | STALE_ODDS, **7.44h** (audit; knockout threshold 6h) |
| Historical odds refresh | Not attempted (`odds_refresh_attempted: false`) |

### Production counts

| Metric | Count |
|--------|-------|
| Total ECSE snapshots | 1 |
| Evaluated ECSE snapshots | 1 |
| Pending ECSE snapshots | 0 |
| WDE stored predictions | 49 |
| WDE evaluated predictions | 35 |

---

## Part D — First production score-candidate evidence

See `FIRST_PRODUCTION_ENDRESULT_EVIDENCE.md`.

Raw ECSE ranks 1–3: 2-0 MISS · **1-0 HIT (rank 2)** · 3-0 MISS. Top3 **HIT**, Top5 **HIT**. WDE all **HIT**.

One fixture — no statistical proof or promotion claim.

---

## Part E — Production research counters

See `artifacts/match_eval/production_ecse_research_counters.json`.

| Counter | Value |
|---------|-------|
| production_ecse_predictions | 1 |
| production_ecse_evaluated | 1 |
| production_top1_hits | 0 |
| production_top3_hits | 1 |
| production_top5_hits | 1 |
| correct_rank_distribution.rank2 | 1 |
| correct_rank_distribution (rank1/3/4/5/miss) | 0 |

Fixture 1567310 contribution: Top1 miss · Top3 hit · Top5 hit · correct rank = 2.

---

## Part F — Validation

**Script:** `scripts/validate_match_eval_1567310_1.py`  
**Artifact:** `artifacts/match_eval/match_eval_1567310_1_validation.json`

Hetzner run: **30/30 checks passed** (`all_passed: true`).

Checks include: provider result confirmed · frozen prediction unchanged · no regeneration · WDE 1X2/BTTS/O/U correct · Top1 miss · Top3/Top5 hit · rank=2 · no duplicate eval · stale odds metadata preserved · no model code changes · timers disabled.

---

## Part G — Constraints honored

- Did **not** regenerate prediction
- Did **not** refresh historical odds
- Did **not** modify frozen prediction
- Did **not** change WDE or ECSE formulas
- Did **not** promote S5
- Did **not** enable timers

---

## Final recommendation

**`FIRST_PRODUCTION_ECSE_EVALUATION_COMPLETE`**

---

## Artifacts

| File | Purpose |
|------|---------|
| `FIRST_PRODUCTION_ENDRESULT_EVIDENCE.md` | Part D evidence |
| `MATCH_EVAL_1567310_1_PREMATCH_SNAPSHOT.md` | Frozen prematch |
| `artifacts/match_eval/production_ecse_research_counters.json` | Part E counters |
| `artifacts/match_eval/1567310_prematch_snapshot.json` | Machine-readable prematch |
| `artifacts/match_eval/match_eval_1567310_1_validation.json` | Validation output |
| `scripts/validate_match_eval_1567310_1.py` | Part F validation |
