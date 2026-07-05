# BRAZIL-NORWAY-CONTROLLED-PREDICTION-1 — Report

**Date:** 2026-07-04  
**Environment:** Hetzner `/opt/worldcup-predictor`, `APP_ENV=production`  
**Production commit (post pipeline fixes):** `282ef70`

---

## Executive summary

Controlled WDE + ECSE prediction created and frozen for **Brazil vs Norway** (fixture **1568100**). Odds refresh succeeded (3 markets); DB shows **FRESH_ODDS**. WDE payload metadata stamped **ODDS_MISSING** at freeze time — documented as odds warning. ECSE snapshot **id=4** with exactly 3 Top3 candidates. Colombia, Canada, and Paraguay predictions unchanged.

**Final recommendation:** `BRAZIL_NORWAY_PREDICTION_WITH_ODDS_WARNING`

---

## Part A — Synchronized production state

| Check | Result |
|-------|--------|
| HEAD (start) | `b512e0b` |
| origin/main | match |
| worldcup-api | active |
| nginx | active |

Pipeline hotfixes applied during task (import path + DailyFixture season) — commits `6b5d5f2`, `282ef70`. No WDE/ECSE formula changes.

---

## Part B — Existing snapshot baseline

See `BRAZIL_NORWAY_CONTROLLED_PREDICTION_1_BASELINE.md`.

Confirmed 3 prior snapshots: Colombia (evaluated), Canada, Paraguay (pending). Brazil had none.

---

## Part C — Fixture discovery

| Field | Value |
|-------|-------|
| fixture_id | **1568100** |
| Match | Brazil vs Norway |
| Kickoff UTC | 2026-07-05T20:00:00 |
| Kickoff Vienna | 2026-07-05 22:00 CEST |
| Round | Round of 16 |
| Status | NS |
| Pre-run WDE/ECSE | none |

---

## Parts D–E — Odds audit and refresh

| Step | Result |
|------|--------|
| Audit before | ODDS_MISSING · would_refresh=1 |
| Refresh dry-run | would_refresh=1 · bounded |
| Refresh real | **refreshed=3** markets |
| Audit after (DB) | snapshot 2026-07-04T09:07:13 · FRESH_ODDS · live |

Markets refreshed via provider (bounded, single fixture).

---

## Part F — Prediction dry-run

- Exactly **one** fixture targeted (1568100)
- WDE would generate · ECSE skipped in dry-run (missing_odds pre-refresh path)
- No Colombia / Canada / Paraguay regeneration
- Provider calls bounded

**Result:** safe (not `PREDICTION_DRY_RUN_UNSAFE`)

---

## Part G — Controlled real prediction

| Field | Value |
|-------|-------|
| Pipeline exit | 0 |
| WDE stored | yes |
| ECSE stored | yes (snapshot id=4) |
| generated_at | 2026-07-04T09:07:14Z |

---

## Part H — Frozen output

### WDE

| Field | Value |
|-------|-------|
| 1X2 | Home (Brazil) |
| Confidence | 52.1% |
| BTTS | Yes |
| O/U 2.5 | Over |
| Engine | 34b-v1 |
| Payload hash | `f08d0b93637b8f2a` |

### ECSE

| Tier | Scores |
|------|--------|
| Top1 | 2-0 |
| Top3 | 2-0 · 1-0 · 2-1 |
| Top5 | +1-1 · 3-0 |
| Model | ECSE-LIVE-1\|ECSE-1C-v1\|ECSE-1D-B-v1 |
| Frozen | yes |

### Odds metadata (WDE payload)

- **odds_freshness_status:** ODDS_MISSING
- **odds_snapshot_at:** null in payload
- DB post-refresh: FRESH_ODDS at 09:07:13 UTC

---

## Part I — Cross-market consistency

| Check | Result |
|-------|--------|
| WDE ↔ ECSE direction | Aligned (home wins) |
| BTTS Yes vs Top3 | Mixed — includes clean sheets and 2-1 |
| O/U Over vs Top3 | **CROSS_MARKET_VARIANCE_CANDIDATE** (1-0 = 1 goal) |
| Draw diversification | 1-1 in Top5 |
| Clean-sheet concentration | Not flagged (BTTS=Yes) |

---

## Part J–K — Owner artifacts

- `BRAZIL_NORWAY_CONTROLLED_PREDICTION_1_OWNER_SUMMARY.md`
- `CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md`

---

## Part L — Production counters

| Metric | Before | After |
|--------|-------:|------:|
| WDE stored | 51 | **52** |
| ECSE snapshots | 3 | **4** |
| ECSE pending | 2 | **3** |

---

## Part M — Validation

Script: `scripts/validate_brazil_norway_controlled_prediction_1.py`  
Run on Hetzner — **22/22 checks passed** (`all_passed: true`).

---

## Pipeline fixes (infrastructure only)

1. `freshness_refresh.py`: import `DailyFixture` from `fixture_discovery`
2. `freshness_refresh.py`: pass `season` when building fallback fixture

No WDE/ECSE ranking formula changes.

---

## Final recommendation

**`BRAZIL_NORWAY_PREDICTION_WITH_ODDS_WARNING`**

Prediction frozen with full ECSE Top3/Top5. WDE payload odds metadata shows ODDS_MISSING despite successful DB odds refresh — use caution; do not regenerate after kickoff.

---

## Artifacts

| File | Purpose |
|------|---------|
| `BRAZIL_NORWAY_CONTROLLED_PREDICTION_1_BASELINE.md` | Part B |
| `BRAZIL_NORWAY_CONTROLLED_PREDICTION_1_OWNER_SUMMARY.md` | Part J |
| `BRAZIL_NORWAY_CONTROLLED_PREDICTION_1_REPORT.md` | This report |
| `CONTROLLED_KNOCKOUT_PREDICTIONS_OWNER_TRACKER.md` | Part K |
| `scripts/validate_brazil_norway_controlled_prediction_1.py` | Part M |
| `artifacts/brazil_norway_controlled_prediction_1/workflow.json` | Full workflow log |
