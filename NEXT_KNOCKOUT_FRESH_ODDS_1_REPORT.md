# NEXT-KNOCKOUT-FRESH-ODDS-1 — Controlled Production Report

**Phase:** NEXT-KNOCKOUT-FRESH-ODDS-1  
**Run date:** 2026-07-04 (Europe/Vienna)  
**Host:** Hetzner `91.107.188.229` — `/opt/worldcup-predictor`  
**Final recommendation:** `NO_UPCOMING_KNOCKOUT_FIXTURE`

---

## Part A — Production Environment Verification

| Item | Value |
|------|-------|
| Branch | `main...origin/main` (many local modifications on server) |
| Production commit | `9ca89f05ac9c0832fcb5fa858214888448cdc7a2` |
| origin/main | `9ca89f05ac9c0832fcb5fa858214888448cdc7a2` |
| App version | **A23.0.0** · hotfix-pack4 · schema v7 |
| DB path | `data/football_intelligence.db` |
| DB size | **9.5 GB** |
| worldcup-api | **active (running)** since 2026-07-03 07:53 UTC |
| nginx | **active (running)** since 2026-06-29 |

**Deploy note:** Required scripts/modules for this phase were copied to production before discovery:

- `scripts/find_next_knockout_fixture.py`
- `scripts/run_odds_freshness_refresh.py`
- `scripts/run_production_prediction_pipeline.py` (with `--fixture-id`)
- `worldcup_predictor/odds/freshness_*.py`
- `worldcup_predictor/owner/production_pipeline/runner.py`
- `worldcup_predictor/owner_daily/cycle.py`

No timers were enabled. No formulas or research logic were promoted.

---

## Part B — Next Upcoming Knockout Fixture Discovery

**Command:**

```bash
.venv/bin/python scripts/find_next_knockout_fixture.py \
  --competition wc --from-date today --format markdown --limit 10
```

**Exit code:** 1  
**Output:** empty fixture table + `NO_UPCOMING_KNOCKOUT_FIXTURE`

### Production DB fixture state (read-only audit)

| Metric | Count |
|--------|------:|
| WC fixtures (non-placeholder) | 329 |
| Status `FT` | 317 |
| Status `NS` (stale) | 12 |
| Fixtures with `kickoff_utc >= now` | **0** |

All 12 remaining `NS` fixtures are **Group Stage - 3** matches with kickoffs between **2026-06-26** and **2026-06-28** (already in the past relative to run time **2026-07-04**). None are classified as knockout.

Knockout round names exist in DB (`Round of 16`, `Quarter-finals`, `Semi-finals`, `Final`, etc.) but sampled rows are **historical** (2018/2022) and **FT** — not upcoming 2026 knockout fixtures.

**Selected fixture:** none  
**Workflow stopped here** per instructions.

---

## Part C — Odds Freshness Audit

**Skipped** — no fixture selected.

---

## Part D — Controlled Odds Refresh Dry-Run

**Skipped** — no fixture selected.

---

## Part E — Controlled Real Odds Refresh

**Skipped** — no fixture selected.

**Provider calls used:** 0

---

## Part F — Prediction Dry-Run

**Skipped** — no fixture selected.

---

## Part G — Controlled Real Prediction Run

**Skipped** — no fixture selected.

---

## Part H — Prediction Inspection

**Skipped** — no prediction created.

- ECSE snapshots before run: **0** (unchanged)
- Admin endpoint: not called (`TOKEN_NOT_AVAILABLE` / not applicable)

---

## Part I — Owner-Facing Summary

Path: [`NEXT_KNOCKOUT_FRESH_ODDS_1_PREDICTION_SUMMARY.md`](NEXT_KNOCKOUT_FRESH_ODDS_1_PREDICTION_SUMMARY.md)

No match prediction available.

---

## Warnings

1. **No upcoming fixtures in production DB** — zero rows with future kickoff times; tournament schedule appears exhausted or not synced forward.
2. **12 stale `NS` group-stage fixtures** — past kickoff but not updated to `FT`; results sync may be needed before knockout schedule appears.
3. **0 ECSE prediction snapshots** in production (unchanged from EVAL-COVERAGE-1).
4. **Do not enable timers** until fixture discovery and results sync are healthy.

---

## Next Required Actions

Before retrying this workflow:

1. **Sync/fixture refresh** — ensure 2026 WC knockout schedule and statuses are loaded into production DB (especially any Round of 16+ fixtures with future kickoffs).
2. **Results-only** — run results sync for the 12 stale `NS` group matches if they have finished.
3. **Re-run NEXT-KNOCKOUT-FRESH-ODDS-1** once an upcoming knockout fixture exists.

After a knockout match finishes (once predictions exist):

1. `results-only` pipeline
2. `eval-only` pipeline
3. Evaluation report

---

## Final Recommendation

### `NO_UPCOMING_KNOCKOUT_FIXTURE`

No upcoming knockout fixture exists in the Hetzner production database. Odds refresh and controlled WDE/ECSE prediction were **not** executed.

**Also:** `DO_NOT_ENABLE_TIMERS`
