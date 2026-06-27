# Phase 63A — Settings Drift Fix Report

**Date:** 2026-06-26  
**Production:** https://footballpredictor.it.com (`91.107.188.229`)  
**Goal:** Restore validation from 30/31 → **31/31**

---

## Executive summary

| Item | Result |
|------|--------|
| Root cause | Production `settings.py` missing Phase 61 + Phase A23 field blocks |
| Failed check | `flags:unchanged` — sentinel expects literal `UNIFIED_ENGINE_PUBLIC` in settings |
| Fix applied | Surgical insert via `scripts/apply_phase63a_settings_drift_fix.py` |
| Business logic | **Unchanged** — all inserted fields use safe repo defaults |
| Post-fix validation | **31/31 PASS** on production |

---

## Diagnosis

### Failing validation

```python
record("flags:unchanged", "UNIFIED_ENGINE_PUBLIC" in settings_py, "settings intact")
```

Production file: **483 lines**, no `UNIFIED_ENGINE_*` strings.  
Repository baseline: **511 lines**, includes Phase 61 unified engine + Phase A23 lifecycle blocks.

### Drift diff (repo-only lines)

Inserted after `AUTONOMOUS_DRY_RUN`:

| Field | Default | Env alias |
|-------|---------|-----------|
| `unified_engine_enabled` | `false` | `UNIFIED_ENGINE_ENABLED` |
| `unified_engine_admin_preview` | `true` | `UNIFIED_ENGINE_ADMIN_PREVIEW` |
| `unified_engine_public` | `false` | `UNIFIED_ENGINE_PUBLIC` |
| `unified_engine_compare_mode` | `true` | `UNIFIED_ENGINE_COMPARE_MODE` |
| `prediction_lifecycle_enabled` | `true` | `PREDICTION_LIFECYCLE_ENABLED` |
| `prediction_lifecycle_eval_limit` | `100` | `PREDICTION_LIFECYCLE_EVAL_LIMIT` |

No `.env.production` overrides were required (`NO_ENV_UNIFIED` before fix).

---

## Fix applied

1. Backup: `/opt/worldcup-predictor/backups/phase63a-settings-20260626-210051`
2. Ran `apply_phase63a_settings_drift_fix.py` (config-only patch)
3. Restarted `worldcup-api`
4. Re-ran `validate_hotfix_market_level_result_evaluation.py`

### Validation result

```
Hotfix market-level evaluation validation: 31/31 PASS
  [PASS] flags:unchanged — settings intact
```

---

## What was NOT changed

- Prediction engines (WDE, EGIE, specialists)
- Stripe / auth / subscriptions
- Unified Engine public flags (remain `false`)
- Stored prediction payloads

---

## Rollback

```bash
BACKUP=/opt/worldcup-predictor/backups/phase63a-settings-20260626-210051
cp $BACKUP/settings.py.pre /opt/worldcup-predictor/worldcup_predictor/config/settings.py
systemctl restart worldcup-api
```

---

**Target met: 31/31 validation pass.**
