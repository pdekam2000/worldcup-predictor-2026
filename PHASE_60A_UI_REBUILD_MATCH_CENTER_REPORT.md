# PHASE 60A — UI Rebuild + Match Center Control Panel

**Date:** 2026-06-20  
**Mode:** Analyze → Implement → Validate → Report  
**Deploy status:** **NOT DEPLOYED** — awaiting owner approval  

---

## Final recommendation

### `READY_TO_DEPLOY`

Frontend build passes (66/66 validation checks). No prediction-engine, WDE, EGIE, auth, Stripe, or subscription logic was changed. All legacy routes remain reachable; navigation is simplified and grouped per spec.

**Caveats (non-blocking):**
- Some inner pages (Dashboard, Archive, Accuracy, Goal Timing sub-pages) still use terminal/dark card components inside the new light shell — functional but not fully re-skinned.
- Live API smoke tests were skipped locally (`PHASE60A_BASE_URL` not set); run on staging/production before go-live.

---

## What changed

### Part A — UI structure cleanup

Navigation restructured into five groups:

| Section | Items |
|---------|--------|
| **Main** | Dashboard, Match Center, Best Tips, Combo Builder |
| **Predictions** | Classic Predictions, Elite Goal Intelligence, Goal Timing, Prediction Archive, Accuracy Center, Prediction Results |
| **Data** | Leagues & Competitions, World Cup 2026, UCL, UEL, UECL, API/Data Health |
| **Account** | Subscription, Profile, Settings |
| **Admin** (role-gated) | Admin Dashboard, Elite Shadow Preview, Learning Dashboard, System Health |

- Admin links hidden from non-admin users via `roles` in `navConfig.js`.
- Shadow/experimental tips not exposed in public nav; Elite Shadow remains `/admin/elite-shadow` (super_admin only).
- Removed crowded duplicate entries (Combo Tips, AI Betting Plan, Watchlist, etc. from primary nav — **routes preserved**).

### Part B — Visual design

- Dashboard shell switched to **white / warm gray** background with **amber/gold** accents.
- `theme-saas` CSS scope in `index.css` lightens cards inside the authenticated layout.
- Landing, login, register, and owner console remain on their existing themes.

### Part C — Match Center

- Light `SaasPageHeader` and white match cards (`EliteMatchCard variant="saas"`).
- Existing competition filters (`LeagueSelector`), status tabs (upcoming/live/finished), and prediction expand panel unchanged functionally.
- Match detail route `/matches/:fixtureId` unchanged.

### Part D — Best Tips

- **New page:** `/best-tips` → `BestTipsPage.jsx`
- Uses existing `GET /api/best-tips` via `fetchBestTips()`.
- Filters: competition, market, confidence tier, kickoff window, high-confidence toggle.
- Public users see Classic engine tips only; shadow referenced only in admin footnote.

### Part E — Combo Builder

- `/combo-tips` retained; `/combo-builder` redirects to it.
- Nav label **Combo Builder**; page retitled with risk disclaimers and light styling.
- Existing `buildCombos()` logic unchanged.

### Part F — Archive + Accuracy

- `archiveStatus.js` already maps correct/wrong/partial/pending with green/red/violet/amber.
- `AccuracyCenter.jsx` already documents quarantined exclusion — no backend change.

### Part G — Admin Elite Shadow Preview

- Route `/admin/elite-shadow` unchanged (super_admin).
- **New route:** `/admin/learning` → `AdminLearningDashboard.jsx` (was orphaned).

### Part H — Backend/API safety

- **No new backend endpoints.**
- **No changes** to `scoring_engine.py`, `weighted_decision_engine.py`, calibration, billing, or auth.
- All pages continue using existing APIs (`/api/matches`, `/api/best-tips`, `/api/history`, `/api/performance/summary`, etc.).

---

## Routes

### Added

| Route | Page |
|-------|------|
| `/best-tips` | BestTipsPage |
| `/admin/learning` | AdminLearningDashboard |

### Aliases / redirects

| From | To |
|------|-----|
| `/combo-builder` | `/combo-tips` |
| `/world-cup` | `/matches?competition=world_cup_2026` (existing) |
| `/analytics/accuracy` | `/accuracy` (existing) |
| `/account/settings` | `/settings` (existing) |
| `/history` | `/archive` (existing) |

### Preserved (not in primary nav, still work)

`/betting-plan`, `/paper-betting`, `/watchlist`, `/daily-briefing`, `/notifications`, `/research/highlights`, `/favorites`, `/alerts`, `/elite/world-cup`, `/admin/performance`, `/admin/predops`, `/super-admin`, `/owner/*`

---

## Files changed

| File | Change |
|------|--------|
| `base44-d/src/lib/navConfig.js` | Phase 60A nav structure |
| `base44-d/src/lib/phase60aTheme.js` | **New** theme tokens |
| `base44-d/src/components/saas/SaasPageHeader.jsx` | **New** light header + card |
| `base44-d/src/components/dashboard/DashboardLayout.jsx` | Light SaaS shell |
| `base44-d/src/components/layout/SidebarNav.jsx` | `saas` variant styles |
| `base44-d/src/index.css` | `.theme-saas` component overrides |
| `base44-d/src/pages/BestTipsPage.jsx` | **New** |
| `base44-d/src/pages/MatchCenter.jsx` | Light header + saas cards |
| `base44-d/src/pages/ComboTipsPage.jsx` | Combo Builder branding + light UI |
| `base44-d/src/components/match-center/EliteMatchCard.jsx` | `variant="saas"` |
| `base44-d/src/App.jsx` | Routes for best-tips, admin/learning, combo-builder redirect |
| `scripts/validate_phase60a_ui_rebuild_match_center.py` | **New** validation script |

**Not modified:** `worldcup_predictor/prediction/*`, `weighted_decision_engine.py`, EGIE modules, Stripe/billing, auth.

---

## Validation results

```
python scripts/validate_phase60a_ui_rebuild_match_center.py
Phase 60A validation: 66/66 passed
npm run build — SUCCESS
```

Checks include: nav structure, admin gating, route preservation, Match Center filters, Best Tips/Combo Builder render paths, archive status colors, accuracy quarantine note, engine files untouched, frontend build, `build_best_tips()` import.

---

## Known limitations

1. **Partial theme migration** — Dashboard, Archive, Accuracy, Goal Timing, and Settings pages still mix terminal-dark inner components with the new light shell.
2. **Best Tips engine label** — API returns Classic stored predictions only; EGIE tips are accessed via Goal Timing / Match detail, not merged into Best Tips list yet.
3. **Screenshots** — Not captured in this environment; verify visually after deploy on staging.
4. **Mobile** — Responsive layout inherited from existing components; full mobile QA recommended on owner devices.

---

## Rollback plan

1. Restore previous `navConfig.js`, `DashboardLayout.jsx`, `SidebarNav.jsx`, `index.css` from git.
2. Remove `BestTipsPage.jsx`, `SaasPageHeader.jsx`, `phase60aTheme.js`.
3. Revert `App.jsx` route additions.
4. Rebuild frontend: `cd base44-d && npm run build`
5. Redeploy `dist/` to production nginx static root.

Backup tag suggestion: `phase60a-ui-rebuild-YYYYMMDD-HHMMSS`

---

## Deploy steps (when approved)

1. **Backup** production frontend dist and relevant env on `91.107.188.229`.
2. **Build** locally or on CI:
   ```bash
   cd base44-d && npm run build
   ```
3. **Validate** on staging:
   ```bash
   PHASE60A_BASE_URL=https://your-domain python scripts/validate_phase60a_ui_rebuild_match_center.py
   ```
4. **Deploy** frontend dist per existing hotfix pattern (`scripts/prod_deploy_phase6_frontend.sh` or tarball unpack).
5. **Smoke test:** login, register, `/matches`, `/best-tips`, `/combo-builder`, `/subscription`, admin shadow (super_admin), non-admin must not see admin nav.
6. **No backend restart required** unless serving static files from a new path.

---

## Owner sign-off

- [ ] Navigation grouping approved  
- [ ] Light theme approved  
- [ ] Match Center behavior verified on live data  
- [ ] Best Tips / Combo Builder reviewed  
- [ ] Deploy to production authorized  

**STOP — awaiting owner approval before production deploy.**
