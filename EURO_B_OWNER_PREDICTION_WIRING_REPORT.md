# EURO-B — Owner UEFA WDE/ECSE Prediction Wiring Report

**Phase:** EURO-B (owner/internal only)  
**Date:** 2026-06-30  
**Scope:** No public exposure, no WDE/ECSE scoring logic changes, no ECSE baseline changes.

---

## Executive summary

EURO-B wired owner-only WDE and ECSE generation for upcoming canonical UEFA fixtures using API-Football IDs and EURO-A2 crosswalk rules. **121 WDE predictions** were stored with `generated_by=owner_euro_b`. **0 ECSE snapshots** were created — all skipped for **missing odds / lambda inputs**. Owner today report successfully lists UEFA fixtures with WDE; ECSE awaits odds import.

**Final recommendation:** `NEED_ODDS_IMPORT`

---

## Part A — Canonical fixture selector

**Module:** `worldcup_predictor/owner/euro_b_fixture_selector.py`

| Competition | Canonical selected (30d) |
|-------------|--------------------------|
| champions_league | 36 |
| europa_league | 16 |
| conference_league | 69 |
| **Total** | **121** |

Criteria applied: upcoming kickoff, non-finished status, API-Football canonical ID or high-confidence crosswalk, Sportmonks-only rows excluded.

---

## Part B — WDE generation

**Script:** `scripts/owner_generate_uefa_predictions.py`

| Metric | Count |
|--------|------:|
| Selected | 121 |
| WDE generated | 121 |
| WDE skipped | 0 |

Storage: `worldcup_stored_predictions` with `source=owner_euro_b`, `generated_by=owner_euro_b`, `owner_only=true`, correct `competition_key`. Public prediction cache **not** written.

**Note:** Many UEFA qualifying fixtures produced confidence scores but **null 1X2/O/U selections** — likely limited team intelligence for early-round clubs (`missing_team_data` context). WDE pipeline ran without errors.

---

## Part C — ECSE generation

| Metric | Count |
|--------|------:|
| ECSE generated | 0 |
| ECSE skipped | 121 |
| Skip reason | `missing_odds` (100%) |

Existing ECSE logic unchanged; snapshots use `prediction_source=owner_euro_b` when odds exist. No baseline table mutations.

---

## Part D — Odds / input readiness

Per-fixture audit (121 fixtures):

| Input | Available |
|-------|-----------|
| 1X2 odds | 0 / 121 |
| Over/Under odds | 0 / 121 |
| BTTS odds | 0 / 121 |
| Correct score odds | 0 / 121 |
| Lambda inputs | 0 / 121 |

No bulk odds fetch was run in EURO-B (`--fetch-missing-odds` reserved for a later capped phase).

---

## Part E — Provider duplicate safety

**Artifact:** `artifacts/euro_b_provider_duplicate_candidates.json`

- **0 duplicate-risk groups** detected after canonical deduplication by `provider_fixture_id`.
- Sportmonks-only feed rows excluded from prediction set.

---

## Part F — Owner report integration

```bash
python scripts/owner_today_10_exact_scores.py --competitions champions_league europa_league conference_league --timezone Europe/Vienna --limit 10 --include-shadow --days-ahead 30 --upcoming-only
```

**Result:** 10 UEFA fixtures in owner report; **10 with WDE**, **0 with ECSE**. Reports written to `reports/owner/today_10_exact_score_predictions.{md,json}`. `public_output_changed: false`.

---

## Part G — Result sync readiness

`SUPPORTED_ECSE_COMPETITIONS` extended to include UEFA cups for **scanner discovery only** (no automatic future sync executed).

Scanner verification: UEFA competitions discoverable; upcoming fixtures not treated as past result-sync candidates.

---

## Part H — Validation

**Script:** `scripts/validate_euro_b_owner_prediction_wiring.py`  
**Result:** **PASSED**

---

## Example generated predictions (WDE)

| fixture_id | competition | confidence | ECSE |
|------------|-------------|------------|------|
| 1554361 | champions_league | 37.1 | skipped (no odds) |
| 1554368 | champions_league | 54.8 | skipped (no odds) |
| 1554410 | conference_league | 42.4 | skipped (no odds) |
| 1554365 | champions_league | 49.9 | skipped (no odds) |
| 1554363 | champions_league | 50.3 | skipped (no odds) |

---

## Artifacts

| Path | Purpose |
|------|---------|
| `artifacts/euro_b_owner_prediction_wiring_summary.json` | Run summary |
| `artifacts/euro_b_generated_predictions.jsonl` | Generated rows |
| `artifacts/euro_b_skipped_fixtures.jsonl` | Skipped rows + reasons |
| `artifacts/euro_b_provider_duplicate_candidates.json` | Duplicate diagnostics |

---

## Remaining blockers

1. **Odds import** for upcoming UEFA fixtures (blocks ECSE entirely).
2. **WDE market picks** often null for early qualifying ties — may need richer team context (`NEED_WDE_INPUTS` follow-up).
3. Public routes remain WC-scoped; owner rows are internal-only.

---

## Files created / updated

| Path | Role |
|------|------|
| `worldcup_predictor/owner/euro_b_fixture_selector.py` | Canonical UEFA selector |
| `worldcup_predictor/owner/euro_b_owner_predictions.py` | WDE/ECSE owner orchestration |
| `scripts/owner_generate_uefa_predictions.py` | CLI |
| `scripts/validate_euro_b_owner_prediction_wiring.py` | Validation |
| `scripts/owner_today_10_exact_scores.py` | UEFA multi-competition report |
| `worldcup_predictor/research/ecse_live/result_sync.py` | UEFA scanner support |

---

## Final recommendation

### `NEED_ODDS_IMPORT`

Owner WDE wiring is operational for 121 canonical UEFA fixtures, but **ECSE cannot run without odds snapshots**. Import or fetch capped 1X2/O/U odds for upcoming UEFA fixtures before enabling owner ECSE exact-score workflows.

---

*EURO-B complete. No public exposure. No prediction scoring logic changes.*
