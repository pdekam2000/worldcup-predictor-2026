# PHASE 50 — Professional SaaS UI Master Plan

**Mode:** Analyze → Design → Report  
**Date:** 2026-06-22  
**Status:** AWAITING APPROVAL — **NO IMPLEMENTATION**

**Companion document:** [PHASE_50A_UI_ARCHITECTURE_AUDIT.md](./PHASE_50A_UI_ARCHITECTURE_AUDIT.md)

---

## Executive summary

WorldCup Predictor has a **production-ready prediction backend** and a **functional but flat** React frontend. Phase 50 transforms the UI into a professional Football Prediction SaaS shell **without modifying** the prediction engine, agents, WDE, learning system, evaluation logic, or payment processing.

**Strategy:** Backend = asset. Frontend = replaceable. Reorganize information architecture, unify visual language, surface real data only, and retire dead UI — using **existing APIs** wherever possible with **minimal additive read endpoints** only if dashboard gaps cannot be closed otherwise.

**Production baseline (verified post hotfix):**
- Archive: 3 Correct · 1 Wrong · 51 Pending
- Performance Center aligned with archive evaluation join
- Plans: Free (4/mo) · Starter €5 (28/mo) · Pro €19 (60/mo)

---

## 1. Current UI audit (summary)

Full detail in [PHASE_50A_UI_ARCHITECTURE_AUDIT.md](./PHASE_50A_UI_ARCHITECTURE_AUDIT.md).

| Dimension | Finding |
|-----------|---------|
| Routes | 25+ pages; admin correctly gated |
| Navigation | Flat 9-item sidebar; no product grouping |
| Data honesty | Phase 49A removed fake landing stats; archive hotfix fixed evaluation display |
| Dead code | `TestimonialsSection`, unused API wrappers, `ApiSettingsPage` stub |
| Biggest gap | No SaaS information hierarchy; dashboard mixes platform vs personal metrics |

---

## 2. Proposed SaaS structure (Phase 50B)

### Target information architecture

```
Dashboard
├── Overview                    → /dashboard
├── Best Picks                  → /dashboard#best-picks (or /predictions/best)
├── Accuracy Snapshot           → /dashboard#accuracy (links to /analytics/accuracy)
├── Subscription Status         → /dashboard#plan (links to /subscription)
└── Recent Evaluations          → /dashboard#recent-results

Match Center
├── Upcoming                    → /matches?status=upcoming
├── Live                        → /matches?status=live
├── Finished                    → /matches?status=finished
└── Prediction Archive          → /history (cross-link from Match Center)

Predictions
├── 1X2                         → /prediction/:id (market tab default)
├── BTTS                        → /prediction/:id#btts
├── Over/Under                  → /prediction/:id#ou
├── Goal Minute                 → /prediction/:id#goal-minute
├── First Goal Team             → /prediction/:id#first-goal
└── Correct Score               → /prediction/:id#correct-score

Analytics
├── Accuracy Center             → /analytics/accuracy (migrate from /accuracy)
├── Market Performance          → /analytics/markets
├── League Performance          → /analytics/leagues
└── Prediction Trends           → /analytics/trends

Subscription
├── Free                        → /subscription (current plan highlight)
├── Starter                     → /subscription#starter
└── Pro                         → /subscription#pro

Account
├── Profile                     → /account/profile (split from /settings)
├── Billing                     → /account/billing (from SubscriptionPage)
└── Settings                    → /account/settings

Admin (hidden)
├── Users                       → /admin
├── Predictions                 → /admin/predictions (new view, existing APIs)
├── Evaluations                 → /admin/accuracy
├── System Health               → /admin#health
└── API Status                  → /admin/api-status (replace stub)
```

### Route migration map (backward compatible)

| Current | Proposed | Action |
|---------|----------|--------|
| `/dashboard` | `/dashboard` | Redesign in place |
| `/matches` | `/matches` | Add query-param deep links |
| `/accuracy` | `/analytics/accuracy` | Redirect alias `/accuracy` → new path |
| `/history` | `/history` | Keep; improve UX |
| `/subscription` | `/subscription` + `/account/billing` | Split billing tab |
| `/settings` | `/account/settings` | Redirect alias |
| `/admin` | `/admin` | Enhance layout |
| `/api-settings` | `/admin/api-status` | Replace stub with real health |

**No new prediction routes required** — market sub-views are tabs/anchors on existing `PredictionDetail`.

---

## 3. Navigation map

### Desktop sidebar (grouped)

```
┌─────────────────────────────────────┐
│  ⚽ WorldCup Predictor              │
├─────────────────────────────────────┤
│  HOME                               │
│    ○ Overview          /dashboard   │
│                                     │
│  MATCHES                            │
│    ○ Match Center      /matches     │
│    ○ Archive           /history     │
│                                     │
│  PREDICTIONS                        │
│    ○ Best Picks        /dashboard#… │
│                                     │
│  ANALYTICS                          │
│    ○ Accuracy          /analytics…  │
│    ○ Markets           /analytics…  │
│    ○ Leagues           /analytics…  │
│    ○ Trends            /analytics…  │
│                                     │
│  ACCOUNT                            │
│    ○ Subscription      /subscription│
│    ○ Favorites         /favorites   │
│    ○ Alerts            /alerts      │
│    ○ Settings          /account/…   │
├─────────────────────────────────────┤
│  ADMIN (role-gated)                 │
│    ○ Dashboard         /admin       │
│    ○ Evaluations       /admin/acc…  │
│    ○ Learning          /admin/lear… │
│    ○ Super Admin       /super-admin │
└─────────────────────────────────────┘
```

### Top header

- Page title + breadcrumb trail
- **Real** notification badge (`unread_count` from `/api/user/notifications`)
- Quota chip (predictions remaining this period)
- User menu: Profile · Billing · Log out

### Mobile

- Collapsible sidebar (existing)
- Optional Phase 50.3: bottom nav (Home · Matches · Archive · Account)

### Public site

- Landing → Pricing → Register unchanged
- Header: Product · Pricing · Login

---

## 4. Dashboard wireframe (Phase 50C)

**Principle: REAL DATA ONLY** — every widget maps to an existing or minimally extended read API.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Good morning, {user}          [Starter · 12/28 left]  [🔔 3]  [Avatar] │
├──────────────────────────────────────────────────────────────────────────┤
│  TOP METRICS (4 cards)                                                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │
│  │ Active      │ │ Accuracy    │ │ Evaluated   │ │ Current Plan│        │
│  │ Predictions │ │ (platform)  │ │ Matches     │ │ + upgrade   │        │
│  │ 51 pending  │ │ 75.0%       │ │ 4           │ │ Starter €5  │        │
│  │ system sum  │ │ perf/summary│ │ system sum  │ │ subscription  │        │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘        │
├──────────────────────────────────────────────────────────────────────────┤
│  MIDDLE ROW                                                              │
│  ┌────────────────────────────┐  ┌────────────────────────────┐         │
│  │ Best Opportunities         │  │ Top Confidence Picks       │         │
│  │ fetchBestTips (top 3)      │  │ best-tips sorted by conf   │         │
│  │ → link /prediction/:id     │  │                            │         │
│  └────────────────────────────┘  └────────────────────────────┘         │
│  ┌────────────────────────────┐  ┌────────────────────────────┐         │
│  │ Weather Alerts             │  │ Live Matches               │         │
│  │ from upcoming matches w/   │  │ fetchMatches status=live   │         │
│  │ weather_flag in predict    │  │ empty state if none        │         │
│  │ cache OR match metadata*   │  │                            │         │
│  └────────────────────────────┘  └────────────────────────────┘         │
├──────────────────────────────────────────────────────────────────────────┤
│  BOTTOM ROW                                                              │
│  ┌────────────────────────────┐  ┌────────────────────────────┐         │
│  │ Recent Prediction Results  │  │ Accuracy Trend (chart)     │         │
│  │ history scope=all filter   │  │ performance/summary series │         │
│  │ evaluated only, last 10    │  │                            │         │
│  └────────────────────────────┘  └────────────────────────────┘         │
│  ┌──────────────────────────────────────────────────────────┐           │
│  │ Market Performance (mini bar chart)                       │           │
│  │ performance/summary.by_market                               │           │
│  └──────────────────────────────────────────────────────────┘           │
└──────────────────────────────────────────────────────────────────────────┘
```

### Data source matrix

| Widget | API | Fallback |
|--------|-----|----------|
| Active Predictions | `GET /api/system/summary` → `pending_count` | Hide card if API fails |
| Accuracy | `GET /api/performance/summary` → `accuracy_rate` | Show "—" |
| Evaluated Matches | `system/summary.evaluated_count` | — |
| Current Plan | `GET /api/user/subscription` + `quota` | Free tier defaults |
| Best Opportunities | `GET /api/best-tips` | Empty state CTA → Match Center |
| Top Confidence | Same, sorted client-side | — |
| Weather Alerts | `GET /api/matches?status=upcoming` + cached predict weather fields* | "No alerts" |
| Live Matches | `GET /api/matches?status=live` | "No live matches" |
| Recent Results | `GET /api/history?scope=all&result=evaluated&limit=10` | — |
| Accuracy Trend | `performance/summary.history` or user dashboard trend | — |
| Market Performance | `performance/summary.by_market` | — |

\* **Weather alerts:** Prefer reading `weather` block from cached prediction responses for upcoming fixtures (batch GET cache if available). If no batch endpoint exists, show alerts only for matches user has opened — **no fabricated alerts**. Optional Phase 50.1 additive endpoint: `GET /api/matches/upcoming-alerts` (read-only aggregation) — only if client-side approach is too slow.

### Visual hierarchy

1. **Platform truth** (top cards) — system-wide, same numbers as Archive stats bar
2. **Action** (middle) — where to bet attention today
3. **Proof** (bottom) — evaluated results and trends build trust

---

## 5. Archive UX redesign (Phase 50D)

### List view — card system

| Status | Color | Border | Icon |
|--------|-------|--------|------|
| Correct | Green `emerald-500/15` | `border-emerald-500/30` | ✓ |
| Wrong | Red `red-500/15` | `border-red-500/30` | ✗ |
| Pending | Yellow `amber-500/10` | `border-amber-500/20` | ◷ |
| Partial | Purple/Blue `violet-500/15` | `border-violet-500/30` | ◑ |

**Card content (each row):**

```
┌────────────────────────────────────────────────────────────┐
│ [CORRECT]  Brazil vs Argentina          Eval: 12 Jun 2026  │
│                                                            │
│ Prediction: Home Win (1)     Confidence: 72%                 │
│ Markets: 1X2 ✓ · BTTS ✓ · O/U — · CS ✗                    │
│ Counts: 2 correct · 1 wrong · 1 pending                    │
│ Source: global_archive                    [View detail →]  │
└────────────────────────────────────────────────────────────┘
```

**Fields (all from `/api/history` enriched rows post hotfix):**
- `match_label` / home vs away
- `main_prediction` + `confidence`
- `market_results[]` with per-market status
- `markets_correct_count`, `markets_wrong_count`, `markets_pending_count`
- `evaluated_at` / `evaluation_date`
- `result_status` (card-level)

**UX improvements:**
- Sticky filter chips with live counts (already partially implemented)
- Default sort: `evaluated_at desc` for evaluated filter; `created_at desc` for all
- Compact vs comfortable density toggle
- Skeleton loaders during pagination

### Detail page

```
┌────────────────────────────────────────────────────────────┐
│ ← Back to Archive                                          │
│ Brazil vs Argentina · World Cup 2026 · 12 Jun 2026         │
│ [CORRECT]  Main: Home Win · Confidence 72%                 │
├────────────────────────────────────────────────────────────┤
│ PER-MARKET RESULTS                                         │
│ ┌──────────┬────────────┬──────────┬──────────┐          │
│ │ Market   │ Prediction │ Result   │ Status   │          │
│ ├──────────┼────────────┼──────────┼──────────┤          │
│ │ 1X2      │ Home       │ Home     │ Correct  │          │
│ │ BTTS     │ Yes        │ Yes      │ Correct  │          │
│ │ O/U 2.5  │ Over       │ —        │ Pending  │          │
│ └──────────┴────────────┴──────────┴──────────┘          │
├────────────────────────────────────────────────────────────┤
│ EVALUATION SOURCE                                          │
│ Table: worldcup_prediction_evaluations                     │
│ Evaluated at: … · Resolver: automatic                      │
├────────────────────────────────────────────────────────────┤
│ PREDICTION EXPLANATION                                     │
│ From cached prediction: reasoning / harmonization summary  │
├────────────────────────────────────────────────────────────┤
│ AGENT SUMMARY (if present in prediction payload)           │
│ Specialist votes, WDE output — read-only display           │
├────────────────────────────────────────────────────────────┤
│ CONFIDENCE TRACE                                           │
│ Rule A gate · lambda bridge · promotion flags (read-only)  │
└────────────────────────────────────────────────────────────┘
```

**Remove or relabel** existing “coming soon” premium blocks — replace with honest empty states when backend field is null.

**No evaluation logic changes** — display only what `prediction_archive_detail` and evaluation join already return.

---

## 6. Subscription UX redesign (Phase 50E)

### Current plan structure (unchanged pricing)

| Plan | Price | Monthly predictions | Key features |
|------|-------|---------------------|--------------|
| Free | €0 | 4 | Basic 1X2, limited history |
| Starter | €5 | 28 | Multi-market, archive access |
| Pro | €19 | 60 | Full markets, priority features |

### Upgrade flow design

```
┌────────────────────────────────────────────────────────────┐
│ YOUR PLAN: Starter                    [Manage billing →]   │
│ ████████████░░░░░░  12 of 28 predictions remaining         │
│ Resets: 1 Jul 2026                                         │
├────────────────────────────────────────────────────────────┤
│ FEATURE COMPARISON (PricingContent reused)                 │
│        Free    Starter ✓    Pro                            │
│ 1X2     ✓        ✓          ✓                              │
│ BTTS    —        ✓          ✓                              │
│ …                                                          │
├────────────────────────────────────────────────────────────┤
│ [ Upgrade to Pro — €19/mo ]   (Stripe checkout — no change)│
└────────────────────────────────────────────────────────────┘
```

**Free → Starter → Pro ladder:**
- Free users: prominent “Unlock 28 predictions” CTA
- Starter users: “Go Pro for 60 predictions” secondary CTA
- Pro users: “You're on our best plan” + billing portal

**Display requirements:**
- `remaining_predictions` from `/api/user/quota`
- `plan_limits` from `pricingPlans.js` + subscription tier
- Feature comparison from shared `PricingContent`
- Upgrade CTA routes to existing Stripe checkout handlers

**Explicitly out of scope:** Payment logic, Stripe price IDs, webhook changes.

**Retire:** `UpgradeComingSoonDialog` once billing confirmed live in all environments — or keep as env-guard only.

---

## 7. Admin UX redesign (Phase 50F)

### Admin dashboard layout

```
┌────────────────────────────────────────────────────────────┐
│ ADMIN COMMAND CENTER                                       │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ Users    │ Predictions│ Evaluations│ Accuracy │ API Health │
│ 142      │ 55 archived│ 4 evaluated│ 75%      │ ● OK       │
├──────────┴──────────┴──────────┴──────────┴──────────────┤
│ TABS: Overview | Users | Predictions | Evaluations | Jobs │
├────────────────────────────────────────────────────────────┤
│ System Health                                              │
│ · PostgreSQL connected                                     │
│ · SportMonks quota / last sync                             │
│ · Background jobs: learning_runner, evaluation_runner      │
├────────────────────────────────────────────────────────────┤
│ Learning Status                                            │
│ Link → /admin/learning (existing dashboard)                │
└────────────────────────────────────────────────────────────┘
```

### Data sources (all existing)

| Metric | API |
|--------|-----|
| User counts | `/api/admin/stats` |
| Prediction counts | `/api/admin/stats` or archive count |
| Evaluation counts | `/api/admin/accuracy/summary` |
| Accuracy | `/api/admin/accuracy/*` |
| API health | `/api/admin/health` |
| Background jobs | health payload / learning status |
| Learning | `/api/admin/learning/*` |

### Access control (unchanged)

- `AdminRoute` + `canSeeAdminNav` — normal users never see admin nav
- `SuperAdminRoute` for commercial controls
- Remove misleading `ApiSettingsPage` stub → wire to `/api/admin/health` or delete route

---

## 8. Component list

### New shared components (proposed)

| Component | Purpose |
|-----------|---------|
| `layout/AppShell.jsx` | Extracted from DashboardLayout |
| `layout/SidebarNav.jsx` | Grouped navigation |
| `layout/PageHeader.jsx` | Title + breadcrumbs + actions |
| `layout/QuotaChip.jsx` | Predictions remaining |
| `dashboard/MetricCard.jsx` | Top stat cards |
| `dashboard/BestPicksPanel.jsx` | Best tips list |
| `dashboard/LiveMatchesPanel.jsx` | Live match strip |
| `dashboard/RecentResultsTable.jsx` | Evaluated history excerpt |
| `archive/ArchiveCard.jsx` | Unified status card |
| `archive/StatusBadge.jsx` | correct/wrong/pending/partial |
| `archive/MarketResultRow.jsx` | Detail table row |
| `analytics/MarketPerformanceChart.jsx` | Shared chart |
| `subscription/PlanUsageBar.jsx` | Quota visualization |
| `subscription/UpgradeLadder.jsx` | Free→Starter→Pro |
| `admin/AdminMetricGrid.jsx` | Admin top stats |
| `admin/HealthIndicator.jsx` | API/job status dot |

### Refactor from existing

| Current | Action |
|---------|--------|
| `DashboardLayout.jsx` | Split into AppShell + SidebarNav |
| `PredictionHistoryPage.jsx` | Extract ArchiveCard |
| `PricingContent.jsx` | Reuse in dashboard plan card |
| `resultConfig` duplicates | Consolidate to `archive/StatusBadge` |

### Remove after migration

| File | Reason |
|------|--------|
| `TestimonialsSection.jsx` | Orphaned |
| `UserNotRegisteredError.jsx` | Unused |
| `ApiSettingsPage.jsx` | Replace with real health view |
| `accuracyDemoData.js` | Dev-only; gate behind `import.meta.env.DEV` or remove |

---

## 9. Pages requiring modification

| Priority | Page | Changes |
|----------|------|---------|
| P0 | `Dashboard.jsx` | Full redesign per wireframe |
| P0 | `DashboardLayout.jsx` | Grouped nav, real notification badge, quota chip |
| P0 | `PredictionHistoryPage.jsx` | Card UX, colors, market counts prominence |
| P0 | `PredictionHistoryDetailPage.jsx` | Evaluation source, agent summary, confidence trace |
| P1 | `AccuracyCenter.jsx` | Move to `/analytics/accuracy`; split market/league views |
| P1 | `SubscriptionPage.jsx` | Usage bar, upgrade ladder, billing split |
| P1 | `MatchCenter.jsx` | Deep links, archive cross-link |
| P1 | `PredictionDetail.jsx` | Market tab anchors |
| P2 | `AdminPanel.jsx` | Command center layout |
| P2 | `Landing.jsx` | Align with new product language |
| P2 | `SettingsPage.jsx` | Profile vs settings split |
| P3 | New analytics sub-pages | Markets, Leagues, Trends (may share AccuracyCenter data) |

---

## 10. Pages that must remain untouched

### Backend (hard constraint)

| Area | Path pattern |
|------|--------------|
| Prediction engine | `worldcup_predictor/prediction/scoring_engine.py`, `lambda_bridge/*`, `odds_primary/*`, `rule_a_gate/*` |
| Agents | `worldcup_predictor/agents/specialists/*` |
| WDE | `worldcup_predictor/decision/weighted_decision_engine.py` |
| Learning | `worldcup_predictor/automation/worldcup_background/*` |
| Evaluation logic | `worldcup_predictor/api/archive_evaluation_join.py` (display-only consumers may change) |
| Stripe webhooks | `worldcup_predictor/api/billing/*` |

### Frontend (minimal touch)

| Page | Reason |
|------|--------|
| `Login.jsx`, `Register.jsx`, auth flows | Stable; security-sensitive |
| `BillingCheckoutSuccess.jsx`, `BillingCheckoutCancel.jsx` | Stripe contract |
| `AdminLearningDashboard.jsx` | Functional; defer restyle to Phase 50.4 |
| Legal pages | Compliance static content |

### APIs — prefer no changes

Existing endpoints sufficient for Phase 50.0. Optional **read-only** additions documented in dashboard section only if weather batch proves necessary.

---

## 11. Risk assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Breaking archive evaluation display | High | Do not change `archive_evaluation_join.py`; UI read-only |
| Route redirects break bookmarks | Medium | Keep `/accuracy`, `/settings` as aliases |
| Dashboard weather alerts without batch API | Medium | Empty state honest; additive read endpoint only if needed |
| Admin stub removal confuses operators | Low | Replace with real health before delete |
| Over-engineering new component library | Medium | Extract incrementally; one page at a time |
| Mixing platform vs user metrics confuses users | Medium | Visual sections + labels (“Platform” vs “Your account”) |
| Stripe upgrade flow regression | High | No payment code changes in Phase 50 |
| Performance (many API calls on dashboard) | Medium | Parallel fetch + React Query caching (already in stack) |
| Mobile nav regression | Low | Test collapsible sidebar first; bottom nav optional |

---

## 12. Implementation phases

### Phase 50.0 — Foundation (shell only)
- Grouped sidebar navigation
- `PageHeader`, `QuotaChip`, real notification badge
- Route aliases for analytics paths
- Remove dead files (`TestimonialsSection`, unused API wrappers)
- **No dashboard widget changes yet**

### Phase 50.1 — Dashboard command center
- Metric cards from `system/summary` + `performance/summary`
- Best picks + live matches panels
- Recent evaluated results + charts
- Weather alerts (client-side or minimal read endpoint)

### Phase 50.2 — Archive polish
- `ArchiveCard` + status color system
- Detail page sections: evaluation source, agent summary, confidence trace
- Remove misleading “coming soon” blocks

### Phase 50.3 — Subscription & account
- Plan usage bar + upgrade ladder
- Split billing from settings (routes only; same APIs)
- Feature comparison prominence

### Phase 50.4 — Analytics expansion
- `/analytics/markets`, `/analytics/leagues`, `/analytics/trends`
- Migrate `/accuracy` content; deprecate old path via redirect

### Phase 50.5 — Admin command center
- Unified admin metrics grid
- Replace `ApiSettingsPage` with real health
- Predictions admin view (read-only table from existing admin APIs)

### Phase 50.6 — Landing & QA
- Marketing copy alignment
- `validate_phase50_ui_shell.py` — route smoke, API contract, no mock data grep
- Production deploy + visual QA

---

## Approval checklist

Before implementation, confirm:

- [ ] Grouped navigation structure approved
- [ ] Dashboard widget set and data sources approved
- [ ] Archive card color system approved (including partial = purple/blue)
- [ ] Route migration map approved (`/analytics/*`, `/account/*`)
- [ ] Admin stub removal approach approved
- [ ] Implementation phase order approved
- [ ] Optional weather alerts endpoint: yes / no / defer

---

**PHASE_50_STATUS = DESIGN COMPLETE — AWAITING APPROVAL**  
**NO CODE CHANGES MADE IN PHASE 50**
