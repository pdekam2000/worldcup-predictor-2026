# PHASE 50A — UI Architecture Audit

**Mode:** Read-only audit  
**Date:** 2026-06-22  
**Scope:** `base44-d/` production frontend (Vite + React 18 + React Router + Tailwind + shadcn/ui)

**Architecture rule confirmed:** Backend prediction engine, agents, WDE, learning, and evaluation logic are **out of scope**. This audit covers presentation layer only.

---

## 1. Existing routes & pages

### Public (unauthenticated)

| Route | Page | Purpose |
|-------|------|---------|
| `/` | `Landing.jsx` | Marketing landing |
| `/login` | `Login.jsx` | Auth |
| `/register` | `Register.jsx` | Auth + invite code |
| `/forgot-password` | `ForgotPassword.jsx` | Password reset request |
| `/reset-password` | `ResetPassword.jsx` | Password reset |
| `/verify-email` | `VerifyEmailPage.jsx` | Email verification |
| `/billing/success` | `BillingCheckoutSuccess.jsx` | Stripe return |
| `/billing/cancel` | `BillingCheckoutCancel.jsx` | Stripe cancel |
| `/pricing` | `PricingPage.jsx` | Public pricing |
| `/privacy`, `/terms`, `/disclaimer`, `/contact`, `/imprint` | Legal pages | Compliance |
| `*` | `PageNotFound.jsx` | 404 |

### Authenticated (inside `DashboardLayout`)

| Route | Page | Primary APIs |
|-------|------|--------------|
| `/dashboard` | `Dashboard.jsx` | `/api/user/dashboard`, `/api/system/summary`, `/api/performance/summary`, `/api/best-tips`, `/api/matches` |
| `/matches` | `MatchCenter.jsx` | `/api/matches` (paginated, status tabs) |
| `/prediction/:id` | `PredictionDetail.jsx` | `/api/predict/:id` (GET cache / POST run) |
| `/accuracy` | `AccuracyCenter.jsx` | `/api/performance/summary`, `/api/best-tips` |
| `/history` | `PredictionHistoryPage.jsx` | `/api/history` |
| `/history/:entryId` | `PredictionHistoryDetailPage.jsx` | `/api/history/:id` |
| `/subscription` | `SubscriptionPage.jsx` | `/api/user/subscription`, `/api/user/quota`, `/api/billing/*` |
| `/favorites` | `FavoritesPage.jsx` | `/api/user/favorites` |
| `/alerts` | `AlertsPage.jsx` | `/api/user/alerts`, `/api/user/settings` |
| `/notifications` | `Notifications.jsx` | `/api/user/notifications` |
| `/settings` | `SettingsPage.jsx` | `/api/user/settings`, `/api/auth/change-password` |

### Admin (role-gated)

| Route | Page | Gate | APIs |
|-------|------|------|------|
| `/admin` | `AdminPanel.jsx` | `AdminRoute` | `/api/admin/stats`, `users`, `health`, `quota` |
| `/admin/accuracy` | `AdminAccuracyCenter.jsx` | `AdminRoute` + admin gate | `/api/admin/accuracy/*` |
| `/admin/learning` | `AdminLearningDashboard.jsx` | `AdminRoute` | `/api/admin/learning/*` |
| `/super-admin` | `SuperAdminPanel.jsx` | `SuperAdminRoute` | admin + commercial APIs |
| `/api-settings` | `ApiSettingsPage.jsx` | `AdminRoute` | **None (local state only)** |

---

## 2. Navigation structure

**Shell:** `DashboardLayout.jsx` — collapsible left sidebar + sticky top header + `Outlet`.

**Primary nav (flat list, 9 items):**
Dashboard → Match Center → Performance → Archive → Favorites → Alerts → Subscription → Notifications → Settings

**Admin section (conditional):**
Admin Panel → Accuracy Center → Learning Dashboard → Super Admin → API Settings

**Gaps vs professional SaaS:**
- No nav grouping (Product / Analytics / Account)
- No breadcrumbs beyond header page title
- `PredictionDetail` (`/prediction/:id`) not in nav — reachable only from Match Center / links
- `Performance` and public `Pricing` naming diverge from “Analytics” / “Subscription” product language
- Notifications header dot is **hardcoded** (always visible) — not tied to unread count
- Mobile: hamburger overlay only; no bottom tab bar

---

## 3. Component inventory

### Application components (domain)

| Component | Used by | Notes |
|-----------|---------|-------|
| `dashboard/DashboardLayout.jsx` | All authenticated routes | App shell |
| `match/TeamBadge.jsx` | Match Center, Prediction Detail | |
| `match/MatchVersusCenter.jsx` | Match Center | |
| `match/DataQualityBadge.jsx` | Prediction Detail | |
| `match/PredictionCacheBanner.jsx` | Prediction Detail | |
| `auth/EmailVerificationBanner.jsx` | DashboardLayout | |
| `auth/PasswordInput.jsx` | Login, Register, etc. | |
| `pricing/PricingContent.jsx` | PricingPage, SubscriptionPage | Shared pricing table |
| `subscription/UpgradeComingSoonDialog.jsx` | SubscriptionPage | Stripe fallback |
| `landing/*` | Landing | Hero, Features, Stats, Pricing, FAQ, Footer |
| `AdminRoute`, `SuperAdminRoute`, `AdminGatePrompt` | Admin pages | |
| `ProtectedRoute` | App.jsx | Auth wrapper |
| `CookieConsent.jsx` | App root | |

### UI primitives (`components/ui/`)

~45 shadcn/Radix components (button, card, tabs, dialog, chart, sidebar, etc.). **Heavily imported library; many components unused in pages** (e.g. `carousel`, `menubar`, `navigation-menu`, `resizable`, `calendar`).

### Page-level duplication

- `resultConfig` / status badge logic duplicated in `PredictionHistoryPage.jsx` and `PredictionHistoryDetailPage.jsx`
- Chart tooltip styles duplicated in `Dashboard.jsx` and `AccuracyCenter.jsx`
- Plan labels duplicated in `SubscriptionPage.jsx` vs `lib/pricingPlans.js`

---

## 4. Dashboard layout assessment

**Current `Dashboard.jsx` (post Phase 49A):**
- Top: 4 system cards (archived, evaluated, pending, platform accuracy) from real APIs
- Middle: Best current tip + system status panel
- Chart: personal performance trend (user history only)
- Side: 5 upcoming matches
- Bottom: personal recent predictions table

**Strengths:** Uses real `/api/system/summary` and `/api/performance/summary`; honest empty states.

**Weaknesses:**
- Mixes **platform** metrics and **personal** metrics without visual separation
- No live matches section
- No weather alerts surfacing (weather exists in Prediction Detail backend)
- No market performance mini-panel on dashboard (only on `/accuracy`)
- Not a true “command center” — still feels like a post-login utility page

---

## 5. Archive pages

**List (`PredictionHistoryPage.jsx`):**
- Scopes: All / My / Global Archive
- Filters: correct / wrong / pending / partial (stats)
- Sort + pagination (50/page)
- Cards: status colors, source badges, market counts (post hotfix)
- APIs: `/api/history?scope=&sort=&offset=`

**Detail (`PredictionHistoryDetailPage.jsx`):**
- Per-market rows with result_status
- Consistency guard section
- Premium placeholders (specialist votes, odds movement, snapshots) — **“coming soon”** blocks
- Missing: evaluation source label, agent summary, confidence trace as first-class sections

**Strengths:** Aligned with Performance Center after archive status hotfix (3 correct / 1 wrong / 51 pending).

---

## 6. Subscription pages

| Surface | File | Stripe |
|---------|------|--------|
| Public pricing | `PricingPage.jsx` + `PricingContent.jsx` | Links to register |
| In-app subscription | `SubscriptionPage.jsx` | Live checkout + portal |
| Plans source | `lib/pricingPlans.js` | Free €0 / Starter €5 / Pro €19 |

**Features shown:** quota bar, billing history, contact admin, upgrade CTAs, `UpgradeComingSoonDialog` when billing not ready.

**Gaps:** No dedicated “Billing” sub-route; profile vs billing vs plan not separated in nav.

---

## 7. Admin pages

| Page | Maturity | Data source |
|------|----------|-------------|
| `AdminPanel` | Functional | Real PostgreSQL stats, users, health, quota |
| `AdminAccuracyCenter` | Functional | Evaluation inspector, filters |
| `AdminLearningDashboard` | Functional | Learning reports, optimization |
| `SuperAdminPanel` | Functional | User roles, billing, commercial analytics |
| `ApiSettingsPage` | **Stub** | Local state; fake “check status” timeout |

Admin is correctly hidden via `canSeeAdminNav` / role routes.

---

## 8. API integrations map

### `saasApi.js` (authenticated SaaS)

| Function | Endpoint | Used by pages |
|----------|----------|---------------|
| `fetchDashboard` | `/api/user/dashboard` | Dashboard |
| `fetchSystemSummary` | `/api/system/summary` | Dashboard, Landing stats |
| `fetchPerformanceSummary` | `/api/performance/summary` | Dashboard, AccuracyCenter |
| `fetchPerformanceMonitoring` | `/api/performance/monitoring` | **Defined, unused in pages** |
| `fetchBestTips` | `/api/best-tips` | Dashboard, AccuracyCenter |
| `fetchHistoryArchive` | `/api/history` | PredictionHistoryPage |
| `fetchPredictionHistoryEntry` | `/api/history/:id` | PredictionHistoryDetailPage |
| `fetchSubscription` / `fetchUserQuota` | user + billing | SubscriptionPage |
| Admin_* | `/api/admin/*` | Admin pages |

### `worldcupApi.js` (predictions + matches)

| Function | Endpoint | Used by |
|----------|----------|---------|
| `fetchMatches` | `/api/matches` | MatchCenter, Dashboard |
| `fetchCachedPrediction` / `runPrediction` | `/api/predict/:id` | PredictionDetail |
| `fetchHealth` | `/api/health` | **Unused in pages** |

### `authApi.js`

Login, register, verify, password — used by auth pages only.

### Legacy / dead API wrappers

- `fetchAccuracySummary` → `/api/accuracy/summary` — **no page imports**
- `fetchPredictionHistoryPage` → `/api/user/prediction-history` — **superseded by `/api/history`**

---

## 9. UI duplication

| Pattern | Locations |
|---------|-----------|
| Status badge config | History list + detail |
| Performance chart styling | Dashboard + AccuracyCenter |
| Pricing comparison | `pricingPlans.js` + inline Subscription labels |
| Admin user tables | AdminPanel + SuperAdminPanel (overlap) |
| “Glass card” layout | Every page (consistent but monotonous) |

---

## 10. Dead / stale artifacts

| Item | Status |
|------|--------|
| `TestimonialsSection.jsx` | **Orphaned** — removed from Landing in Phase 49A, file still exists |
| `DEV_ACCURACY_DEMO` | Dev-only fallback in AccuracyCenter (production safe) |
| `UserNotRegisteredError.jsx` | **Unused** in routes |
| `fetchAccuracySummary` | **Unused** |
| `fetchPredictionHistoryPage` | **Unused** |
| `ApiSettingsPage` | Placeholder UX (misleading “operational” check) |
| `components/ui/sidebar.jsx` | shadcn sidebar — **DashboardLayout uses custom sidebar** |
| Repo copies (`_deploy_staging`, `_pack_*`) | Not deployed; create audit noise |

---

## 11. Maturity summary

| Area | Score | Notes |
|------|-------|-------|
| Auth & billing | ★★★★☆ | Stripe live; email verify |
| Match Center | ★★★★☆ | Phase 49A pagination + tabs |
| Prediction Detail | ★★★★☆ | Rich backend data; dense UI |
| Archive | ★★★★☆ | Hotfix aligned; needs polish |
| Performance Center | ★★★★☆ | Real metrics + Rule A |
| Dashboard | ★★★☆☆ | Improved but not “SaaS command center” |
| Navigation / IA | ★★☆☆☆ | Flat, overloaded sidebar |
| Admin | ★★★☆☆ | Functional; fragmented |
| Marketing | ★★★☆☆ | Real stats; still generic landing |
| Design system | ★★★☆☆ | shadcn present; no product-specific tokens |

---

## 12. Constraints for Phase 50 implementation

**Must not touch:**
- `worldcup_predictor/prediction/*` (engine, WDE, agents)
- `worldcup_predictor/decision/*`
- `worldcup_predictor/automation/worldcup_background/*` (learning, evaluation)
- Database schema (unless purely additive read models for UI — not recommended in 50)

**Safe to replace:**
- All `base44-d/src/pages/*`
- `DashboardLayout` and shell components
- `saasApi.js` client wrappers (not backend routes)
- Landing marketing composition

---

**PHASE_50A_STATUS = COMPLETE (audit only, no code changes)**
