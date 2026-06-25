# PHASE 54F-2 — xG Coverage Expansion + Metric Key Repair Report

**Date:** 2026-06-23  
**Mode:** Implement → Backfill → Validate → Re-run 54F → Report  
**Status:** COMPLETE (backtest / feature-store only — no production, WDE, or deploy changes)

---

## Executive Summary

Phase 54F-2 **repaired metric classification** (critical bug: Shots On Target → xGoT) and re-imported UEFA cache with strict `metric_key=xg` semantics. False xG pollution was removed.

**Rolling xG coverage did not reach 30%.** After repair, usable rolling coverage is **5.0%** (4 of 80 UEFA fixtures) — down from the inflated **7.5%** in Phase 54F, which counted misclassified xGoT as xG.

**54F A/B backtest was not re-run** (coverage below threshold).  
**WC 732 server backfill could not run** — Phase 54E/54F feature-store code is not deployed on the production server yet.

**Final recommendation:** `NEED_MORE_HISTORICAL_XG`  
**Next action:** `RERUN_XG_BACKFILL` on server after deploying 54E/54F-2 code + valid Sportmonks token.

---

## 1. Root Cause from Phase 54F

| Issue | Detail |
|-------|--------|
| False xG | `Shots On Target` (type 86) matched `"on target"` → stored as `metric_key=xgot` |
| Mislabeled `xgfixture` | UEFA cache arrays named `xgfixture` often contain **regular statistics** (Corners, Fouls), not Expected Goals |
| Blind coercion | Lowercase `xgfixture` was always promoted to `xGFixture` without semantic check |
| Sparse true xG | Only **8 of 80** UEFA cache files contain Sportmonks type **5304** (Expected Goals) |
| Inflated 54F coverage | 63 fixtures had fake xGoT; only 8 had real team xG; rolling history could not form |

Phase 54F `NO_VALUE` was a **data-quality and coverage failure**, not proof that xG lacks predictive value.

---

## 2. Metric Key Repair

### Changes

| File | Fix |
|------|-----|
| `worldcup_predictor/providers/sportmonks_xg_extraction.py` | Strict `_metric_key_from_row`: type 5304→`xg`, 5305→`xgot`; `"on target"` requires `"expected"`; no default `"xg"` on player rows |
| `worldcup_predictor/feature_store/normalizers.py` | `classify_metric_key()`; `_block_has_expected_goals_semantics()`; coerce `xgfixture` only when expected-goals types present; removed bad fallback classifiers |
| `worldcup_predictor/feature_store/sportmonks_xg_store.py` | `--force-reimport`, `require_team_xg`, manifest skip reasons, purge-on-reimport |
| `worldcup_predictor/feature_store/repository.py` | `delete_fixture_records`, `delete_fixture_summary`, `count_records_by_metric` |
| `scripts/phase54e_sportmonks_xg_backfill.py` | `--metric-key`, `--force-reimport` |

### Classification proof

| Input | Before (54F) | After (54F-2) |
|-------|--------------|---------------|
| Shots On Target (type 86) | `xgot` ❌ | `None` (skipped) ✅ |
| Expected Goals (type 5304) | `xg` | `xg` ✅ |
| Expected Goals on Target (type 5305) | `xgot` | `xgot` ✅ |

---

## 3. xG vs xGoT Separation Proof

- **EGIE rolling features** (`xg_feature_builder.py`) use only `home_xg` / `away_xg` from summaries built from `metric_key=xg` records.
- **EGIE feature names** exclude `xgot`, `home_xgot`, `away_xgot`.
- **Post-repair DB:** `fixtures_xgot_only_no_team_xg = 0` (xGoT never substitutes for team xG in summaries).
- **xGoT preserved** separately when true type 5305 rows exist (Europa league fixtures).

Validation: **15/15 PASS** (`scripts/validate_phase54f2_xg_coverage_repair.py`)

---

## 4. WC 732 Backfill Result

| Attempt | Result |
|---------|--------|
| Local `--league-id 732 --max-calls 80 --metric-key xg` | **0 fixtures processed** — local Sportmonks token not configured / invalid |
| Server `/opt/worldcup-predictor` | **Blocked** — `phase54e` script and `worldcup_predictor/feature_store/` **not deployed** on server; `alembic` requires `DATABASE_URL` in shell context |

**Action required:** Deploy 54E/54F-2 code to server, then:

```bash
cd /opt/worldcup-predictor
set -a && source .env.production && set +a
.venv/bin/python -m alembic upgrade head
.venv/bin/python scripts/phase54e_sportmonks_xg_backfill.py \
  --league-id 732 --max-calls 80 --metric-key xg --force-reimport \
  --job-key phase54f2_wc732
```

---

## 5. UEFA 2 / 5 / 2286 Re-import Result

Cache-only re-import with `--force-reimport --metric-key xg`:

| League | ID | Scanned | Imported | Skipped (no true team xG) |
|--------|-----|---------|----------|---------------------------|
| Champions League | 2 | 30 | 0 | 30 |
| Europa League | 5 | 30 | **8** | 22 |
| Conference League | 2286 | 20 | 0 | 20 |

**Cache semantics (post-repair):**

| Category | Fixtures |
|----------|----------|
| True team xG (type 5304) | **8** |
| xGoT-only | **0** (previously 63 false positives) |
| No xG data | **72** |

Manifest records **72** fixtures as `empty:no_true_xg_metrics`.

---

## 6. Coverage Before / After

| Metric | Phase 54F (pre-repair) | Phase 54F-2 (post-repair) |
|--------|------------------------|---------------------------|
| Feature store records | 442 | 316 |
| Summaries with team xG | 8 (many polluted) | **8** (clean) |
| Usable rolling xG fixtures | 6 | **4** |
| Rolling coverage % (of 80 UEFA) | 7.5% (inflated) | **5.0%** (honest) |
| xGoT-only false positives | ~63 | **0** |

### Rolling windows (EGIE pre-match features)

| Window | Fixtures |
|--------|----------|
| rolling_xg_3 | 4 |
| rolling_xg_5 | 4 |
| rolling_xg_10 | 4 |

### Threshold

| Target | Required | Actual | Pass |
|--------|----------|--------|------|
| Minimum | ≥ 30% | 5.0% | ❌ |
| Preferred | ≥ 40% | 5.0% | ❌ |

---

## 7. Phase 54F Re-run

**Not executed** — coverage **5.0% < 30%** threshold.

Per phase rules: only dataset/readiness validation; no new A/B performance claims.

Prior 54F results remain valid as **low-sample baseline** only.

---

## 8. Insufficient Coverage — Next Data Actions

1. **Deploy** `worldcup_predictor/feature_store/` + scripts to server (`/opt/worldcup-predictor`).
2. **Run WC 732 backfill** with production Sportmonks token (80 API calls, cache-first).
3. **Refresh UEFA caches** via live Sportmonks pulls for leagues 2/5/2286 — current cache lacks type 5304 for CL/Conference.
4. **Re-run** `scripts/phase54f2_xg_coverage_repair.py` until `usable_rolling_xg_coverage_pct >= 30%`.
5. **Then** re-run `scripts/phase54f_egie_xg_backtest.py` for authoritative A/B comparison.

Do **not** reclassify xGoT as xG. Do **not** start Phase 54G Pressure Index until xG coverage and backtest justify it.

---

## 9. Final Recommendation

### `NEED_MORE_HISTORICAL_XG`

| Option | Verdict |
|--------|---------|
| READY_FOR_54G | ❌ Coverage too low |
| RERUN_XG_BACKFILL | ✅ **Yes** — after server deploy + live API |
| NEED_MORE_HISTORICAL_XG | ✅ **Current state** |
| STOP_XG_FOR_NOW | ❌ Pipeline is sound; data is the blocker |

**Why not STOP:** Metric repair succeeded; leakage-safe EGIE arm exists; true xG signal exists in 8 Europa fixtures; problem is **historical depth**, not architecture.

---

## Deliverables

| Item | Path |
|------|------|
| Metric repair | `normalizers.py`, `sportmonks_xg_extraction.py` |
| Backfill CLI | `scripts/phase54e_sportmonks_xg_backfill.py` |
| Orchestrator | `scripts/phase54f2_xg_coverage_repair.py` |
| Coverage audit | `scripts/audit_phase54f2_xg_coverage_repair.py` |
| Validation | `scripts/validate_phase54f2_xg_coverage_repair.py` |
| Artifacts | `artifacts/phase54f2_xg_coverage_repair/` |

---

*Phase 54F-2 complete. STOP — no deploy, no live prediction changes.*
