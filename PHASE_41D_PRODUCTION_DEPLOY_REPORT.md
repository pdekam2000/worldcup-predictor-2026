# PHASE 41D — Production Deploy Report (Change Password in Settings)

**Date:** 2026-06-21  
**Server:** `91.107.188.229` — https://footballpredictor.it.com  
**Phase:** 41D — User Change Password in Settings  
**Status:** **DEPLOYED & VERIFIED**

---

## Executive summary

Phase 41D is live in production. Backend `POST /api/auth/change-password`, frontend Settings security form, and validation/smoke scripts are deployed. Backup taken before deploy. All production smoke tests **PASS**. Automated validation **22/22 PASS** (after frontend bundle check fix).

**Not changed:** prediction engine, subscription/Stripe logic, existing user passwords (except ephemeral smoke-test users).

---

## Backup path

```
/opt/worldcup-predictor/backups/deploy-phase41d-20260621-064639/
```

| Artifact | Description |
|----------|-------------|
| `pre_deploy_commit.txt` | Git HEAD before deploy |
| `postgres.dump` | PostgreSQL pg_dump (custom format) |
| `frontend_dist/` | Previous `/var/www/worldcup/frontend/dist` |
| `football_intelligence.db` | SQLite snapshot |
| `worldcup-api.service` | systemd unit copy |
| `repo_snapshot_pre.tar.gz` | Pre-deploy auth route + change_password module |
| `validate_41d.log` | Validation output |
| `smoke.log` | Smoke test output (if captured in re-run) |

---

## Deployed commit / files

**Pre-deploy git commit (server):** `267812e6e1c71258b78373161ade915c00b3ed71`

Phase 41D was deployed via tarball overlay (not a new git commit on server).

| Path | Action |
|------|--------|
| `worldcup_predictor/auth/change_password.py` | **Added** |
| `worldcup_predictor/api/routes/auth.py` | **Updated** — `POST /api/auth/change-password` |
| `scripts/validate_phase41d_change_password.py` | **Added** |
| `scripts/deploy_phase41d_production.sh` | **Added** |
| `scripts/deploy_phase41d_smoke.sh` | **Added** |
| `/var/www/worldcup/frontend/dist/` | **Rebuilt & replaced** |
| `base44-d/src/api/authApi.js` | `changePassword()` (in frontend bundle) |
| `base44-d/src/pages/SettingsPage.jsx` | Change Password form |
| `base44-d/src/pages/Login.jsx` | Post-change re-login message |

**Frontend bundle:** `/var/www/worldcup/frontend/dist/assets/index-B7q7kpNK.js` (contains `/api/auth/change-password`)

---

## Commands run

### Local (pack & upload)

```powershell
cd base44-d
npm run build

# Pack tarball: backend + scripts + _deploy_frontend_dist
tar -czf phase41d_deploy.tar.gz ...

scp phase41d_deploy.tar.gz root@91.107.188.229:/tmp/phase41d_deploy.tar.gz
scp scripts/deploy_phase41d_production.sh scripts/deploy_phase41d_smoke.sh root@91.107.188.229:/opt/worldcup-predictor/scripts/
```

### Production

```bash
sed -i 's/\r$//' /opt/worldcup-predictor/scripts/deploy_phase41d_*.sh
chmod +x /opt/worldcup-predictor/scripts/deploy_phase41d_*.sh

bash /opt/worldcup-predictor/scripts/deploy_phase41d_production.sh /tmp/phase41d_deploy.tar.gz

# Post-deploy smoke (re-run after CRLF fix)
bash /opt/worldcup-predictor/scripts/deploy_phase41d_smoke.sh

# Validation
sudo -u www-data env PYTHONPATH=/opt/worldcup-predictor bash -lc \
  'cd /opt/worldcup-predictor && set -a && source .env.production && set +a && \
   .venv/bin/python scripts/validate_phase41d_change_password.py'
```

**Services restarted:**

```bash
systemctl restart worldcup-api
systemctl reload nginx
```

---

## Smoke test results

```
=== Phase 41D smoke ===
SMOKE_PASS: /api/health 200
SMOKE_PASS: login 200 + jwt
SMOKE_PASS: settings api 200
SMOKE_PASS: settings page 200
SMOKE_PASS: wrong current password 400 current_password_invalid
SMOKE_PASS: change password 200 password_changed=true
SMOKE_PASS: old jwt invalidated 401
SMOKE_PASS: login with new password 200
SMOKE_ALL_PASS
```

| Test | Result |
|------|--------|
| `GET /api/health` | ✅ 200 |
| Login (ephemeral test user) | ✅ 200 + JWT |
| Settings API (`/api/user/settings`) | ✅ 200 |
| Settings page (`/settings`) | ✅ 200 |
| Change password — wrong current | ✅ 400 `current_password_invalid` |
| Change password — valid | ✅ 200 `password_changed=true` |
| Old JWT after change | ✅ 401 (token_version bump) |
| Login with new password | ✅ 200 |

Ephemeral smoke users cleaned up after test.

---

## Validation result

```
Phase 41D validation: 22/22 PASS
```

Run on production against live PostgreSQL + FastAPI TestClient.

---

## Final production status

| Component | Status |
|-----------|--------|
| `worldcup-api` | **active** |
| `nginx` | **active** |
| `GET /api/health` | `{"status":"ok"}` |
| `POST /api/auth/change-password` | **live** |
| Settings UI Change Password | **live** (frontend dist deployed) |
| Prediction engine | **unchanged** |
| Subscription / Stripe | **unchanged** |

**User flow:** Settings → Security → Change Password → success → logout → login page message → sign in with new password.

---

## Rollback command

```bash
BACKUP=/opt/worldcup-predictor/backups/deploy-phase41d-20260621-064639
APP=/opt/worldcup-predictor
FRONTEND=/var/www/worldcup/frontend/dist

# Restore backend files from snapshot
tar xzf "${BACKUP}/repo_snapshot_pre.tar.gz" -C "${APP}"
# If change_password.py did not exist pre-deploy, remove it:
rm -f "${APP}/worldcup_predictor/auth/change_password.py"

# Restore frontend
rm -rf "${FRONTEND}"
cp -a "${BACKUP}/frontend_dist/." "${FRONTEND}/"
chown -R www-data:www-data "${FRONTEND}"

# Optional: restore PostgreSQL (only if password changes must be reverted)
# pg_restore -d "$DATABASE_URL" --clean "${BACKUP}/postgres.dump"

systemctl restart worldcup-api
systemctl reload nginx

curl -sf http://127.0.0.1:8000/api/health
```

No Alembic migration was required for Phase 41D — rollback is code + frontend only.

---

**Phase 41D production deploy complete.**
