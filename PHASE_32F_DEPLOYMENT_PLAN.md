# PHASE 32F — PRODUCTION DEPLOYMENT PREPARATION

**Mode:** Deploy Preparation  
**Date:** 2026-06-20  
**Deploy:** NO — awaiting approval  
**Scope:** Phase 32B + 32C + 32E (national team intelligence stack)

---

## Executive Summary

Phases 32B (intelligence engines), 32C (history backfill), and 32E (reality calibration) are ready for production deployment **with pre-flight steps**. Phase 32D audit findings are resolved in 32E. All four phase reports were verified; safety checks pass on the 20-fixture validation cohort.

| Phase | Report | Validation | Status |
|-------|--------|------------|--------|
| 32B | `PHASE_32B_NATIONAL_TEAM_INTELLIGENCE_REPORT.md` | **12/12 PASS** | ✅ Ready |
| 32C | `PHASE_32C_NATIONAL_TEAM_HISTORY_BACKFILL_REPORT.md` | **9/9 PASS** | ✅ Ready (requires prod backfill) |
| 32D | `PHASE_32D_LEAKAGE_REALITY_AUDIT.md` | Audit only | ✅ Issues fixed in 32E |
| 32E | `PHASE_32E_REALITY_CALIBRATION_REPORT.md` | **9/10 PASS** | ✅ Ready (avg +0.14 over band) |

### Final Answer: **B) Deploy with caution**

Deploy is recommended after completing the pre-flight checklist below. Confidence calibration is honest and safe for upcoming fixtures; production requires a one-time SQLite backfill and post-deploy smoke validation on the server.

---

## 1. Validation Report Verification

### Phase 32B — National Team Intelligence

| Check | Result |
|-------|--------|
| Validation script | `scripts/validate_phase32b_national_team_intelligence.py` |
| Artifact | `artifacts/phase32b_national_team_validation.json` |
| Checks passed | **12/12** |
| WDE thresholds unchanged | conf ≥ 60, DQ ≥ 50 ✅ |
| All five engines produce scores | form, H2H, squad, injury, consensus ✅ |
| Feature flag | `NATIONAL_TEAM_INTELLIGENCE_ENABLED` (default `True`) ✅ |

**Original 20-fixture metrics (pre-32C cache):** avg 59.24, rec rate 35%, 13/20 ≥ 60.

### Phase 32C — History Backfill

| Check | Result |
|-------|--------|
| Validation script | `scripts/validate_phase32c_national_history_backfill.py` |
| Artifact | `artifacts/phase32c_national_history_validation.json` |
| Checks passed | **9/9** |
| Team IDs resolved | 20/20 (72/72 full DB backfill) |
| Form cache | 40 teams |
| H2H cache | 20 pairs |
| External API on backfill | **0 calls** |
| Cache hit rate | 87% overall |

**Note:** 32C confidence metrics (avg 79.47) were inflated; superseded by 32E calibration. Deploy **32E code**, not 32C scoring behavior.

### Phase 32D — Leakage & Reality Audit

| Finding (pre-32E) | 32E resolution |
|-------------------|----------------|
| No explicit kickoff filter | ✅ `history_filters.py` + resolver/warm-cache filters |
| Circular self-inclusion (72 DB, FT fixtures) | ✅ Read-time `exclude_fixture_id` filter |
| Consensus 20/20 at 95 | ✅ Recalibrated; max 72.2 on cohort |
| Injury empty-list → 95 | ✅ Neutral 55; max 72 on cohort |
| Upcoming cohort: zero future leakage | ✅ Confirmed post-32E |

**32D verdict was B) Needs fixes** — all recommended fixes implemented in 32E.

### Phase 32E — Reality Calibration

| Check | Result |
|-------|--------|
| Validation script | `scripts/validate_phase32e_reality_calibration.py` |
| Artifact | `artifacts/phase32e_reality_calibration_validation.json` |
| Checks passed | **9/10** |
| Future leakage | **0** ✅ |
| Circular history | **0** ✅ |
| Consensus at ≥95 | **0/20** ✅ |
| Injury at ≥95 | **0/20** ✅ |
| Avg confidence band 65–72 | **72.14** ⚠️ (+0.14) |

---

## 2. Safety Confirmations (Post-32E)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| No future leakage | ✅ PASS | `leakage_audit.future_leaks = 0` |
| No circular history | ✅ PASS | `leakage_audit.circular_refs = 0` |
| No consensus saturation | ✅ PASS | max 72.2, 0 at 95, stdev 1.17 |
| No injury inflation | ✅ PASS | max 72.0, avg 66.05, 0 at 95 |

**Residual note:** Cache tables store unfiltered API payloads; filters apply at **read time** in `resolve_match_history()`. Safe for production predict path on upcoming fixtures. Finished-fixture backtests inherit 32E guards automatically.

---

## 3. Production Safety Checklist

### Pre-deploy (required)

| # | Item | Owner | Status |
|---|------|-------|--------|
| 1 | Merge/deploy code containing `worldcup_predictor/intelligence/national_team/` (32B+32C+32E) | Dev | ☐ |
| 2 | Confirm `NATIONAL_TEAM_INTELLIGENCE_ENABLED=true` in prod `.env.production` | Ops | ☐ |
| 3 | SQLite migrations auto-run on API start (`PHASE43_DDL` via `ensure_schema_compat`) | Auto | ☐ verify |
| 4 | Run Phase 32C backfill on prod SQLite (see §5) | Ops | ☐ **critical** |
| 5 | Verify prod has API-Football disk cache at `.cache/api_football/` (backfill source) | Ops | ☐ |
| 6 | Restart `worldcup-api` after code + backfill | Ops | ☐ |
| 7 | Smoke: `curl /api/health` + one WC fixture predict | Ops | ☐ |
| 8 | Run `validate_phase32e_reality_calibration.py --limit 5` on server (optional) | Ops | ☐ |

### Post-deploy monitoring (first 24h)

| # | Item |
|---|------|
| 1 | Watch avg confidence on new predictions (expect 65–75, not 90+) |
| 2 | Confirm `national_team_intelligence.version = "32e"` in predict response supplemental |
| 3 | Confirm no Bet rate ~25–35% (not 0% or 100%) |
| 4 | Monitor API quota — national intel uses cached data; no new live endpoints |
| 5 | Check logs for `National team intelligence attach failed` |

### Rollback triggers

- Avg confidence consistently > 85 on upcoming fixtures
- Recommendation rate > 95% or < 10% unexpectedly
- Errors in national intel attach path
- User-facing confidence regression vs pre-deploy baseline

---

## 4. Deployment Plan

### 4.1 Files Changed (full stack)

#### New package — `worldcup_predictor/intelligence/national_team/`

| File | Phase | Role |
|------|-------|------|
| `_shared.py` | 32B/32E | Helpers, date/kickoff filters |
| `form_engine.py` | 32B | National form scoring |
| `h2h_engine.py` | 32B | H2H scoring |
| `squad_strength_engine.py` | 32B | Squad/lineup strength |
| `injury_impact_engine.py` | 32B/32E | Injury impact (recalibrated) |
| `consensus_engine.py` | 32B/32E | Market consensus (recalibrated) |
| `data_resolver.py` | 32B/32C/32E | Team ID resolution, cache reads, filters |
| `orchestrator.py` | 32B/32E | Intelligence assembly (version `32e`) |
| `integration.py` | 32B/32E | ScoringEngine + WDE integration |
| `history_backfill.py` | 32C | Offline team ID + cache build |
| `history_filters.py` | 32E | Temporal safety filters |
| `__init__.py` | 32B | Exports |

#### Modified core files

| File | Phase | Change |
|------|-------|--------|
| `worldcup_predictor/prediction/scoring_engine.py` | 32B | Attach national intel; override breakdown |
| `worldcup_predictor/decision/weighted_decision_engine.py` | 32B/32E | National factors + WDE boost |
| `worldcup_predictor/config/settings.py` | 32B | `national_team_intelligence_enabled` |
| `worldcup_predictor/database/migrations.py` | 32C | `PHASE43_DDL` tables |
| `worldcup_predictor/database/repository.py` | 32C | Team resolution + form/H2H cache CRUD |

#### Validation scripts

| Script | Phase |
|--------|-------|
| `scripts/validate_phase32b_national_team_intelligence.py` | 32B |
| `scripts/validate_phase32c_national_history_backfill.py` | 32C |
| `scripts/validate_phase32e_reality_calibration.py` | 32E |

#### Reports & artifacts

| File |
|------|
| `PHASE_32B_NATIONAL_TEAM_INTELLIGENCE_REPORT.md` |
| `PHASE_32C_NATIONAL_TEAM_HISTORY_BACKFILL_REPORT.md` |
| `PHASE_32D_LEAKAGE_REALITY_AUDIT.md` |
| `PHASE_32E_REALITY_CALIBRATION_REPORT.md` |
| `artifacts/phase32{b,c,e}_*.json` |

### 4.2 Database Impact

**SQLite** (`data/football_intelligence.db` — prod path per `SQLITE_PATH`):

| Table | Phase | Purpose | Migration |
|-------|-------|---------|-----------|
| `fixture_team_resolution` | 32C | Maps fixture_id → API team IDs | Auto on connect |
| `national_team_form_cache` | 32C | Per-team recent fixtures JSON | Auto on connect |
| `national_team_h2h_cache` | 32C | Per-pair H2H meetings JSON | Auto on connect |

**PostgreSQL (SaaS):** No schema changes. National intel reads SQLite only.

**One-time backfill (required on prod):**

```bash
cd /opt/worldcup-predictor
sudo -u www-data python -c "
from worldcup_predictor.intelligence.national_team.history_backfill import run_phase32c
print(run_phase32c())
"
```

Or via validation script (runs backfill + checks):

```bash
sudo -u www-data python scripts/validate_phase32c_national_history_backfill.py --limit 20
```

**Data volume:** ~40 form cache rows, ~20–72 H2H pairs, 72 fixture_team_resolution rows (negligible).

### 4.3 Rollback Plan

| Level | Action | Effect | Time |
|-------|--------|--------|------|
| **L1 — Feature flag** | Set `NATIONAL_TEAM_INTELLIGENCE_ENABLED=false`, restart API | Disables national intel; reverts to legacy scoring components | ~1 min |
| **L2 — Code rollback** | Restore previous git tag / systemd backup (`worldcup-api.service.bak.*`) | Full pre-32B behavior | ~5 min |
| **L3 — DB rollback** | Not required — new tables are additive; unused if flag off | — | — |

**Recommended rollback:** L1 first. Cache tables can remain; they are inert when intel is disabled.

### 4.4 Cache Impact

| Cache | Location | Build | Read path |
|-------|----------|-------|-----------|
| `national_team_form_cache` | SQLite | Phase 32C backfill (offline) | `data_resolver.load_recent_fixtures_cached()` |
| `national_team_h2h_cache` | SQLite | Phase 32C backfill | `data_resolver.load_h2h_cached()` |
| `api_response_cache` | SQLite | Existing API responses | Team ID resolution fallback |
| `.cache/api_football/` | Disk | Existing | Backfill source; warm-cache fallback |

**Runtime behavior:**
- Predict path: **read-only** from caches + apply 32E temporal filters
- No new live API calls for form/H2H when caches populated
- `warm_national_team_cache_for_fixture()` available for on-demand cache refresh (uses existing cached API payloads)

**Prod risk:** If backfill skipped, national intel degrades to 32B behavior (sparse form/H2H, lower confidence ~59). Not a safety issue; performance/coverage issue.

### 4.5 Expected Production Behavior

| Behavior | Before (Phase 32 audit) | After deploy (32E) |
|----------|------------------------|---------------------|
| WC avg confidence | ~55 | **68–72** |
| Fixtures ≥ 60 | 0% | **~95%** (19/20 in validation) |
| Recommendation rate | 0% | **65–75%** |
| No Bet rate | 100% | **25–35%** |
| Max confidence | ~56 | **~84** (not 92+) |
| WDE thresholds | 60 / 50 | **Unchanged** |
| Supplemental block | absent | `national_team_intelligence` v32e |
| Form/H2H active | No (NULL IDs) | Yes (cached history) |
| Consensus scores | Legacy odds | Calibrated 68–72 typical |
| Injury unknown | Legacy path | Neutral **55** |

**User-visible changes:**
- More WC fixtures receive recommendations (pass confidence ≥ 60 gate)
- Confidence scores more differentiated (not clustered at 95)
- Prediction breakdown shows national form, H2H, squad, injury, consensus components
- No change to UI thresholds or No Bet gate logic

---

## 5. Estimated Production Metrics

Based on 32E validation cohort (20 upcoming NS fixtures, Jun 20–24 2026) and full 72-fixture cache coverage:

| Metric | Conservative | Expected | Optimistic |
|--------|-------------|----------|------------|
| Avg confidence | 65 | **70–72** | 75 |
| Max confidence | 78 | **82–84** | 88 |
| Recommendation rate | 55% | **68–72%** | 80% |
| No Bet rate | 40% | **28–32%** | 20% |
| Fixtures ≥ 60 | 85% | **95%** | 100% |
| Fixtures ≥ 70 | 50% | **70%** | 80% |

**Assumptions:**
- Prod backfill completed successfully (32C)
- Upcoming WC fixtures with populated team IDs and form/H2H cache
- Injury data sparse on some fixtures → neutral 55 (7/20 in validation)
- Same WDE + promotion stack as validation

**Not expected in production:**
- Consensus saturation at 95
- Injury default at 95 for empty lists
- Future-data leakage on pre-match predictions

---

## 6. Deploy Sequence (when approved)

```
1. git pull / rsync code → /opt/worldcup-predictor
2. Verify .env.production:
     NATIONAL_TEAM_INTELLIGENCE_ENABLED=true
     SQLITE_PATH=data/football_intelligence.db
3. Run backfill (www-data):
     python scripts/validate_phase32c_national_history_backfill.py --limit 20
4. Restart API:
     systemctl restart worldcup-api
5. Smoke test:
     curl -sf http://127.0.0.1:8000/api/health
     # predict one upcoming WC fixture; confirm supplemental.national_team_intelligence.version == "32e"
6. Monitor first 10 predictions for confidence range 60–85
```

**NO deploy in this phase — execute above only after explicit approval.**

---

## 7. Verdict Rationale

### Why not A) Deploy recommended

- Production server has not yet run Phase 32C backfill (local-only validated)
- 32E avg confidence 72.14 exceeds target band by 0.14 pts
- First deploy of a multi-phase scoring change warrants 24h monitoring

### Why not C) Hold deployment

- All 32D blockers resolved in 32E
- Safety checks pass (leakage, circular, saturation, inflation)
- Feature-flag rollback is instant and safe
- Validated lift is real (+13 pts over 32B) without inflation artifacts

### **B) Deploy with caution** ✅

Proceed after pre-flight checklist (§3). Low risk for upcoming fixtures; primary caution is ensuring prod SQLite backfill runs before enabling traffic.

---

**STOP — NO DEPLOY — AWAITING APPROVAL**
