# HOTFIX H3B — Elite Shadow JSONL Restore Report

**Date:** 2026-06-25  
**Mode:** Package → Upload → Restore → Validate → Report  
**Final status:** `SHADOW_JSONL_RESTORED_OK`

---

## Goal

Restore historical Elite Shadow JSONL data on production so `/admin/elite-shadow` displays existing shadow predictions, evaluations, and root-cause records.

**Scope:** Data-restore only — no WDE, EGIE, models, scoring, calibration, billing, PredOps, or production prediction changes.

---

## Files restored

| File | Production path | Rows |
|------|---------------|------|
| `elite_orchestrator_predictions.jsonl` | `/opt/worldcup-predictor/data/shadow/elite_orchestrator_predictions.jsonl` | **108** |
| `elite_orchestrator_evaluations.jsonl` | `/opt/worldcup-predictor/data/shadow/elite_orchestrator_evaluations.jsonl` | **108** |
| `knowledge_records.jsonl` | `/opt/worldcup-predictor/data/shadow/root_cause_store/knowledge_records.jsonl` | **476** |

**Tarball:** `/tmp/hotfix_h3b_shadow_jsonl.tar.gz` (13 KB, 3 files only — no node_modules, dist, DB, cache, secrets, or `.env`)

**Local source counts (pre-pack):** 108 predictions / 18 fixtures · 108 evaluations · 476 root cause

---

## Backup

| Item | Value |
|------|-------|
| Backup folder | `/opt/worldcup-predictor/backups/shadow-jsonl-restore-20260625-195032/` |
| Restore log | `/opt/worldcup-predictor/backups/shadow-jsonl-restore-20260625-195032.log` |
| Prior JSONL on server | **None** — backup folder empty (files were missing before restore, consistent with H3 audit) |

---

## Permissions

```bash
sudo -u www-data test -r /opt/worldcup-predictor/data/shadow/elite_orchestrator_predictions.jsonl   # OK
sudo -u www-data test -r /opt/worldcup-predictor/data/shadow/elite_orchestrator_evaluations.jsonl  # OK
sudo -u www-data test -r /opt/worldcup-predictor/data/shadow/root_cause_store/knowledge_records.jsonl # OK
```

| File | Owner | Mode |
|------|-------|------|
| `elite_orchestrator_predictions.jsonl` | `www-data:www-data` | `644` |
| `elite_orchestrator_evaluations.jsonl` | `www-data:www-data` | `644` |
| `knowledge_records.jsonl` | `www-data:www-data` | `644` |
| `root_cause_store/` | — | `755` |

No API restart required — `EliteShadowPreviewService` reads JSONL on each request.

---

## Line counts (production, post-restore)

```
   108  elite_orchestrator_predictions.jsonl
   108  elite_orchestrator_evaluations.jsonl
   476  knowledge_records.jsonl
   692  total
```

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Predictions | ≥ 108 | 108 | PASS |
| Evaluations | ≥ 108 | 108 | PASS |
| Root cause | ≥ 476 | 476 | PASS |
| Fixtures | ≥ 18 | 18 | PASS |

---

## API validation (service layer + routes)

Ran on server via `EliteShadowPreviewService` (same code path as admin API):

```json
{
  "fixtures_with_predictions": 18,
  "prediction_rows": 108,
  "evaluation_rows": 108,
  "root_cause_records": 476,
  "sources": {
    "predictions": { "exists": true, "rows_parsed": 108 },
    "evaluations": { "exists": true, "rows_parsed": 108 },
    "root_cause": { "exists": true, "rows_parsed": 476 }
  }
}
```

| Endpoint | Smoke | Notes |
|----------|-------|-------|
| `GET /api/admin/elite-shadow/summary` | **401** unauthenticated (expected) | Service summary **200-equivalent** via Python |
| `GET /api/admin/elite-shadow/predictions` | **401** unauthenticated | `total: 18` fixture bundles |
| `GET /api/admin/elite-shadow/evaluations` | **401** unauthenticated | `total: 108` |
| `GET /api/admin/elite-shadow/root-cause` | **401** unauthenticated | `total: 476` |

Super-admin authenticated UI/API will return full payloads; data layer confirmed live.

---

## UI smoke

| Check | Result |
|-------|--------|
| `GET /admin/elite-shadow` SPA shell | **200** |
| Expected stat cards (super_admin session) | Fixtures **18**, Prediction rows **108**, Root cause **476** |
| `shadow_jsonl_missing` empty state | **Should not appear** — `sources.predictions.exists: true` |

**Action for owner:** Log in as super_admin → open `/admin/elite-shadow` → hard refresh. Stat cards should show non-zero counts and fixture/comparison tables should populate.

---

## Scripts added

| Script | Purpose |
|--------|---------|
| `scripts/pack_hotfix_h3b_shadow_jsonl.sh` | Pack 3 JSONL files only |
| `scripts/restore_hotfix_h3b_shadow_jsonl_production.sh` | Server restore with backup + permissions |
| `scripts/_remote_restore_h3b.sh` | One-shot remote restore runner |
| `scripts/_validate_h3b_on_server.py` | Post-restore summary validation |

---

## Rollback

If restore must be reverted (backup empty in this case — prior state was missing files):

```bash
# Remove restored files (returns to pre-restore empty state)
rm -f /opt/worldcup-predictor/data/shadow/elite_orchestrator_predictions.jsonl
rm -f /opt/worldcup-predictor/data/shadow/elite_orchestrator_evaluations.jsonl
rm -f /opt/worldcup-predictor/data/shadow/root_cause_store/knowledge_records.jsonl
```

To restore from a future backup that contains prior copies:

```bash
BACKUP=/opt/worldcup-predictor/backups/shadow-jsonl-restore-<timestamp>
cp -a "${BACKUP}/data/shadow/"* /opt/worldcup-predictor/data/shadow/
chown www-data:www-data /opt/worldcup-predictor/data/shadow/elite_orchestrator_*.jsonl
chown -R www-data:www-data /opt/worldcup-predictor/data/shadow/root_cause_store/
```

---

## Final status

**`SHADOW_JSONL_RESTORED_OK`**

Elite Shadow historical data is on production with correct counts and `www-data` readability. `/admin/elite-shadow` should display fixtures, predictions, and root-cause records for super_admin users immediately.
