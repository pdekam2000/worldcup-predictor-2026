# Emergency Hotfix — Blank Website After Deploy

**Date:** 2026-06-26  
**Site:** https://footballpredictor.it.com  
**Mode:** Diagnose → Fix → Validate → Report

---

## Executive summary

| Item | Result |
|------|--------|
| **Root cause** | React runtime crash on load — missing imports in Phase 64 files |
| **Backend** | OK — API healthy throughout |
| **Nginx** | OK — correct root, config valid |
| **Frontend build** | Was present but JS crashed before render |
| **Fix** | Restore `useEffect` + `Link` imports; rebuild + redeploy |
| **Final status** | **`WEBSITE_RESTORED`** |

---

## Root cause

Phase 64 soft-launch changes introduced **two JavaScript ReferenceErrors** at app bootstrap, preventing React from mounting → blank white page.

| File | Bug | Error |
|------|-----|-------|
| `base44-d/src/components/ScrollToTop.jsx` | `useEffect` used but not imported after analytics edit | `ReferenceError: useEffect is not defined` |
| `base44-d/src/components/CookieConsent.jsx` | `Link` used but import removed when adding analytics | `ReferenceError: Link is not defined` |

Both components load on every page (`App.jsx` → `ScrollToTop`, `CookieConsent`), so the entire SPA failed before any route rendered.

**Not the cause:** nginx misconfig, missing dist, API outage, wrong `VITE_API_BASE_URL`, or service worker (none registered).

---

## Diagnostics performed

### 1. Services

```
worldcup-api: active (running)
nginx -t:     syntax ok
nginx:        active (running)
```

### 2. Frontend files

| Check | Result |
|-------|--------|
| Nginx root | `/var/www/worldcup/frontend/dist` |
| `index.html` | Present (2559 bytes) |
| JS bundle (broken deploy) | `/assets/index-D0RcQZEd.js` (1.5 MB) |
| CSS bundle | `/assets/index-CY27vWEY.css` (117 KB) |
| Build source | `/opt/worldcup-predictor/base44-d` |

`index.html` correctly referenced `/assets/index-D0RcQZEd.js` — assets existed and returned **HTTP 200**, but React crashed at runtime.

### 3. API health

```json
curl http://127.0.0.1:8000/api/health        → {"status":"ok"}
curl https://footballpredictor.it.com/api/health → {"status":"ok"}
```

### 4. Nginx logs

Recent errors were historical API restarts (connection refused during deploy windows). No frontend 404 on JS/CSS for current bundle. Access log showed browsers receiving `index.html` + assets **200** — consistent with JS runtime failure, not missing files.

### 5. Secondary finding (non-fatal)

`manifest.json` is **missing** from dist. Nginx SPA fallback serves `index.html` for `/manifest.json` (977-byte gzip responses in access log). Does not cause blank page; optional follow-up.

---

## Fix applied

1. **Restored imports:**
   - `ScrollToTop.jsx` → `import { useEffect } from "react"`
   - `CookieConsent.jsx` → `import { Link } from "react-router-dom"`

2. **Rebuilt frontend on production:**
   ```bash
   cd /opt/worldcup-predictor/base44-d
   npm run build
   rsync -a --delete dist/ /var/www/worldcup/frontend/dist/
   systemctl reload nginx
   ```

3. **New asset hashes (cache bust):**
   - JS: `/assets/index-CFmAGVR2.js` (200)
   - CSS: `/assets/index-CY27vWEY.css` (unchanged hash, 200)
   - Old JS `index-D0RcQZEd.js` → **404** (removed by `--delete`)

4. **Cache:** `index.html` already has `Cache-Control: no-cache, no-store, must-revalidate` in nginx. New hashed JS forces fresh download.

---

## Smoke test results (post-fix)

| Test | Result |
|------|--------|
| `GET /` | 200, 2559 bytes, script → `index-CFmAGVR2.js` |
| `GET /assets/index-CFmAGVR2.js` | 200 |
| Old bundle `index-D0RcQZEd.js` | 404 (expected) |
| `/login` | 200 |
| `/archive` | 200 |
| `/results` | 200 |
| `/api/health` | 200 `{"status":"ok"}` |

Phase 63 brand assets preserved (gold/warm-white CSS in `index-CY27vWEY.css`).

---

## Constraints honored

- No prediction engine / WDE / EGIE changes  
- No auth / subscription changes  
- Unified Engine public flags unchanged  
- Phase 63 theme + settings drift fixes preserved  

---

## Rollback reference

Prior frontend backup:
`/opt/worldcup-predictor/backups/deploy-hotfix-market-level-20260626-205016/frontend_dist_pre.tar.gz`

---

## Recommendations

1. Add a **pre-deploy frontend smoke** step: `npm run build` + grep built bundle loads without missing imports (or run `vite build` in CI with eslint).
2. Add **`manifest.json`** to `base44-d/public/` to stop SPA fallback noise.
3. Users seeing blank page should **hard refresh** (Ctrl+Shift+R) once — old cached `index.html` may reference deleted JS hash.

---

### Final status: **`WEBSITE_RESTORED`**

**STOP after report.**
