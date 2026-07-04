# CODEBASE CONSOLIDATION 2 — Deploy Report

**Phase:** CODEBASE-CONSOLIDATION-2  
**Date:** 2026-07-01 16:27 UTC  
**Mode:** GitHub main → production (code + schema migrations only; no DB copy)

---

## Executive summary

| Item | Value |
|------|-------|
| Starting commit | `4dd87d2f99b9f2f03e0366604b332b7697f0f61a` |
| Ending commit | `7b7b08d8d6b859cde7d356426fce4af59f667e78` |
| GitHub deployed | `7b7b08d8d6b859cde7d356426fce4af59f667e78` |
| **Recommendation** | **PRODUCTION_DEPLOY_COMPLETE** |
| Block reason | — |

Production code now matches GitHub `main`. Database and runtime data preserved. No local DB copy performed.

---

## Backups

| Backup | Path |
|--------|------|
| Pre-deploy commit | `/opt/worldcup-predictor/data/backups/pre_deploy_commit_20260701_162213.txt` |
| Git diff patch | `/opt/worldcup-predictor/data/backups/pre_deploy_git_diff_20260701_162213.patch` |
| SQLite DB | `/opt/worldcup-predictor/data/backups/football_intelligence_before_code_deploy_20260701_162213.db` |
| PostgreSQL dump | `/opt/worldcup-predictor/data/backups/postgres_before_code_deploy_20260701_162213.sql` |
| Untracked source quarantine | `/opt/worldcup-predictor/data/backups/pre_deploy_untracked_source_20260701_162321` |

**Quarantined files (13)** — server-local untracked copies backed up before pull (GitHub versions are canonical):

- `config/external_historical_csv_schema.json`
- `scripts/crosswalk_external_historical_to_local_fixtures.py`
- `scripts/download_today_oddalerts_csv_from_gmail.py`
- `scripts/import_external_historical_zip.py`
- `scripts/inspect_external_historical_zip.py`
- `scripts/preview_external_historical_final_import.py`
- `scripts/validate_external_historical_zip_ingest.py`
- `scripts/validate_oddalerts_ecse_complete_coverage.py`
- `worldcup_predictor/data_import/external_historical_*.py` (3 files)
- `worldcup_predictor/data_import/oddalerts_today_gmail_downloader.py`
- `EXTERNAL_HISTORICAL_ZIP_INGEST_REPORT.md`

---

## Preflight

- Modified tracked source: **0** (no blocker)
- Untracked source: **15** (quarantined 13 that conflicted with incoming)
- Runtime/data dirty files: present (jsonl, cache) — **ignored, not touched**
- `.env` / credentials: **not modified**

Artifact: `artifacts/codebase_consolidation_2_production_preflight.json`

---

## Incoming commits (12 batches)

```
7b7b08d docs(consolidation-1): set final GitHub HEAD in report
b9203f3 docs(consolidation-1): update report with final commit hash
d8c9e8c docs(consolidation-1): report, config schemas, and consolidation runner fix
bbe2dd8 chore(consolidation): expand gitignore for code-first policy
8d62939 chore(tooling): project asset audit and consolidation runners
5552bf1 docs: phase reports and consolidation audit artifacts
0db8b1a feat(scripts): owner ECSE WDE and data pipeline CLI entrypoints
72a1dbd feat(frontend): Owner Lab ECSE panels and navigation
2974a19 feat(api): owner ECSE routes result refresh and core client updates
6e30cf5 feat(owner): daily predict eval manual exact and euro pipelines
9b24b44 feat(research): ECSE live/X2/X3/WC OddAlerts shadow and WDE historical
c229a89 feat(data-import): historical CSV OddAlerts and European import pipelines
b9b1395 feat(db): migrations repository and settings for owner/ECSE
```

Pull method: `git pull --ff-only origin main` — **fast-forward success**

---

## Dependencies

| Step | Result |
|------|--------|
| requirements.txt changed | No — pip install skipped |
| pip check | Ran (non-fatal) |
| Frontend rebuild | Skipped (no base44-d diff requiring rebuild on server path) |

Post-pull: `chown -R www-data:www-data worldcup_predictor scripts` applied for service user access.

---

## Migrations

| | Before | After |
|---|--------|-------|
| schema_version | 7 | 7 |
| PostgreSQL alembic | 014_enterprise_rbac | 014_enterprise_rbac (no new revisions) |

### Table counts

| Table | Before | After | Delta |
|-------|-------:|------:|------:|
| odds_snapshots | 1451 | 1451 | 0 |
| worldcup_stored_predictions | 48 | 48 | 0 |
| ecse_prediction_snapshots | (missing) | 0 | new table |
| ecse_oddalerts_shadow_predictions | (missing) | 0 | new table |
| ecse_oddalerts_shadow_monitor | (missing) | 0 | new table |

Migrations run:

1. `alembic upgrade head` — OK
2. `ensure_schema_compat()` — OK (created ECSE OddAlerts tables)

Row loss check: **PASS** — no existing table row decrease.

---

## Validation

| Validator | Result |
|-----------|--------|
| compileall (as root) | FAIL — `PermissionError` on new `__pycache__` dirs |
| compileall (as www-data, post-chown) | **PASS** |
| validate_project_asset_audit.py | **PASS** |
| validate_owner_daily_prediction_and_eval.py | **PASS** |
| validate_daily_oddalerts_ecse_owner_pipeline.py | **PASS** |
| validate_ecse_oddalerts_owner_lab.py | **PASS** |
| validate_ecse_oddalerts_limited_shadow_monitor.py | **PASS** |
| validate_wde_shadow_training.py | **PASS** |

Note: `scripts/audit_specialists_server.py` is a bash script with `.py` extension — pre-existing; does not affect API runtime.

---

## Services

| Service | Status |
|---------|--------|
| worldcup-api | **active** (restarted 2026-07-01 16:26 UTC) |
| nginx | active |

Health: `GET /api/health` → `{"status":"ok"}`

Version: `GET /api/version` → schema 7, migration `014_enterprise_rbac`, env `production`

---

## Skipped steps

- Frontend npm rebuild (no production dist path change required this deploy)
- Long CSV market audit (explicitly out of scope)

---

## Rollback instructions

1. `systemctl stop worldcup-api`
2. `cd /opt/worldcup-predictor && git checkout 4dd87d2f99b9f2f03e0366604b332b7697f0f61a`
3. Restore SQLite if needed:  
   `cp data/backups/football_intelligence_before_code_deploy_20260701_162213.db data/football_intelligence.db`
4. Restore PostgreSQL if needed:  
   `psql $DATABASE_URL < data/backups/postgres_before_code_deploy_20260701_162213.sql`
5. `chown www-data:www-data data/football_intelligence.db`
6. `systemctl start worldcup-api`

To restore quarantined server-local scripts (optional):  
`cp -a data/backups/pre_deploy_untracked_source_20260701_162321/* .` (only if needed; GitHub versions already deployed)

---

## Final recommendation

**PRODUCTION_DEPLOY_COMPLETE**

- GitHub `main` (`7b7b08d`) deployed to production via fast-forward pull
- Schema migrations applied safely; production data preserved
- All pipeline validators passed; API healthy after restart
- Database consolidation remains a **separate future phase**

---

*Preflight: `artifacts/codebase_consolidation_2_production_preflight.json`*  
*Orchestrator: `scripts/run_codebase_consolidation_2.py`*
