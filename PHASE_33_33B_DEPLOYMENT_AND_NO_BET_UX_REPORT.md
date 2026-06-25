# PHASE 33 + 33B — DEPLOYMENT AND NO-BET UX REPORT

**Mode:** Deploy Phase 33 → Implement 33B → Validate → Report  
**Date:** 2026-06-20  
**Server:** `91.107.188.229` / `footballpredictor.it.com`  
**Deploy method:** Scoped tarball overlay (backend + frontend dist)

---

## Executive Summary

| Item | Status |
|------|--------|
| Phase 33 background prediction | ✅ Deployed |
| Phase 33 auto evaluation + accuracy summary | ✅ Deployed |
| Stored prediction reuse (SQLite + file cache) | ✅ Verified |
| CLI commands (`daily-worldcup-predict`, `evaluate-worldcup-results`, `worldcup-auto-cycle`) | ✅ Working |
| Phase 33B no-bet UX replacement | ✅ Deployed (backend + frontend) |
| Systemd timers / cron auto-run | ⏭ **Not enabled** (files prepared only) |
| Local validation Phase 33 | ✅ **21/21 PASS** |
| Local validation Phase 33B | ✅ **20/20 PASS** |
| Production validation Phase 33 | ✅ **21/21 PASS** |
| Production validation Phase 33B | ✅ **20/20 PASS** |

### Final Status: **Deployed with caution — monitor**

Background automation is live and manual auto-cycle succeeded. User-facing predictions now always show picks (official or caution tier). Internal `no_bet` flag preserved for accuracy analytics.

---

## 1. Backup

| Asset | Path |
|-------|------|
| **Backup directory** | `/opt/worldcup-predictor/backups/deploy-phase33-33b-20260620-150734` |
| SQLite DB snapshot | `.../football_intelligence.db` |
| Pre-deploy overlay snapshot | `.../repo_overlay_pre.tar.gz` |
| Pre-deploy commit | `.../pre_deploy_commit.txt` → **267812e** |
| Auto-cycle log | `.../auto_cycle.log` (partial — initial run blocked by missing CLI; rerun succeeded) |

---

## 2. Deployment Result

### Deployed components

**Phase 33 — Background automation**
- `worldcup_predictor/automation/worldcup_background/` (full package)
- SQLite PHASE44 tables via `migrations.py` / `repository.py`
- `prediction_store.py`, freshness bands, daily job, evaluation job, accuracy summary
- `main.py` CLI wiring
- `worldcup_predictor/cli/commands.py` *(deployed in follow-up patch)*
- `predict_pipeline.py`, `prediction_cache.py`, `cache_policy.py`, `settings.py`

**Phase 33B — No-bet UX replacement**
- `worldcup_predictor/api/pick_visibility.py` *(new)*
- `worldcup_predictor/api/market_ranking_engine.py`
- `worldcup_predictor/api/prediction_output.py`
- `worldcup_predictor/api/routes/predictions.py`
- `worldcup_predictor/automation/worldcup_background/pick_evaluator.py`
- `worldcup_predictor/automation/worldcup_background/accuracy_summary.py`
- Frontend: `base44-d` → `/var/www/worldcup/frontend/dist/` (Caution Prediction card)

**Scheduler plan (not enabled)**
- `deployment/systemd/worldcup-daily-predict.{service,timer}`
- `deployment/systemd/worldcup-evaluate-results.{service,timer}`
- `deployment/systemd/worldcup-auto-cycle.{service,timer}`

### Deploy fixes applied on server

1. **`sportmonks_xg_extraction.py`** — required by updated `predictions.py`; overlaid separately after API restart failure.
2. **`cli/commands.py`** — required by `main.py` Phase 33 commands; overlaid before auto-cycle.

### API health

```
GET /api/health → {"status":"ok"}
systemctl is-active worldcup-api → active
```

---

## 3. Manual Auto-Cycle Result

```bash
sudo -u www-data bash -lc 'cd /opt/worldcup-predictor && .venv/bin/python main.py worldcup-auto-cycle'
```

**First successful run:**
```
Phase 33 — World Cup auto cycle complete
  Predicted: 6
  Evaluated: 0
  Winrate: None
```

- **6 fixtures** stored in `worldcup_stored_predictions`
- **0 evaluations** (no finished fixtures in window yet — expected)
- Accuracy summary table initialized (pending results)

**Follow-up `daily-worldcup-predict --force-refresh --limit 3`:**
- Predicted: 2, Errors: 1 (fixture `1539007` — pre-existing `extended_markets._scorer_picks` AttributeError on prod; unrelated to Phase 33B)

---

## 4. Stored Prediction Reuse + No Duplicate API

| Test | Result |
|------|--------|
| `GET /api/predict/{id}` returns cached payload | ✅ `cache_source=sqlite_store` |
| `POST /api/predict/{id}` without `force_refresh` reuses store | ✅ No pipeline run; cache served |
| Phase 33 validation `fresh_skip_no_duplicate_pipeline` | ✅ PASS (pipeline_calls=1, skipped=1) |
| Phase 33B validation `no_duplicate_pipeline_on_reuse` | ✅ PASS (cache_hits=True) |

Production smoke (`scripts/prod_smoke_predict_reuse.sh`):
```
cache_source= sqlite_store
pick_tier= caution
no_bet= True
rec0= caution Low Confidence Pick: Home or Draw
```

---

## 5. Phase 33B — No-Bet UX Replacement

### Problem (before)

Low-confidence fixtures returned:
```
display_text: "No Bet — confidence or data quality too low"
status: "no_bet"
```
Frontend showed a yellow **No Bet** card with no actionable pick.

### New behavior (after)

| Condition | User-facing output | Internal |
|-----------|-------------------|----------|
| `confidence >= 60` and WDE allows | **Safe Pick**, **Value Pick**, **Aggressive Pick** | `pick_tier=official`, `no_bet=false` |
| `confidence < 60` or WDE no-bet | **Low Confidence Pick**, **Best Available Pick**, risk High/Medium | `pick_tier=caution`, `no_bet=true` (internal) |

**New API fields:**
- `user_visible_pick`
- `pick_tier` — `official` | `caution`
- `caution_reason`
- `confidence_gap_to_threshold`

**Unchanged (per spec):**
- WDE threshold **60**
- Internal `no_bet` flag for accuracy analysis
- Confidence / data quality still exposed

### Accuracy tracking split

`accuracy_tracking` now stores:
- `official_recommended` — `true` when confidence ≥ 60
- `caution_pick` / `best_available_pick` slots when below threshold

`accuracy_summary` aggregates separate winrates:
- `official_picks`
- `caution_picks`
- `caution_pick_market`

Caution evaluations are **not void** — they track win/loss independently so official winrate is not polluted.

---

## 6. Sample Fixture — Before / After

**Fixture `1489392` (confidence ~2.8%, internal no_bet)**

| | Before 33B | After 33B |
|---|-----------|-----------|
| Main headline | No Bet — confidence or data quality too low | **Low Confidence Pick: Home or Away** |
| Ranked picks section | Hidden | **Caution Prediction** card with two picks |
| `pick_tier` | n/a | `caution` |
| `no_bet` (internal) | `true` | `true` (unchanged) |
| `recommended_bets[0].status` | `no_bet` | `caution` |
| Message | (none) | *Confidence is below premium threshold, but this is the strongest available market.* |

**Fixture with official tier (confidence ≥ 60, e.g. NL vs Sweden when freshly predicted):**
- Shows Safe / Value / Aggressive ranked picks
- `pick_tier=official`, `recommended_bets[].status=recommended`

---

## 7. Validation Summary

| Script | Environment | Result |
|--------|-------------|--------|
| `scripts/validate_phase33_background_prediction_evaluation.py` | Local | **21/21 PASS** |
| `scripts/validate_phase33_background_prediction_evaluation.py` | Production | **21/21 PASS** |
| `scripts/validate_phase33b_no_bet_ux_replacement.py` | Local | **20/20 PASS** |
| `scripts/validate_phase33b_no_bet_ux_replacement.py` | Production | **20/20 PASS** |

Key 33B checks:
- confidence ≥ 60 → official ranked picks ✅
- confidence < 60 → caution pick (never hard No Bet) ✅
- internal `no_bet` still stored ✅
- official vs caution accuracy tracking split ✅
- stored prediction reuse ✅
- no duplicate pipeline on cache hit ✅

---

## 8. Scheduler Plan (NOT ENABLED)

Timer unit files are in `deployment/systemd/` on the server. **No timers are active:**

```bash
systemctl list-timers --all | grep worldcup
# → No worldcup timers enabled
```

**When approved, enable with:**
```bash
sudo cp deployment/systemd/worldcup-*.service deployment/systemd/worldcup-*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now worldcup-daily-predict.timer
sudo systemctl enable --now worldcup-evaluate-results.timer
sudo systemctl enable --now worldcup-auto-cycle.timer
```

Suggested schedule:
| Timer | Schedule |
|-------|----------|
| `worldcup-daily-predict` | 06:00 UTC daily |
| `worldcup-evaluate-results` | Every 6h |
| `worldcup-auto-cycle` | Every 4h |

---

## 9. Rollback Plan

1. **Stop timers** (if ever enabled):
   ```bash
   sudo systemctl disable --now worldcup-daily-predict.timer worldcup-evaluate-results.timer worldcup-auto-cycle.timer
   ```

2. **Restore code overlay:**
   ```bash
   cd /opt/worldcup-predictor
   tar xzf backups/deploy-phase33-33b-20260620-150734/repo_overlay_pre.tar.gz
   ```

3. **Restore SQLite** (if schema/data regression):
   ```bash
   cp backups/deploy-phase33-33b-20260620-150734/football_intelligence.db data/football_intelligence.db
   chown www-data:www-data data/football_intelligence.db
   ```

4. **Restore frontend** (from Phase 32 backup if needed):
   ```bash
   cp -a backups/deploy-phase32bc32e-20260620-144452/frontend_dist/. /var/www/worldcup/frontend/dist/
   ```

5. **Restart API:**
   ```bash
   sudo systemctl restart worldcup-api
   curl -sf http://127.0.0.1:8000/api/health
   ```

---

## 10. Known Issues / Monitor

1. **Fixture `1539007` force-refresh error** — `extended_markets._scorer_picks` AttributeError on prod (pre-existing); does not block cache reuse or caution UX.
2. **Low-confidence World Cup placeholders** — many fixtures show ~3% confidence; caution tier is working as designed until richer data is available.
3. **Git commit on server unchanged** — **267812e** (file overlay deploy, not git-pushed).

---

**STOP — Report complete. No cron/systemd auto-run enabled.**
