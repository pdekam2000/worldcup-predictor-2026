# PHASE A23 — World Cup Goal Timing Reliability Upgrade

**Mode:** Audit → Blueprint → Validation  
**Date:** 2026-06-20  
**Status:** `BLUEPRINT_COMPLETE` · **A23B = `DEFERRED_READY`** — no deployment  
**Validation:** `scripts/validate_phase_a23_goal_timing_reliability.py` → **23/23 PASS**  
**Deferral decision:** [`PHASE_A23B_STATUS_DEFERRED.md`](PHASE_A23B_STATUS_DEFERRED.md) · Trigger check: `scripts/check_a23b_deferral_triggers.py`

---

## Executive summary

World Cup goal timing is **unreliable today** because:

1. **EGIE published predictions are Premier League only** — WC uses WDE `detailed_markets.first_goal` without six-bucket distributions.
2. **`goal_timing.range_probabilities` is absent** on all 48 stored WC predictions (local audit).
3. **`minute_range` vs `expected_minute` conflicts** affect 13/48 stored rows (e.g. `16-30` + `68'`).
4. **PredOps EGIE blocks are missing** for active WC fixtures locally; production has 94 snapshots but refresh policy does not meet the 15-minute active-fixture target.

This phase delivers an **isolated blueprint** (`worldcup_predictor/goal_timing/wc_reliability/`) and **EGIE_WC_GOAL_TIMING_ENGINE** design without modifying WDE, PL EGIE, scoring, calibration, billing, or subscriptions.

---

## 1. EGIE compatibility analysis (expanded)

### Competition matrix

| Competition | Registry key | EGIE allowed | EGIE published | Finished matches | Goal-event % | Compatibility |
|-------------|--------------|--------------|----------------|------------------|--------------|---------------|
| **World Cup 2026** | `world_cup_2026` | No | No | 5 | 0% | `WC_BLUEPRINT_ONLY` |
| **Euro** | `european_championship`* | No | No | 0† | — | `DATA_PARTIAL` |
| **Champions League** | `champions_league` | Yes | No | 90 | 67.8% | `ALLOWED_NOT_PUBLISHED` |
| **Europa League** | `europa_league` | Yes | No | 65 | 38.5% | `ALLOWED_NOT_PUBLISHED` |
| **Conference League** | `conference_league` | Yes | No | 65 | 83.1% | `ALLOWED_NOT_PUBLISHED` |
| **Premier League** (baseline) | `premier_league` | Yes | **Yes** | 380 | 97.1% | `PRODUCTION_EGIE` |

\* Euro is not registered as `euro_2024` in `COMPETITION_REGISTRY`. Sportmonks / feature-store key is `european_championship` (league 1326).  
† No finished fixtures stored under a Euro competition key locally.

### Key code boundaries (unchanged)

| Setting | Value | File |
|---------|-------|------|
| Published EGIE leagues | `("premier_league",)` only | `goal_timing/config.py` |
| Allowed feature leagues | PL, top-5, CL, EL, Eredivisie, Liga PT | `goal_timing/leagues.py` |
| PL engine | `EliteGoalTimingEngine` | `goal_timing/engine.py` |

**A23 decision:** WC/Euro/UEFA tournament timing must use **new** `EGIE_WC_GOAL_TIMING_ENGINE` (parallel module), not extend `GOAL_TIMING_PREDICTION_LEAGUE_KEYS`.

---

## 2. `goal_timing.range_probabilities` — schema & normalization

### Public API shape (A23)

```json
{
  "goal_timing": {
    "range_probabilities": {
      "0_15": 0.18,
      "16_30": 0.29,
      "31_45": 0.17,
      "46_60": 0.14,
      "61_75": 0.12,
      "76_90": 0.10
    }
  }
}
```

### Internal EGIE keys (unchanged for PL)

`0-15`, `16-30`, `31-45+`, `46-60`, `61-75`, `76-90+`

### Blueprint implementation

- `worldcup_predictor/goal_timing/wc_reliability/range_probabilities.py`
  - `normalize_range_probabilities()` — underscore public keys, renormalize if sum ≠ 1
  - `to_internal_range_probs()` — bridge to PL EGIE bucket math when needed

### Current state

| Source | `range_probabilities` present |
|--------|------------------------------|
| WC stored predictions (n=48) | **0 / 48** |
| PL EGIE engine output | In `match_first_goal_range_probs` (agent breakdown), not yet on WC payload |
| PredOps `egie` snapshot | Does not extract `range_probabilities` today |

---

## 3. Consistency validation rules

### A23 policy (blueprint)

| Condition | Result |
|-----------|--------|
| `expected_minute` ∉ `minute_range` | `prediction_status = INVALID` |
| Deviation from band midpoint **> 15 min** (within band) | `confidence_penalty = 30%` |
| Fields incomplete | `VALID` + reason `incomplete_timing_fields` |

### Blueprint module

`worldcup_predictor/goal_timing/wc_reliability/timing_consistency.py` → `validate_timing_consistency()`

Builds on existing `market_consistency_timing.py` (`expected_minute_in_band`, `band_for_expected_minute`) used by WDE consistency guard — **does not modify** that guard in this phase.

### Stored WC audit (local)

| Metric | Count |
|--------|-------|
| Total stored WC predictions | 48 |
| Missing `range_probabilities` | 48 |
| `prediction_status = INVALID` (A23 rules) | **13** |

Example conflicts: `minute_range=16-30`, `expected_minute=68` (fixtures 1489413, 1489414, 1489415).

---

## 4. PredOps coverage audit

### Local environment

| Metric | Value |
|--------|-------|
| `predops_snapshots` total | 0 |
| Active WC fixtures checked | 50 |
| Missing latest snapshot | **50** |
| Queue state | 12 fixtures queued (coverage report) |
| EGIE in PredOps | 12/12 `missing` |

### Production (reference — prior audit)

| Metric | Value |
|--------|-------|
| `predops_snapshots` | 94 |
| Scheduler cycle | ~1h (`next_run_estimate` +1h) |

### Refresh policy vs 15-minute target

From `predops/refresh_policy.py`:

| Hours to kickoff | Current TTL |
|------------------|-------------|
| ≤ 3h | **0.5h (30 min)** |
| ≤ 24h | 2h |
| ≤ 72h | 6h |

**Gap:** Target is **15 minutes** for active fixtures; policy allows 30 min minimum and scheduler runs ~hourly → snapshots can lag **30–60+ minutes** near kickoff.

### A23 PredOps recommendations (blueprint)

1. Add `ACTIVE_FIXTURE_REFRESH_MINUTES = 15` for `status IN (NS, 1H, HT, 2H, LIVE)` and kickoff ≤ 6h.
2. Run PredOps scheduler every **15 min** during WC match windows (cron/systemd).
3. Extend `build_egie_snapshot()` to include `range_probabilities` and `prediction_action`.
4. Alert when `egie_missing` > 20% of active window fixtures.

---

## 5. EGIE_WC_GOAL_TIMING_ENGINE — blueprint

Full design: [`worldcup_predictor/goal_timing/wc_reliability/egie_wc_engine_blueprint.md`](worldcup_predictor/goal_timing/wc_reliability/egie_wc_engine_blueprint.md)

### Summary

| Aspect | Design |
|--------|--------|
| Engine name | `EGIE_WC_GOAL_TIMING_ENGINE` |
| Scope | FIFA tournaments, national teams, UEFA club cups (read-only reuse of UEFA datasets) |
| Features | `intelligence/national_team/*`, tournament baselines, lambda bridge, xG (when present) |
| Output | Six-bucket `range_probabilities` + quality gate + abstention |
| Promotion | Shadow JSONL → validation → PredOps sidecar (no WDE math change) |

### Proposed module tree (future implementation)

```
worldcup_predictor/goal_timing/wc_engine/
  config.py
  feature_builder.py
  baseline_model.py
  engine.py
  adapter.py
  shadow_runner.py
```

---

## 6. Goal Timing Quality Gate

### Blueprint class

`GoalTimingQualityGate` in `worldcup_predictor/goal_timing/wc_reliability/quality_gate.py`

### Checks

| Check | Signal |
|-------|--------|
| `minute_range_consistency` | A23 timing validator |
| `expected_minute_consistency` | Same |
| `range_probabilities_present` | Six-bucket dict |
| `xg_present` | `xg` / `xg_intelligence` block |
| `lambda_present` | `lambda_home` + `lambda_away` |
| `over_under_present` | O/U market |
| `first_goal_team_present` | FG team |
| `egie_available` | EGIE / goal_timing status |

### Outputs

```json
{
  "data_quality": "HIGH | MEDIUM | LOW",
  "no_clear_edge": true,
  "prediction_action": "BET | LEAN | PASS",
  "checks": { "...": true },
  "reasons": ["timing_conflict", "missing_range_probabilities"]
}
```

### DATA_QUALITY thresholds (blueprint)

| Level | Criteria |
|-------|----------|
| **HIGH** | `data_quality_score ≥ 0.75`, range_probs present, ≥3 auxiliary signals |
| **MEDIUM** | Score ≥ 0.50 or partial signals |
| **LOW** | `INVALID` timing or score < 0.50 |

### NO_CLEAR_EDGE

`true` when top-two bucket probabilities differ by **< 8 pp** OR timing is `INVALID`.

---

## 7. Official abstention system

### Blueprint

`worldcup_predictor/goal_timing/wc_reliability/abstention.py` → `decide_prediction_action()`

| Action | When |
|--------|------|
| **PASS** | Timing conflict, LOW data quality, missing EGIE (non-HIGH), missing range_probs, no clear edge, model disagreement |
| **BET** | HIGH quality, valid timing, clear edge |
| **LEAN** | MEDIUM quality, valid timing, clear edge |

### PASS conditions (explicit)

- `timing_conflict`
- `low_data_quality`
- `missing_egie`
- `missing_range_probabilities`
- `model_disagreement`
- `bucket_probabilities_too_close`
- `high_timing_deviation` (optional soft PASS via LEAN suppression)

---

## 8. Implementation blueprint — phased rollout

### Phase A23b (implementation, post-approval)

| Step | Work | Risk |
|------|------|------|
| 1 | Wire `wc_reliability` gate into prediction **sidecar** adapter | Low |
| 2 | Implement `wc_engine` shadow runner | Low |
| 3 | Backfill national-team goal-minute history for WC/Euro | Medium |
| 4 | PredOps 15-min policy + EGIE snapshot fields | Medium |
| 5 | UI: show `prediction_action`, hide timing on PASS | Low |

### Phase A23c (promotion)

- Shadow replay vs finished WC matches
- Certify before surfacing BET labels to users

---

## 9. Migration impact analysis

### Database

| Table | Impact |
|-------|--------|
| `worldcup_stored_predictions` | **JSON payload only** — add optional `goal_timing.range_probabilities`, `prediction_status`, `prediction_action` keys. No schema migration required (SQLite JSON). |
| `goal_timing_predictions` (PostgreSQL) | New rows from WC engine use new `model_version`; PL rows unchanged. |
| `predops_snapshots` | `egie_json` column gains fields; backward compatible. |
| `prediction_lifecycle` | Optional capture of quality gate output. |

### API

| Endpoint | Change |
|----------|--------|
| `GET /api/predict/{id}` | Optional enriched `goal_timing` block (sidecar merge) |
| `GET /api/goal-timing/picks` | **No change** to PL picks |
| New (future) | `GET /api/goal-timing/wc/{fixture_id}` shadow read |

### Engines (explicitly NOT modified)

- `WeightedDecisionEngine`
- `EliteGoalTimingEngine` (PL)
- Scoring / calibration pipelines
- Billing / subscriptions

### Rollback

- Feature flag `WC_GOAL_TIMING_ENGINE_ENABLED=false`
- Remove sidecar merge; stored payloads remain valid without new keys

---

## 10. Validation framework

### Script

```bash
python scripts/validate_phase_a23_goal_timing_reliability.py
```

### Checks (23)

- EGIE compatibility per competition (6)
- PL-only published predictions preserved
- WC stored prediction audit (range_probs, invalid timing)
- PredOps table + 15-minute target documentation
- Blueprint module files exist
- Range probability schema normalization
- Consistency validator (INVALID / VALID paths)
- Quality gate PASS and BET paths
- WDE / PL EGIE unchanged

### Artifact

`artifacts/phase_a23_goal_timing_reliability_audit.json`

---

## 11. File index

| Path | Purpose |
|------|---------|
| `PHASE_A23_GOAL_TIMING_RELIABILITY_REPORT.md` | This report |
| `scripts/validate_phase_a23_goal_timing_reliability.py` | Validation runner |
| `worldcup_predictor/goal_timing/wc_reliability/` | Blueprint modules (isolated) |
| `worldcup_predictor/goal_timing/wc_reliability/egie_wc_engine_blueprint.md` | Engine design |
| `artifacts/phase_a23_goal_timing_reliability_audit.json` | Latest audit JSON |

---

## 12. Conclusion

Phase A23 establishes a **reliable path** for World Cup goal timing:

- **Do not** extend PL EGIE into WC prematurely.
- **Do** ship six-bucket probabilities, consistency validation, quality gate, and abstention as an isolated WC engine + sidecar.
- **Fix** PredOps refresh to 15 minutes for active fixtures before trusting live timing picks.

**Next step:** ~~Approve A23b implementation~~ **Deferred** — see [`PHASE_A23B_STATUS_DEFERRED.md`](PHASE_A23B_STATUS_DEFERRED.md). Re-open when `check_a23b_deferral_triggers.py` reports `REOPEN_ELIGIBLE`.

**Status:** `BLUEPRINT_AND_VALIDATION_COMPLETE` · `A23B_DEFERRED_READY` — no deploy.
