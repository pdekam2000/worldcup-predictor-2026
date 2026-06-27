# Phase 64B — Frontend Runtime Deploy Guard Report

**Date:** 2026-06-26  
**Mode:** Preventive Hardening Only  
**Context:** Emergency blank-site fix (missing `useEffect` / `Link` imports)

---

## Executive summary

| Item | Status |
|------|--------|
| Static import guard | **Active** — ESLint critical + custom hook/router scan |
| Smoke render test | **Active** — dist assets + Vite preview route checks |
| Deploy gate script | **Active** — `scripts/frontend_deploy_guard.sh` |
| Rollback backup | **Active** — dist snapshot before every guarded deploy |
| Playwright mount test | **Optional** — skipped if not installed |
| Local validation | **PASS** |
| Production validation | **PASS** |

### Final status: **`DEPLOY_GUARD_ACTIVE`**

*(Optional upgrade: install Playwright for `#root` mount + console error checks — see Part B.)*

---

## Part A — Static import check

### 1. ESLint critical config

**File:** `base44-d/eslint.critical.config.js`  
**Script:** `npm run lint:critical`

Covers bootstrap files that can blank the entire app:

| File | Why |
|------|-----|
| `src/main.jsx` | React mount |
| `src/App.jsx` | Router + global shell |
| `src/components/ScrollToTop.jsx` | **Emergency root cause** |
| `src/components/CookieConsent.jsx` | **Emergency root cause** |
| `src/components/dashboard/DashboardLayout.jsx` | Authenticated shell |
| `src/lib/AuthContext.jsx` | Auth provider |
| Route guards | `ProtectedRoute`, `AdminRoute`, etc. |

**Rules enforced:**

- `no-undef` — catches `useEffect` without import  
- `react/jsx-no-undef` — catches `<Link>` without import  
- `react-hooks/rules-of-hooks` — invalid hook usage  

### 2. Custom import scanner

**File:** `scripts/validate_frontend_static_imports.mjs`

Scans **17 critical files** (bootstrap list + top-level `src/components/*.jsx`):

- Detects React hook **calls** without matching `from 'react'` import  
- Detects router symbols (`Link`, `useNavigate`, …) without `react-router-dom` import  

This directly catches the Phase 64 emergency bug class even when full-repo `npm run lint` is not run.

### How it would have blocked the emergency deploy

| Bug | Detection |
|-----|-----------|
| `useEffect()` without import in `ScrollToTop.jsx` | `no-undef` + custom hook scan |
| `<Link>` without import in `CookieConsent.jsx` | `react/jsx-no-undef` + custom router scan |

---

## Part B — Smoke render test

**File:** `scripts/validate_frontend_smoke_render.mjs`

### Always runs (no Playwright required)

1. Parse `dist/index.html` — require `#root` + `/assets/*.js`  
2. Verify referenced JS/CSS files exist on disk  
3. Start `vite preview` on port **4173**  
4. HTTP GET routes (expect SPA shell):

| Route | Purpose |
|-------|---------|
| `/` | Homepage |
| `/login` | Auth entry |
| `/archive` | Archive SPA |
| `/results` | Results / Best Bet Winrate |
| `/matches` | Match Center |

Each must return **200**, include `id="root"`, and reference `/assets/*.js`.

### Optional Playwright tier

If `playwright` is installed:

- Launches headless Chromium  
- Visits same routes  
- Asserts `#root` has child elements (app mounted)  
- Fails on fatal `pageerror` / console errors  

**Current state:** `PLAYWRIGHT_SKIP not installed` — preview smoke still **PASS**.

To enable full mount test:

```bash
cd base44-d && npm i -D playwright && npx playwright install chromium
```

---

## Part C — Deploy gate

**File:** `scripts/frontend_deploy_guard.sh`

### Order (must all pass before sync)

```
1. Backup current dist
2. npm run build
3. node scripts/validate_frontend_static_imports.mjs
4. node scripts/validate_frontend_smoke_render.mjs
5. rsync dist/ → /var/www/worldcup/frontend/dist/
6. nginx reload
```

### On failure

- **Does not sync** new dist  
- Writes report to `backups/frontend-deploy-{timestamp}/deploy_guard_report.txt`  
- Prints rollback one-liner  

### Usage (production)

```bash
bash /opt/worldcup-predictor/scripts/frontend_deploy_guard.sh
```

### Local dev

```bash
cd base44-d && npm run validate:deploy-guard
```

---

## Part D — Rollback safety

Before sync, guard creates:

| Artifact | Path |
|----------|------|
| Full dist snapshot | `{backup}/dist_snapshot/` |
| Previous `index.html` | `{backup}/index.html.pre` |
| Asset hashes (pre) | `{backup}/asset_hashes.pre.txt` |
| Asset hashes (post) | `{backup}/asset_hashes.post.txt` |
| Build / lint / smoke logs | `{backup}/*.log` |

### One-command rollback

```bash
cp -a /opt/worldcup-predictor/backups/frontend-deploy-YYYYMMDD-HHMMSS/dist_snapshot/. \
  /var/www/worldcup/frontend/dist/
systemctl reload nginx
```

---

## Part E — Validation results

### Local (Windows dev)

```
lint:critical          PASS
STATIC_IMPORT_GUARD    PASS (17 files)
SMOKE_RENDER           PASS (5 routes)
PLAYWRIGHT             SKIP (not installed)
```

### Production server (`91.107.188.229`)

```
lint:critical          PASS
STATIC_IMPORT_GUARD    PASS (17 files)
SMOKE_RENDER           PASS (5 routes)
PLAYWRIGHT             SKIP (not installed)
Current bundle         /assets/index-CFmAGVR2.js
```

---

## Files added / updated

| File | Purpose |
|------|---------|
| `base44-d/eslint.critical.config.js` | **NEW** — bootstrap ESLint |
| `base44-d/package.json` | `lint:critical`, `validate:deploy-guard` |
| `scripts/validate_frontend_static_imports.mjs` | **NEW** — static gate |
| `scripts/validate_frontend_smoke_render.mjs` | **NEW** — preview smoke |
| `scripts/frontend_deploy_guard.sh` | **NEW** — deploy + backup + rollback |

---

## Constraints honored

- No feature changes  
- No model / WDE / EGIE / backend logic changes  
- No public Unified Engine flags  
- Phase 63 theme preserved  

---

## Recommendations

1. **Always** use `frontend_deploy_guard.sh` for production frontend deploys (replace raw `rsync` tarball flows).  
2. Optionally add `playwright` for true JS runtime mount verification.  
3. Wire guard into CI if GitHub Actions added later.  

---

### Final status: **`DEPLOY_GUARD_ACTIVE`**

**STOP after report.**
