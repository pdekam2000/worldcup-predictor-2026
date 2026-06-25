# PHASE 33 — BACKGROUND PREDICTION + AUTO EVALUATION REPORT

**Mode:** Implement → Validate → Report  
**Date:** 2026-06-20  
**Deploy:** NO — awaiting approval

---

## Executive Summary

Phase 33 adds a background World Cup prediction pipeline with durable SQLite storage, kickoff-aware cache freshness, automatic result evaluation, and accuracy summaries. User-facing predict flow reuses stored predictions when fresh — no duplicate pipeline or external API calls.

**Validation:** 21/21 checks PASS → `artifacts/phase33_background_prediction_validation.json`

Phase 32E national team intelligence remains active (`national_team_intelligence.version = 32e` stored in payloads).

---

## 1. Goals Met

| Requirement | Status |
|-------------|--------|
| Background daily prediction (today + 3 days) | ✅ |
| Store full API payload + national intel 32e | ✅ |
| User predict reuses fresh stored prediction | ✅ |
| No duplicate API/pipeline on cache hit | ✅ |
| Kickoff-aware freshness (12h/4h/1h/15m) | ✅ |
| Post-kickoff: no refresh, evaluate only | ✅ |
| Auto result evaluation (picks + markets) | ✅ |
| Accuracy summary storage | ✅ |
| CLI commands | ✅ |
| No new GUI page | ✅ |
| WDE/confidence/DQ thresholds unchanged | ✅ |

---

## 2. Files Changed

### New — `worldcup_predictor/automation/worldcup_background/`

| File | Role |
|------|------|
| `freshness.py` | Kickoff-aware TTL bands + fresh/stale logic |
| `prediction_store.py` | SQLite + file cache unified lookup |
| `prediction_runner.py` | Run pipeline, build payload, persist |
| `daily_prediction_job.py` | Background predict job |
| `result_evaluation_job.py` | Finished fixture evaluation |
| `pick_evaluator.py` | safe/value/aggressive + market evaluation |
| `accuracy_summary.py` | Aggregate winrate stats |
| `runner.py` | Auto-cycle orchestrator |
| `__init__.py` | Public exports |

### Modified

| File | Change |
|------|--------|
| `worldcup_predictor/database/migrations.py` | `PHASE44_DDL` — 3 new tables |
| `worldcup_predictor/database/repository.py` | CRUD for stored preds, evaluations, summary |
| `worldcup_predictor/config/settings.py` | `WORLDCUP_PREDICTION_WINDOW_DAYS`, `WORLDCUP_BACKGROUND_PREDICTION_ENABLED` |
| `worldcup_predictor/orchestration/predict_pipeline.py` | Expose `intelligence_report` + `specialist_report` on result |
| `worldcup_predictor/api/routes/predictions.py` | SQLite store lookup + persist; national intel in payload |
| `worldcup_predictor/quota/prediction_cache.py` | Phase 33 freshness at read time |
| `worldcup_predictor/quota/cache_policy.py` | TTL aligned to Phase 33 bands |
| `main.py` | CLI subcommands |
| `worldcup_predictor/cli/commands.py` | CLI handlers |

### Validation

| File | Role |
|------|------|
| `scripts/validate_phase33_background_prediction_evaluation.py` | 21-check validation suite |

---

## 3. Storage Structure

### SQLite (`PHASE44_DDL`)

**`worldcup_stored_predictions`**
| Column | Purpose |
|--------|---------|
| `fixture_id` | PK — one row per fixture |
| `payload_json` | Full API prediction payload |
| `kickoff_utc` | Match kickoff |
| `source` | `background_daily`, `user_predict`, etc. |
| `predicted_at` | ISO timestamp |

**`worldcup_prediction_evaluations`**
| Column | Purpose |
|--------|---------|
| `fixture_id` | PK |
| `overall_status` | correct / wrong / pending / unknown / void |
| `safe_pick_status`, `value_pick_status`, `aggressive_pick_status` | Pick-level results |
| `market_1x2_status`, `market_ou_status`, etc. | Market-level results |
| `detail_json` | Full evaluation breakdown |

**`worldcup_accuracy_summary`**
| Column | Purpose |
|--------|---------|
| `competition_key` | PK (`world_cup_2026`) |
| `summary_json` | Aggregate stats (winrates, counts) |

### File cache (existing)

`.cache/predictions/` — fast API path, synced on every store. Phase 33 freshness enforced at read via `cached_at` + kickoff bands.

---

## 4. Cache Freshness Logic

| Hours until kickoff | Max age before stale |
|--------------------|----------------------|
| > 24h | 12 hours |
| 24h – 4h | 4 hours |
| 4h – 1h | 1 hour |
| < 1h | 15 minutes |
| After kickoff | Frozen — no refresh; evaluation only |

Implementation: `worldcup_predictor/automation/worldcup_background/freshness.py`

---

## 5. CLI Commands

```bash
# Predict upcoming WC fixtures (today + window_days, default 3)
python main.py daily-worldcup-predict
python main.py daily-worldcup-predict --window-days 3 --limit 10
python main.py daily-worldcup-predict --force-refresh

# Evaluate finished fixtures against stored predictions
python main.py evaluate-worldcup-results
python main.py evaluate-worldcup-results --limit 50

# Full cycle: predict + evaluate + summary report
python main.py worldcup-auto-cycle
python main.py worldcup-auto-cycle --report-path artifacts/phase33_auto_cycle_report.json
```

---

## 6. API-Call Saving Behavior

**User POST `/api/predict/{fixture_id}`:**
1. `WorldcupPredictionStore.get()` — SQLite then file cache
2. If fresh → return immediately (no `PredictPipeline`, no API-Football/Sportmonks)
3. If stale/missing → run pipeline once, store to SQLite + file cache

**Background job:**
- Skips fixtures with fresh stored predictions
- Skips post-kickoff fixtures
- Uses `record_history=False` to avoid duplicate accuracy history noise

Validation confirmed: second background run with fresh cache → **0 additional pipeline calls**.

---

## 7. Validation Results

```
21/21 PASS
```

| Check | Result |
|-------|--------|
| Schema tables created | ✅ |
| Freshness bands (12h/4h/1h/15m) | ✅ |
| Background job predicts | ✅ |
| Stored prediction reused (user path) | ✅ |
| No duplicate pipeline on fresh skip | ✅ |
| Stale detection + refresh | ✅ |
| Evaluation correct/wrong/pending | ✅ |
| safe_pick + 1X2 evaluation | ✅ |
| Accuracy summary generated | ✅ |
| No duplicate stored rows (upsert) | ✅ |
| national_team_intelligence 32e stored | ✅ |

---

## 8. Production Cron / Systemd Plan (NOT DEPLOYED)

### Option A — systemd timers (recommended)

**`/etc/systemd/system/worldcup-daily-predict.service`**
```ini
[Unit]
Description=World Cup daily background prediction (Phase 33)
After=network.target worldcup-api.service

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/opt/worldcup-predictor
EnvironmentFile=/opt/worldcup-predictor/.env.production
ExecStart=/opt/worldcup-predictor/.venv/bin/python main.py daily-worldcup-predict
```

**`/etc/systemd/system/worldcup-daily-predict.timer`**
```ini
[Unit]
Description=Run WC prediction every 6 hours

[Timer]
OnCalendar=*-*-* 00,06,12,18:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

**`/etc/systemd/system/worldcup-evaluate-results.service`**
```ini
[Unit]
Description=World Cup result evaluation (Phase 33)

[Service]
Type=oneshot
User=www-data
WorkingDirectory=/opt/worldcup-predictor
EnvironmentFile=/opt/worldcup-predictor/.env.production
ExecStart=/opt/worldcup-predictor/.venv/bin/python main.py evaluate-worldcup-results
```

**`/etc/systemd/system/worldcup-evaluate-results.timer`**
```ini
[Unit]
Description=Evaluate WC results every 2 hours on match days

[Timer]
OnCalendar=*-*-* 08,10,12,14,16,18,20,22:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
```

Enable after deploy approval:
```bash
systemctl daemon-reload
systemctl enable --now worldcup-daily-predict.timer
systemctl enable --now worldcup-evaluate-results.timer
```

### Option B — cron

```cron
0 */6 * * * cd /opt/worldcup-predictor && .venv/bin/python main.py daily-worldcup-predict >> logs/phase33_predict.log 2>&1
0 */2 * * * cd /opt/worldcup-predictor && .venv/bin/python main.py evaluate-worldcup-results >> logs/phase33_eval.log 2>&1
```

---

## 9. Rollback Plan

| Level | Action |
|-------|--------|
| **L1 — Disable jobs** | Stop/disable systemd timers or remove cron entries |
| **L2 — Feature off** | `WORLDCUP_BACKGROUND_PREDICTION_ENABLED=false` (future gate; user predict still uses existing file cache) |
| **L3 — Revert code** | Restore pre-Phase-33 `predictions.py`, `prediction_cache.py`, remove `worldcup_background/` package |
| **L4 — DB** | Tables are additive; optional `DROP TABLE worldcup_*` if full rollback needed |

User predict flow falls back to pre-33 file cache behavior if SQLite layer removed.

---

## 10. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WORLDCUP_PREDICTION_WINDOW_DAYS` | `3` | Background job lookahead |
| `WORLDCUP_BACKGROUND_PREDICTION_ENABLED` | `true` | Gate background jobs |
| `NATIONAL_TEAM_INTELLIGENCE_ENABLED` | `true` | Unchanged — Phase 32E active |
| `PREDICTION_CACHE_DIR` | `.cache/predictions` | File cache path |

---

## Final Verdict

**Ready for deployment review.** Phase 33 extends existing prediction cache infrastructure without breaking user flow, preserves Phase 32E national intelligence, and eliminates redundant pipeline/API calls on cache hits.

**STOP — NO DEPLOY — AWAITING APPROVAL**
