# PROJECT ASSET / DATABASE / GITHUB AUDIT REPORT

**Phase:** PROJECT-ASSET-AUDIT-1  
**Generated:** 2026-07-01T17:41:16.593538  
**Mode:** Read-only audit — no changes performed

## 1. Executive summary

- **Primary local workspace:** `C:\Users\kaman\Desktop\Footbal`
- **Production server code:** `/opt/worldcup-predictor` (91.107.188.229)
- **GitHub repo:** https://github.com/pdekam2000/worldcup-predictor-2026.git
- **GitHub `main` commit:** `4dd87d2f99b9…`
- **Local commit:** `d143e98f2096…` (**ahead 1**, behind 0)
- **Server commit:** `4dd87d2f99b9…` (matches GitHub main; extensive dirty tree)
- **Local dirty:** 30 modified + 580 untracked
- **GitHub status:** Local is **ahead** of origin/main; GitHub does **not** contain latest local commit or most new modules

## 2. Canonical database conclusion

- **Local candidate:** `C:\Users\kaman\Desktop\Footbal\data\football_intelligence.db`
- **Server candidate:** `/opt/worldcup-predictor/data/football_intelligence.db`
- **Type:** SQLite primary intelligence DB; PostgreSQL via DATABASE_URL for SaaS layer
- **Confidence:** 85/100

**Reasons:**
- Local SQLITE_PATH default football_intelligence.db exists and is largest active DB
- Local odds_snapshots count matches expected production scale (~2200+)
- Local DB has ECSE production tables present
- Config references DATABASE_URL and/or SQLITE_PATH env vars
- Production server uses /opt/worldcup-predictor/data/football_intelligence.db via systemd
- WARNING: server DB row counts differ significantly from local — not the same copy

**Do NOT delete:**
- `data/football_intelligence.db (local active)`
- `/opt/worldcup-predictor/data/football_intelligence.db (production active)`
- `data/backups/*.db until consolidation plan approved`
- `data/oddalerts_csv/ staged CSV data`

## 3. Environment table

| Environment | Path | Git commit | Dirty | DB path | Notes |
|-------------|------|------------|-------|---------|-------|
| Local PC | `C:\Users\kaman\Desktop\Footbal` | `d143e98f2096` | yes (610 lines) | `data/football_intelligence.db` (~31GB) | Ahead of GitHub; owner modules local |
| GitHub origin/main | remote | `4dd87d2f99b9` | n/a | n/a | Published baseline |
| Production server | `/opt/worldcup-predictor` | `4dd87d2f99b9` | yes (~2032 lines) | `data/football_intelligence.db` (~9.5GB) | systemd active; missing new ECSE tables |

## 4. Source code gap table

| Module | Local | GitHub tracked | Server | Status |
|--------|-------|----------------|--------|--------|
| owner_daily workflow | True | False | None | modified_uncommitted |
| owner_predict_eval | True | False | False | modified_uncommitted |
| owner_manual_exact | True | False | False | modified_uncommitted |
| OddAlerts CSV pipeline | True | False | None | modified_uncommitted |
| ECSE OddAlerts shadow | True | False | None | modified_uncommitted |
| ECSE OddAlerts monitor | True | False | None | modified_uncommitted |
| Historical CSV ingest | True | False | None | modified_uncommitted |
| WDE shadow retrain | True | False | None | modified_uncommitted |
| manual exact score report | True | False | None | modified_uncommitted |
| knockout prediction eval | True | False | None | modified_uncommitted |
| Owner Lab API routes | True | False | None | modified_uncommitted |
| database migrations | True | True | None | modified_uncommitted |

## 5. Database inventory table

| DB path | Size (MB) | Tables | Key counts | Role |
|---------|-----------|--------|------------|------|
| `football_intelligence.db` | 31247.54 | 109 | fixtures=2463, fixture_results=2216, odds_snapshots=2236, worldcup_stored_predictions=185, ecse_prediction_snapshots=18, ecse_oddalerts_shadow_predictions=197, ecse_oddalerts_shadow_monitor=0 | likely_canonical_local |
| `football_intelligence_before_oddalerts_csv_promotion_20260701_034614.db` | 27555.94 | 107 | fixtures=2451, fixture_results=2216, odds_snapshots=2015, worldcup_stored_predictions=173, ecse_prediction_snapshots=8 | backup |
| `football_intelligence_pre_data1d_20260629_090902.db` | 5055.29 | 76 | fixtures=2161, fixture_results=1929, odds_snapshots=1443, worldcup_stored_predictions=48 | backup |
| `football_intelligence_pre_data1c_20260629_084258.db` | 3613.05 | 76 | fixtures=2161, fixture_results=1929, odds_snapshots=1443, worldcup_stored_predictions=48 | backup |
| `football_intelligence_pre_data1c_20260629_084215.db` | 3613.03 | 75 | fixtures=2161, fixture_results=1929, odds_snapshots=1443, worldcup_stored_predictions=48 | backup |
| `football_intelligence_pre_data1b_20260629_061845.db` | 470.42 | 74 | fixtures=2161, fixture_results=1929, odds_snapshots=1443, worldcup_stored_predictions=48 | backup |
| `phase46d_validation.db` | 0.35 | 41 | fixtures=1, fixture_results=0, odds_snapshots=0, worldcup_stored_predictions=0 | test_or_validation |
| `phase46c1_validation.db` | 0.34 | 40 | fixtures=2, fixture_results=2, odds_snapshots=0, worldcup_stored_predictions=0 | test_or_validation |
| `phase46c2_validation.db` | 0.34 | 40 | fixtures=0, fixture_results=0, odds_snapshots=0, worldcup_stored_predictions=0 | test_or_validation |
| `phase46c3_validation.db` | 0.34 | 40 | fixtures=0, fixture_results=0, odds_snapshots=0, worldcup_stored_predictions=0 | test_or_validation |
| `phase44a_validation.db` | 0.32 | 39 | fixtures=2, fixture_results=1, odds_snapshots=0, worldcup_stored_predictions=2 | test_or_validation |
| `phase45b_validation.db` | 0.32 | 39 | fixtures=2, fixture_results=1, odds_snapshots=0, worldcup_stored_predictions=2 | test_or_validation |
| `phase46b_validation.db` | 0.32 | 39 | fixtures=1, fixture_results=0, odds_snapshots=0, worldcup_stored_predictions=5 | test_or_validation |
| `_phase30e_test.db` | 0.26 | 31 | fixtures=1, fixture_results=0, odds_snapshots=0 | test_or_validation |
| `worldcup_predictor.db` | 0.0 | 0 |  | other |

## 6. Generated data / artifact inventory

| Folder | Size (MB) | Files | Git track? | Backup? |
|--------|-----------|-------|------------|---------|
| `artifacts` | 685.68 | 1351 | no | yes |
| `reports` | 0.96 | 110 | no | yes |
| `reports/owner` | 0.09 | 29 | no | yes |
| `logs` | 0.24 | 13 | no | yes |
| `data/external_historical_csv` | 77.1 | 119 | no | yes |
| `data/oddalerts_csv` | 3883.66 | 892 | no | yes |
| `data/research` | 30.35 | 4 | no | yes |
| `data/backups` | 40307.72 | 5 | no | yes |
| `models/shadow` | 4.93 | 5 | no | yes |
| `.cache` | 193.37 | 12600 | no | yes |
| `data/evaluation` | 0.0 | 3 | no | yes |

## 7. Secret risk summary

No secret **values** printed in this audit.

| File | Severity | Note |
|------|----------|------|
| `.streamlit/secrets.example.toml` | medium | review whether secrets should be tracked |
| `EMERGENCY_OWNER_PASSWORD_RECOVERY_REPORT.md` | medium | review whether secrets should be tracked |
| `PHASE_41C_OWNER_LOGIN_PASSWORD_RESET_REPORT.md` | medium | review whether secrets should be tracked |
| `PHASE_41D_CHANGE_PASSWORD_SETTINGS_REPORT.md` | medium | review whether secrets should be tracked |
| `_pack_phase41d/scripts/validate_phase41d_change_password.py` | medium | review whether secrets should be tracked |
| `_pack_phase41d/worldcup_predictor/auth/change_password.py` | medium | review whether secrets should be tracked |
| `alembic/versions/006_password_reset_tokens.py` | medium | review whether secrets should be tracked |
| `artifacts/oa3_token_capabilities.json` | medium | review whether secrets should be tracked |
| `artifacts/oa4_token_capabilities.json` | medium | review whether secrets should be tracked |
| `base44-d/src/components/auth/PasswordInput.jsx` | medium | review whether secrets should be tracked |
| `base44-d/src/pages/ForgotPassword.jsx` | medium | review whether secrets should be tracked |
| `base44-d/src/pages/ResetPassword.jsx` | medium | review whether secrets should be tracked |
| `credentials/gmail_oauth_client.json` | high | review whether secrets should be tracked |
| `credentials/gmail_oauth_client1.json` | high | review whether secrets should be tracked |
| `data/dev/email_verification_tokens.jsonl` | medium | review whether secrets should be tracked |
| `data/dev/password_reset_tokens.jsonl` | medium | review whether secrets should be tracked |
| `data/imports/oddalerts_probability_exports/.gmail_token.json` | high | review whether secrets should be tracked |
| `deploy_staging_phase40a/base44-d/src/components/auth/PasswordInput.jsx` | medium | review whether secrets should be tracked |
| `deploy_staging_phase40a/worldcup_predictor/auth/jwt_tokens.py` | medium | review whether secrets should be tracked |
| `requirements-oddalerts-gmail.txt` | medium | review whether secrets should be tracked |
| `scripts/bump_owner_token_version.py` | medium | review whether secrets should be tracked |
| `scripts/emergency_owner_password_diagnose.sh` | medium | review whether secrets should be tracked |
| `scripts/emergency_owner_password_restore.sh` | medium | review whether secrets should be tracked |
| `scripts/oddalerts_gmail_csv_downloader.py` | medium | review whether secrets should be tracked |
| `scripts/reset_owner_login_password.py` | medium | review whether secrets should be tracked |
| `scripts/sync_pg_password_from_env.sh` | medium | review whether secrets should be tracked |
| `scripts/validate_oddalerts_gmail_exporter.py` | medium | review whether secrets should be tracked |
| `scripts/validate_phase41c_owner_login_password_reset.py` | medium | review whether secrets should be tracked |
| `scripts/validate_phase41d_change_password.py` | medium | review whether secrets should be tracked |
| `worldcup_predictor/auth/change_password.py` | medium | review whether secrets should be tracked |
| `worldcup_predictor/auth/jwt_tokens.py` | medium | review whether secrets should be tracked |
| `worldcup_predictor/auth/password_reset.py` | medium | review whether secrets should be tracked |
| `worldcup_predictor/auth/passwords.py` | medium | review whether secrets should be tracked |
| `worldcup_predictor/data_import/oddalerts_gmail_exporter.py` | medium | review whether secrets should be tracked |
| `worldcup_predictor/database/postgres/repositories/password_reset.py` | medium | review whether secrets should be tracked |
| `ODDALERTS_LOWER_BAND_GMAIL_IMPORT_REPORT.md` | medium | working tree status ?? |
| `ODDALERTS_TODAY_GMAIL_CSV_DOWNLOAD_REPORT.md` | medium | working tree status ?? |
| `artifacts/oddalerts_lower_band_gmail_download_summary_20260630.json` | medium | working tree status ?? |
| `artifacts/oddalerts_today_gmail_csv_download_summary_20260630.json` | medium | working tree status ?? |
| `artifacts/oddalerts_today_gmail_csv_download_validation.json` | medium | working tree status ?? |
| `artifacts/oddalerts_today_gmail_market_coverage_20260630.json` | medium | working tree status ?? |
| `deployment/ecse_x2_m7_enablement_snippet.env` | medium | working tree status ?? |
| `scripts/download_today_oddalerts_csv_from_gmail.py` | medium | working tree status ?? |
| `scripts/validate_today_oddalerts_gmail_csv_download.py` | medium | working tree status ?? |
| `scripts/watch_oddalerts_lower_band_gmail.py` | medium | working tree status ?? |
| `worldcup_predictor/data_import/oddalerts_today_gmail_downloader.py` | medium | working tree status ?? |

## 8. Recommended consolidation plan (later — not executed)

1. Backup canonical DB on local and server separately
2. Freeze production writes during any merge window
3. Git: commit local modules in logical chunks
4. Push to GitHub after review
5. Server: pull/deploy only after DB strategy decided
6. Decide single canonical DB or explicit local↔prod sync policy
7. Archive duplicate backup DBs only after verification
8. Update `.gitignore` for artifacts/cache/CSV/data
9. Document owner daily workflow paths

## 9. Final recommendation

**AUDIT_COMPLETE_CANONICAL_DB_IDENTIFIED; AUDIT_COMPLETE_GITHUB_BEHIND; SECRET_RISK_REVIEW_REQUIRED; LARGE_DUPLICATE_DB_REVIEW_REQUIRED; DO_NOT_CONSOLIDATE_YET**