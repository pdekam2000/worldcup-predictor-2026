# HOTFIX PACK 4 — Global App Version Badge Report

**Date:** 2026-06-20  
**Final status:** `APP_VERSION_BADGE_DEPLOYED_OK`

---

## Version value

| Field | Value |
|-------|--------|
| `app_version` | **A23.0.0** |
| `build_label` | **hotfix-pack4** |
| `build_date` | **2026-06-20** |
| `commit` | **d8fd1ab** (overridden at deploy via `DEPLOY_COMMIT`) |

**Public badge (desktop):** `vA23.0.0 · hotfix-pack4 · prod`  
**Public badge (mobile):** `vA23.0.0`

---

## Why

After each hotfix deploy, there was no quick way to confirm frontend and backend were on the same build. The global header badge + `/api/version` endpoint make deploy verification immediate.

---

## Files changed

| Area | File |
|------|------|
| Manifest (single source) | `app_version.manifest.json` |
| Backend config | `worldcup_predictor/config/app_version.py` |
| API | `worldcup_predictor/api/routes/health.py` — extended `GET /api/version` |
| Frontend constants | `base44-d/src/lib/appVersion.js` |
| Build metadata | `base44-d/public/build-metadata.json` |
| UI component | `base44-d/src/components/layout/AppVersionBadge.jsx` |
| Layouts | `DashboardLayout.jsx`, `OwnerLayout.jsx` |
| Vite cache bust | `base44-d/vite.config.js` — `__APP_VERSION__` defines |
| Scripts | `scripts/sync_app_version_metadata.py`, `scripts/validate_hotfix_pack4_app_version_badge.py` |

---

## API response (`GET /api/version`)

```json
{
  "app_version": "A23.0.0",
  "build_label": "hotfix-pack4",
  "build_date": "2026-06-20",
  "commit": "d8fd1ab",
  "environment": "production",
  "environment_short": "prod",
  "display_short": "vA23.0.0",
  "display_full": "vA23.0.0 · hotfix-pack4 · prod",
  "project": "WorldCup Predictor 2026",
  "api_version": "1.0"
}
```

---

## UI behavior

| User | Badge |
|------|--------|
| All users | Short version on mobile; full label on desktop |
| Owner / Admin | Click badge → popover with frontend + backend version, build date, commit, environment, API version |
| Mismatch | Warning if frontend commit ≠ backend commit |

Visible on all `DashboardLayout` routes: dashboard, matches, archive, accuracy, admin, paper betting, etc. Owner layout includes the same badge.

---

## Validation

```bash
python scripts/validate_hotfix_pack4_app_version_badge.py
```

**Local: 22/22 PASS** — `APP_VERSION_BADGE_DEPLOYED_OK`

---

## Deploy workflow (future hotfixes)

1. Bump `app_version.manifest.json` (`app_version`, `build_label`, `build_date`, `commit`).
2. Run `python scripts/sync_app_version_metadata.py`.
3. Build frontend + deploy backend.
4. Confirm header badge and `GET /api/version` match.

---

## Production smoke

| Endpoint | Expected |
|----------|----------|
| `GET /api/version` | 200, `app_version` present |
| `/matches` | Badge in header |
| `/archive` | Badge in header |
| `/accuracy` | Badge in header |

---

## Rollback

1. Restore `frontend_dist_pre.tar.gz` from backup.
2. Revert `app_version.manifest.json` and restart `worldcup-api`.
3. Remove `AppVersionBadge` import from layouts if full rollback needed.

---

## Untouched

WDE, EGIE, prediction models, calibration, scoring, billing, subscriptions — **no changes**.
