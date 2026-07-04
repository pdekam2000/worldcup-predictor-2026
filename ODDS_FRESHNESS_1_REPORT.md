# ODDS-FRESHNESS-1 — Final Report

Phase: **ODDS-FRESHNESS-1** | Status: Complete — **DO NOT PROMOTE S5 / selectors**

## Final Recommendation: `DO_NOT_USE_STALE_ODDS_FOR_KNOCKOUT`

Validation: **25/25 passed** — `DO_NOT_USE_STALE_ODDS_FOR_KNOCKOUT`

---

## Executive Summary

Implemented a **central odds freshness policy**, **safe cache-first refresh runner**, **pipeline integration hooks**, and **metadata propagation** without changing WDE scoring, ECSE ranking formulas, or lambda retraining.

Impact analysis on **13 evaluated knockout ECSE fixtures (local research DB)** shows **100% STALE_ODDS** — Top3 53.8%, clean-sheet Top1 **92.3%**, BTTS/O-U consistency **46.2%** each. Fresh segment n=0; stale odds strongly correlate with clean-sheet bias and weak market alignment.

---

## PART A — Current System Audit

See `ODDS_FRESHNESS_1_AUDIT.md`.

| Metric (local DB) | Value |
|-------------------|------:|
| odds_snapshots rows | 2242 |
| Distinct fixtures | 901 |
| WC stale odds fixtures | 183 |
| WC fresh odds fixtures | 44 |
| WC missing odds | 1 |
| ECSE snapshots | 18 |
| WDE stored predictions | 185 |

**Quota risk:** Controlled via `--max-provider-calls` (default 20). No UI-triggered refresh.

---

## PART B — Freshness Policy

**Module:** `worldcup_predictor/odds/freshness_policy.py`

| Tier | Stale threshold |
|------|-----------------|
| Knockout | 6 hours |
| Normal upcoming | 12 hours |
| Low priority (>72h to kickoff) | 24 hours |

**Statuses:** `FRESH_ODDS`, `STALE_ODDS`, `ODDS_FRESHNESS_UNKNOWN`, `ODDS_MISSING`, `REQUIRES_FRESH_ODDS`

**API:** `calculate_odds_age_hours()`, `classify_odds_freshness()`, `should_refresh_odds()`, `explain_odds_freshness()`

Research wrapper `odds_freshness_meta()` in `ecse_rerank/features.py` now delegates to central policy (no formula change).

---

## PART C — Safe Refresh Runner

**Script:** `scripts/run_odds_freshness_refresh.py`

Dry-run (today's fixtures, local):

| Metric | Value |
|--------|------:|
| Fixtures scanned | 3 |
| Would refresh | 3 |
| Provider calls | 0 (dry-run) |
| DB writes | 0 |

**Artifacts:**
- `artifacts/odds_freshness/odds_freshness_refresh_report.json`
- `ODDS_FRESHNESS_1_LAST_RUN.md`

Controlled refresh mode respects `--max-provider-calls`; uses cache-first `import_daily_odds`.

---

## PART D — Pipeline Integration

**Updated files:**
- `scripts/run_production_prediction_pipeline.py` — flags: `--refresh-stale-odds`, `--max-odds-provider-calls`, `--strict-fresh-odds`
- `worldcup_predictor/owner/production_pipeline/runner.py`
- `worldcup_predictor/owner_daily/cycle.py`

**Default:** Safe — no refresh unless flag set; no strict blocking unless `--strict-fresh-odds`.

---

## PART E — Metadata Propagation

**Module:** `worldcup_predictor/odds/freshness_metadata.py`

WDE payloads now include (metadata only):
- `odds_freshness_metadata`
- `odds_freshness_status`, `odds_age_hours`, `odds_source`, `odds_snapshot_at`
- `requires_fresh_odds`, `odds_refresh_attempted/success/reason`

**UI:** `ecse_match_display.py` uses central policy for owner freshness warnings.

---

## PART F — Impact Analysis

See `ODDS_FRESHNESS_1_IMPACT_ANALYSIS.md`.

| Question | Answer |
|----------|--------|
| Stale odds vs Top3/Top5? | All 13 eval fixtures stale; Top3 53.8%, Top5 76.9% — cannot compare fresh |
| Clean-sheet bias? | **92.3%** clean-sheet Top1 on stale segment |
| O/U & BTTS errors? | **46.2%** consistency each on stale |
| Require fresh for knockout? | **Yes** — policy recommends ≤6h; use `--strict-fresh-odds` only when explicitly enabled |

---

## PART G — Validation

**Script:** `scripts/validate_odds_freshness_1.py`

Checks: policy math, dry-run no writes, max-provider-calls, pipeline flags, metadata stamping, WDE/ECSE formulas unchanged, timers off, reports exist.

---

## Production Safety

- No WDE core logic changes
- No ECSE ranking formula changes
- No S5/selector promotion
- No lambda retrain
- No timers enabled
- No uncontrolled provider calls
- Cache-first refresh only

---

## Recommended Next Step

1. Run `--refresh-stale-odds --max-odds-provider-calls 20` before daily knockout predictions.
2. Enable owner UI freshness warnings (already wired).
3. **KEEP_COLLECTING_EVALUATIONS** with fresh odds segment before promoting any re-rank/selector.
4. On Hetzner production: ECSE snapshots still absent — pair with ECSE backfill phase.

**STOP — No promotion. No timers.**
