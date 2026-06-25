# PHASE 44A — PRODUCTION AUTO EVALUATION SYSTEM

**Mode:** Implement → Validate → Report  
**Date:** 2026-06-21  
**Deploy:** **NOT DEPLOYED — awaiting operator approval**

---

## Executive summary

Phase 44A adds a **production-safe, periodic auto evaluation job** that scans **stored predictions first**, evaluates finished fixtures, writes/updates evaluation rows idempotently, rebuilds accuracy summary, and logs structured counts. Systemd unit files are ready but **not installed on production**.

**Validation:** **21/21 PASS** → `artifacts/phase44a_auto_evaluation_validation.json`

**No prediction engine, WDE, or stored probability changes.**

---

## 1. Current evaluation flow (audit)

| Path | Entry | Behavior |
|------|-------|----------|
| **CLI** | `python main.py evaluate-worldcup-results` | Runs evaluation job (now stored-first) |
| **CLI (new)** | `python main.py worldcup-auto-evaluation` | Production timer entry point + structured logging |
| **CLI** | `python main.py worldcup-auto-cycle` | Predict + evaluate + summary (manual) |
| **Admin API** | `POST /api/admin/accuracy/rebuild?evaluate=true` | Optional evaluate + summary rebuild |
| **Evaluator** | `pick_evaluator.evaluate_stored_prediction()` | Read payload, compare to outcome |
| **Job** | `result_evaluation_job.run_evaluate_worldcup_results()` | Orchestrates scan → evaluate → upsert |
| **Summary** | `accuracy_summary.rebuild_accuracy_summary()` | Aggregates `worldcup_prediction_evaluations` |
| **Systemd (before)** | `deployment/systemd/worldcup-evaluate-results.*` | Existed as **PLAN ONLY**, not installed on prod |

### Phase 44 audit findings addressed

- No production timer → **timer unit prepared (30 min)**
- Only 2 test eval rows → job will refresh when fixtures finish (upsert, not duplicate)
- Silent failures → **INFO logging with evaluated/skipped/error counts**

---

## 2. Production auto evaluation job

### New module

`worldcup_predictor/automation/worldcup_background/auto_evaluation_job.py`

- `run_production_auto_evaluation()` — systemd/CLI entry point
- Configures logging if unset
- Calls stored-first evaluation with `skip_unchanged=True`

### Enhanced job

`worldcup_predictor/automation/worldcup_background/result_evaluation_job.py`

**Stored-first scan (default):**

1. Load all `worldcup_stored_predictions` for `world_cup_2026`
2. Resolve fixture outcome via `FixtureOutcomeResolver`
3. Skip if not finished
4. Skip if already evaluated with same score/status (idempotent rerun)
5. Evaluate via `evaluate_stored_prediction()` (read-only on payload)
6. Upsert `worldcup_prediction_evaluations` (PK = `fixture_id`)
7. Rebuild `worldcup_accuracy_summary`

**Does NOT:**

- Modify `worldcup_stored_predictions.payload_json`
- Touch WDE / prediction engine
- Change raw probabilities

---

## 3. Idempotency

| Mechanism | Detail |
|-----------|--------|
| Primary key | `worldcup_prediction_evaluations.fixture_id` — upsert prevents duplicates |
| Unchanged skip | Re-run skips rows where `final_score` + `overall_status` unchanged |
| Safe restart | Timer `Persistent=true` catches missed runs after downtime |
| Connection cleanup | `repo.close()` + `store._repo.close()` in `finally` block |

---

## 4. Logging

Structured INFO logs (stdout → journald when systemd installed):

```
worldcup_auto_evaluation_start competition_key=world_cup_2026 mode=stored_first
worldcup_auto_evaluation {scanned, evaluated, updated, skipped_not_finished, skipped_unchanged, ...}
worldcup_auto_evaluation_done evaluated=N updated=N skipped=N errors=N
```

Exceptions per fixture logged with `logger.exception()` — no silent swallow.

---

## 5. Systemd

| Unit | Purpose |
|------|---------|
| `worldcup-evaluate-results.service` | Oneshot job as `www-data` |
| `worldcup-evaluate-results.timer` | Every **30 minutes** (`*:00,30:00`) + 120s randomized delay |

### Service command

```
ExecStart=/opt/worldcup-predictor/.venv/bin/python main.py worldcup-auto-evaluation
EnvironmentFile=/opt/worldcup-predictor/.env.production
```

### Install script (operator, after approval)

```bash
sudo bash /opt/worldcup-predictor/scripts/install_phase44a_eval_timer.sh
```

---

## 6. Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/automation/worldcup_background/result_evaluation_job.py` | Stored-first scan, idempotency, logging, connection cleanup |
| `worldcup_predictor/automation/worldcup_background/auto_evaluation_job.py` | **New** — production entry point |
| `worldcup_predictor/automation/worldcup_background/__init__.py` | Export new symbols |
| `worldcup_predictor/automation/worldcup_background/runner.py` | Pass mode to CLI wrapper |
| `worldcup_predictor/database/repository.py` | `get_worldcup_prediction_evaluation()` |
| `worldcup_predictor/cli/commands.py` | Enhanced output + `run_auto_evaluation_command()` |
| `main.py` | `worldcup-auto-evaluation` CLI command |
| `worldcup_predictor/api/routes/admin_accuracy.py` | Extended rebuild response fields |
| `deployment/systemd/worldcup-evaluate-results.service` | Phase 44A production config |
| `deployment/systemd/worldcup-evaluate-results.timer` | 30-minute schedule |
| `scripts/install_phase44a_eval_timer.sh` | **New** — timer installer |
| `scripts/validate_phase44a_auto_evaluation.py` | **New** — 21-check validation |

---

## 7. Validation results

```
Phase 44A validation: 21/21 PASS
```

| Check | Result |
|-------|--------|
| Finished fixture evaluated | PASS |
| Rerun idempotent (no duplicate row) | PASS |
| Summary rebuilt | PASS |
| Performance Center updates | PASS |
| History archive status correct/wrong | PASS |
| Upcoming fixture skipped (not error) | PASS |
| Systemd service/timer wiring | PASS |
| Evaluator read-only on predictions | PASS |

Artifact: `artifacts/phase44a_auto_evaluation_validation.json`

---

## 8. Deploy steps (after approval)

1. **Backup production DB**
   ```bash
   cp /opt/worldcup-predictor/data/football_intelligence.db \
      /opt/worldcup-predictor/backups/pre-phase44a-$(date +%Y%m%d-%H%M%S).db
   ```

2. **Deploy code** (backend only — no frontend rebuild required)
   ```bash
   # Standard deploy tarball/rsync for worldcup_predictor/, main.py, deployment/systemd/, scripts/
   sudo systemctl restart worldcup-api
   ```

3. **Install timer**
   ```bash
   sudo bash /opt/worldcup-predictor/scripts/install_phase44a_eval_timer.sh
   ```

4. **Verify**
   ```bash
   systemctl list-timers worldcup-evaluate-results.timer
   journalctl -u worldcup-evaluate-results.service -n 50 --no-pager
   curl -sS https://footballpredictor.it.com/api/performance/summary | python3 -m json.tool
   ```

5. **Optional manual trigger**
   ```bash
   sudo -u www-data bash -lc 'cd /opt/worldcup-predictor && .venv/bin/python main.py worldcup-auto-evaluation'
   ```

---

## 9. Rollback plan

1. **Disable timer**
   ```bash
   sudo systemctl disable --now worldcup-evaluate-results.timer
   ```

2. **Remove units**
   ```bash
   sudo rm /etc/systemd/system/worldcup-evaluate-results.service
   sudo rm /etc/systemd/system/worldcup-evaluate-results.timer
   sudo systemctl daemon-reload
   ```

3. **Restore code** from pre-Phase-44A backup if needed

4. **Restore SQLite** only if evaluation data regression (unlikely — upserts only)

5. **Restart API**
   ```bash
   sudo systemctl restart worldcup-api
   ```

Evaluation rows created by the job are safe to keep; rollback stops future auto-runs only.

---

## 10. Expected production behavior post-deploy

| Scenario | Behavior |
|----------|----------|
| Stored prediction, fixture still `NS` | Skipped (`skipped_not_finished`) |
| Fixture finishes (FT + result) | Next timer run evaluates + updates summary |
| Same fixture, unchanged result | Skipped (`skipped_unchanged`) |
| Result correction / stale test row | Upsert updates evaluation when score/status changes |
| Performance Center | Reflects new `worldcup_prediction_evaluations` count |
| Global History archive | Status badges update from evaluation rows |

---

## Final status

```
PHASE_44A_STATUS = IMPLEMENTED_VALIDATED
PHASE_44A_DEPLOY = PENDING_APPROVAL
```

**STOP — No production deploy performed.**
